from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Asset,
    CharacterAsset,
    CharacterInstance,
    CharacterTemplate,
    CharacterVersion,
    User,
)
from app.domain.characters import DEVELOPMENT_CHARACTERS
from app.schemas.character import CharacterRead, CharacterWrite
from app.schemas.scene_plan import SceneCharacter


@dataclass(frozen=True, slots=True)
class DevelopmentContext:
    user_id: UUID
    user_display_name: str
    character_instance_ids: dict[str, UUID]
    character_profiles: dict[str, SceneCharacter]


class SQLAlchemyCharacterRepository:
    def __init__(
        self,
        session: Session,
        *,
        development_user_external_id: str,
        development_user_display_name: str,
    ) -> None:
        self.session = session
        self.development_user_external_id = development_user_external_id
        self.development_user_display_name = development_user_display_name

    def ensure_development_context(self) -> DevelopmentContext:
        user = self._ensure_user()
        instance_ids: dict[str, UUID] = {}
        profiles: dict[str, SceneCharacter] = {}
        known_instance_ids: set[UUID] = set()

        for public_id, default in DEVELOPMENT_CHARACTERS.items():
            template = None
            owned_rows = self.session.execute(
                select(CharacterTemplate, CharacterVersion)
                .join(
                    CharacterVersion,
                    CharacterVersion.id == CharacterTemplate.current_version_id,
                )
                .where(CharacterTemplate.creator_user_id == user.id)
            )
            for candidate_template, candidate_version in owned_rows:
                if candidate_version.traits_json.get("public_id") == public_id:
                    template = candidate_template
                    break
            if template is None:
                template = self.session.scalar(
                    select(CharacterTemplate).where(
                        CharacterTemplate.creator_user_id == user.id,
                        CharacterTemplate.name == default.name,
                    )
                )
            if template is None:
                template = CharacterTemplate(
                    creator_user_id=user.id,
                    name=default.name,
                    description=default.concept,
                    visibility="PRIVATE",
                )
                self.session.add(template)
                self.session.flush()

            version = self._current_version(template)
            if version is None:
                version = CharacterVersion(
                    template_id=template.id,
                    version=1,
                    concept_prompt=default.concept,
                    traits_json={"traits": list(default.traits)},
                    speech_style_json={},
                    relationship_defaults_json={},
                    additional_prompt=default.persona,
                )
                self.session.add(version)
                self.session.flush()
                template.current_version_id = version.id

            if version.traits_json.get("public_id") != public_id:
                version.traits_json = {
                    **version.traits_json,
                    "public_id": public_id,
                }

            instance = self.session.scalar(
                select(CharacterInstance).where(
                    CharacterInstance.user_id == user.id,
                    CharacterInstance.template_id == template.id,
                )
            )
            if instance is None:
                instance = CharacterInstance(
                    user_id=user.id,
                    template_id=template.id,
                    version_id=version.id,
                )
                self.session.add(instance)
                self.session.flush()

            instance_ids[public_id] = instance.id
            profiles[public_id] = self._scene_character(public_id, template, version)
            known_instance_ids.add(instance.id)

        additional_rows = self.session.execute(
            select(CharacterInstance, CharacterTemplate, CharacterVersion)
            .join(CharacterTemplate, CharacterTemplate.id == CharacterInstance.template_id)
            .join(CharacterVersion, CharacterVersion.id == CharacterInstance.version_id)
            .where(
                CharacterInstance.user_id == user.id,
                CharacterInstance.archived_at.is_(None),
            )
        )
        for instance, template, version in additional_rows:
            if instance.id in known_instance_ids:
                continue
            public_id = str(instance.id)
            instance_ids[public_id] = instance.id
            profiles[public_id] = self._scene_character(public_id, template, version)

        self.session.commit()
        return DevelopmentContext(
            user_id=user.id,
            user_display_name=user.display_name,
            character_instance_ids=instance_ids,
            character_profiles=profiles,
        )

    def update_display_name(self, display_name: str) -> DevelopmentContext:
        user = self._ensure_user()
        user.display_name = display_name
        self.session.commit()
        return self.ensure_development_context()

    def list_characters(self) -> list[CharacterRead]:
        context = self.ensure_development_context()
        reverse_ids = {
            instance_id: public_id
            for public_id, instance_id in context.character_instance_ids.items()
        }
        rows = self.session.execute(
            select(CharacterInstance, CharacterTemplate, CharacterVersion)
            .join(CharacterTemplate, CharacterTemplate.id == CharacterInstance.template_id)
            .join(CharacterVersion, CharacterVersion.id == CharacterInstance.version_id)
            .where(
                CharacterInstance.user_id == context.user_id,
                CharacterInstance.archived_at.is_(None),
            )
            .order_by(CharacterTemplate.created_at.asc())
        )
        return [
            self._character_read(reverse_ids[instance.id], instance, template, version)
            for instance, template, version in rows
        ]

    def get_character(self, public_id: str) -> CharacterRead | None:
        context = self.ensure_development_context()
        instance_id = context.character_instance_ids.get(public_id)
        if instance_id is None:
            return None
        row = self.session.execute(
            select(CharacterInstance, CharacterTemplate, CharacterVersion)
            .join(CharacterTemplate, CharacterTemplate.id == CharacterInstance.template_id)
            .join(CharacterVersion, CharacterVersion.id == CharacterInstance.version_id)
            .where(
                CharacterInstance.id == instance_id,
                CharacterInstance.user_id == context.user_id,
                CharacterInstance.archived_at.is_(None),
            )
        ).one_or_none()
        if row is None:
            return None
        instance, template, version = row
        return self._character_read(public_id, instance, template, version)

    def create_character(self, value: CharacterWrite) -> CharacterRead:
        user = self._ensure_user()
        template = CharacterTemplate(
            creator_user_id=user.id,
            name=value.name,
            description=value.concept,
            visibility="PRIVATE",
        )
        self.session.add(template)
        self.session.flush()
        version = self._new_version(template, value, version_number=1)
        template.current_version_id = version.id
        instance = CharacterInstance(
            user_id=user.id,
            template_id=template.id,
            version_id=version.id,
            nickname_override=value.nickname,
        )
        self.session.add(instance)
        self.session.commit()
        return self._character_read(str(instance.id), instance, template, version)

    def update_character(
        self, public_id: str, value: CharacterWrite
    ) -> CharacterRead | None:
        context = self.ensure_development_context()
        instance_id = context.character_instance_ids.get(public_id)
        if instance_id is None:
            return None
        row = self.session.execute(
            select(CharacterInstance, CharacterTemplate)
            .join(CharacterTemplate, CharacterTemplate.id == CharacterInstance.template_id)
            .where(
                CharacterInstance.id == instance_id,
                CharacterInstance.user_id == context.user_id,
                CharacterInstance.archived_at.is_(None),
            )
        ).one_or_none()
        if row is None:
            return None
        instance, template = row
        latest_version = self.session.scalar(
            select(func.max(CharacterVersion.version)).where(
                CharacterVersion.template_id == template.id
            )
        ) or 0
        version = self._new_version(
            template,
            value,
            latest_version + 1,
            public_id=public_id if public_id in DEVELOPMENT_CHARACTERS else None,
        )
        template.name = value.name
        template.description = value.concept
        template.current_version_id = version.id
        instance.version_id = version.id
        instance.nickname_override = value.nickname
        self.session.commit()
        return self._character_read(public_id, instance, template, version)

    def upload_portrait(
        self,
        public_id: str,
        *,
        content: bytes,
        mime_type: str,
    ) -> CharacterRead | None:
        context = self.ensure_development_context()
        instance_id = context.character_instance_ids.get(public_id)
        if instance_id is None:
            return None
        row = self.session.execute(
            select(CharacterInstance, CharacterTemplate, CharacterVersion)
            .join(CharacterTemplate, CharacterTemplate.id == CharacterInstance.template_id)
            .join(CharacterVersion, CharacterVersion.id == CharacterInstance.version_id)
            .where(
                CharacterInstance.id == instance_id,
                CharacterInstance.user_id == context.user_id,
                CharacterInstance.archived_at.is_(None),
            )
        ).one_or_none()
        if row is None:
            return None
        instance, template, version = row

        suffix = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }[mime_type]
        old_links = self.session.scalars(
            select(CharacterAsset).where(
                CharacterAsset.character_template_id == template.id,
                CharacterAsset.asset_role == "PORTRAIT",
            )
        ).all()
        old_paths: list[Path] = []
        for link in old_links:
            old_asset = self.session.get(Asset, link.asset_id)
            if old_asset is not None and old_asset.storage_uri.startswith("/uploads/"):
                old_paths.append(
                    self._backend_root() / old_asset.storage_uri.lstrip("/")
                )
            self.session.delete(link)
            if old_asset is not None:
                self.session.delete(old_asset)

        asset = Asset(
            owner_user_id=context.user_id,
            asset_type="IMAGE",
            storage_uri="",
            mime_type=mime_type,
            metadata_json={"role": "PORTRAIT"},
        )
        self.session.add(asset)
        self.session.flush()
        relative_uri = f"/uploads/character-portraits/{asset.id}{suffix}"
        destination = self._backend_root() / relative_uri.lstrip("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        asset.storage_uri = relative_uri
        self.session.add(
            CharacterAsset(
                character_template_id=template.id,
                character_version_id=None,
                asset_id=asset.id,
                asset_role="PORTRAIT",
                display_order=0,
            )
        )
        self.session.commit()
        for old_path in old_paths:
            old_path.unlink(missing_ok=True)
        return self._character_read(public_id, instance, template, version)

    def _ensure_user(self) -> User:
        user = self.session.scalar(
            select(User).where(User.external_auth_id == self.development_user_external_id)
        )
        if user is None:
            user = User(
                display_name=self.development_user_display_name,
                external_auth_id=self.development_user_external_id,
            )
            self.session.add(user)
            self.session.flush()
        return user

    def _current_version(
        self, template: CharacterTemplate
    ) -> CharacterVersion | None:
        if template.current_version_id is not None:
            version = self.session.get(CharacterVersion, template.current_version_id)
            if version is not None:
                return version
        return self.session.scalar(
            select(CharacterVersion)
            .where(CharacterVersion.template_id == template.id)
            .order_by(CharacterVersion.version.desc())
        )

    def _new_version(
        self,
        template: CharacterTemplate,
        value: CharacterWrite,
        version_number: int,
        public_id: str | None = None,
    ) -> CharacterVersion:
        version = CharacterVersion(
            template_id=template.id,
            version=version_number,
            age=value.age,
            occupation=value.occupation,
            gender=value.gender,
            concept_prompt=value.concept,
            traits_json={
                "traits": value.traits,
                **({"public_id": public_id} if public_id else {}),
            },
            speech_style_json={
                "style": value.speech_style,
                "response_length": value.response_length,
                "voice_label": value.voice_label,
                "typecast_voice_id": value.typecast_voice_id or "",
            },
            relationship_defaults_json={"style": value.relationship_style},
            additional_prompt=value.persona,
            additional_character_prompt=value.additional_prompt,
        )
        self.session.add(version)
        self.session.flush()
        return version

    def _scene_character(
        self,
        public_id: str,
        template: CharacterTemplate,
        version: CharacterVersion,
    ) -> SceneCharacter:
        return SceneCharacter(
            id=public_id,
            name=template.name,
            age=version.age,
            age_group=self._age_group(version.age),
            occupation=self._occupation(version),
            gender=self._gender(version),
            concept=version.concept_prompt,
            persona=self._scene_persona(version),
            traits=list(version.traits_json.get("traits", [])),
            speech_style=str(version.speech_style_json.get("style", "")),
            relationship_style=str(
                version.relationship_defaults_json.get("style", "")
            ),
        )

    def _character_read(
        self,
        public_id: str,
        instance: CharacterInstance,
        template: CharacterTemplate,
        version: CharacterVersion,
    ) -> CharacterRead:
        return CharacterRead(
            id=public_id,
            version=version.version,
            name=template.name,
            nickname=instance.nickname_override,
            age=version.age,
            occupation=self._occupation(version),
            gender=self._gender(version),
            concept=version.concept_prompt,
            persona=version.additional_prompt,
            additional_prompt=version.additional_character_prompt,
            traits=list(version.traits_json.get("traits", [])),
            speech_style=str(version.speech_style_json.get("style", "관계에 따라 변화")),
            response_length=str(version.speech_style_json.get("response_length", "보통")),
            relationship_style=str(
                version.relationship_defaults_json.get("style", "편한 친구")
            ),
            voice_label=str(version.speech_style_json.get("voice_label", "")),
            typecast_voice_id=(str(version.speech_style_json.get("typecast_voice_id", "")).strip() or None),
            image_url=self._portrait_url(template.id),
        )

    def _portrait_url(self, template_id: UUID) -> str | None:
        return self.session.scalar(
            select(Asset.storage_uri)
            .join(CharacterAsset, CharacterAsset.asset_id == Asset.id)
            .where(
                CharacterAsset.character_template_id == template_id,
                CharacterAsset.asset_role == "PORTRAIT",
            )
            .order_by(CharacterAsset.display_order.asc(), Asset.created_at.desc())
        )

    @staticmethod
    def _scene_persona(version: CharacterVersion) -> str:
        base_persona = version.additional_prompt.strip()
        extra_persona = version.additional_character_prompt.strip()
        if not extra_persona:
            return base_persona
        if not base_persona:
            return f"추가 캐릭터성: {extra_persona}"
        return f"{base_persona}\n추가 캐릭터성: {extra_persona}"

    @staticmethod
    def _backend_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def _occupation(version: CharacterVersion) -> str:
        if version.occupation:
            return version.occupation
        # Pre-0006 characters stored the occupation only inside the generated
        # concept sentence. Keep that value editable until the user saves a
        # new version with a dedicated occupation field.
        match = re.search(r"([^.]+)\(으\)로 지내고 있다\.", version.concept_prompt)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _gender(version: CharacterVersion) -> str:
        if version.gender in {"male", "female"}:
            return version.gender
        if "남성이다." in version.concept_prompt:
            return "male"
        if "여성이다." in version.concept_prompt:
            return "female"
        return "unspecified"

    @staticmethod
    def _age_group(age: int | None) -> str:
        if age is None:
            return ""
        if age <= 12:
            return "아동"
        if age <= 18:
            return "청소년"
        if age <= 24:
            return "초기 성인"
        if age <= 39:
            return "성인"
        if age <= 64:
            return "중년"
        return "노년"


