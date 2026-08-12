from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CharacterInstance, CharacterTemplate, CharacterVersion, User
from app.domain.characters import DEVELOPMENT_CHARACTERS
from app.schemas.character import CharacterRead, CharacterWrite
from app.schemas.scene_plan import SceneCharacter


@dataclass(frozen=True, slots=True)
class DevelopmentContext:
    user_id: UUID
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
            character_instance_ids=instance_ids,
            character_profiles=profiles,
        )

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
            concept_prompt=value.concept,
            traits_json={
                "traits": value.traits,
                **({"public_id": public_id} if public_id else {}),
            },
            speech_style_json={
                "style": value.speech_style,
                "response_length": value.response_length,
                "voice_label": value.voice_label,
            },
            relationship_defaults_json={"style": value.relationship_style},
            additional_prompt=value.persona,
        )
        self.session.add(version)
        self.session.flush()
        return version

    @staticmethod
    def _scene_character(
        public_id: str,
        template: CharacterTemplate,
        version: CharacterVersion,
    ) -> SceneCharacter:
        return SceneCharacter(
            id=public_id,
            name=template.name,
            concept=version.concept_prompt,
            persona=version.additional_prompt,
            traits=list(version.traits_json.get("traits", [])),
            speech_style=str(version.speech_style_json.get("style", "")),
            relationship_style=str(
                version.relationship_defaults_json.get("style", "")
            ),
        )

    @staticmethod
    def _character_read(
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
            concept=version.concept_prompt,
            persona=version.additional_prompt,
            traits=list(version.traits_json.get("traits", [])),
            speech_style=str(version.speech_style_json.get("style", "관계에 따라 변화")),
            response_length=str(version.speech_style_json.get("response_length", "보통")),
            relationship_style=str(
                version.relationship_defaults_json.get("style", "편한 친구")
            ),
            voice_label=str(version.speech_style_json.get("voice_label", "")),
        )
