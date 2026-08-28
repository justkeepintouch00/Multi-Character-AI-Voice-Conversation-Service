from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CharacterInstance, Scenario, ScenarioCharacter, ScenarioScene, User
from app.repositories.characters import SQLAlchemyCharacterRepository
from app.schemas.scenario import ScenarioDraftRead, ScenarioDraftWrite


_MODE_TO_DATABASE = {"A": "PRACTICE", "B": "SCENARIO", "C": "TALK"}
_MODE_FROM_DATABASE = {value: key for key, value in _MODE_TO_DATABASE.items()}


class SQLAlchemyScenarioRepository:
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
        self.character_repository = SQLAlchemyCharacterRepository(
            session,
            development_user_external_id=development_user_external_id,
            development_user_display_name=development_user_display_name,
        )

    def get_draft(self, scenario_id: str) -> ScenarioDraftRead | None:
        user = self._ensure_user()
        scenario = self._owned_scenario(scenario_id, user.id)
        return self._read(scenario) if scenario is not None else None

    def list_drafts(self) -> list[ScenarioDraftRead]:
        user = self._ensure_user()
        scenarios = self.session.scalars(
            select(Scenario)
            .where(Scenario.creator_user_id == user.id)
            .order_by(Scenario.updated_at.desc())
        ).all()
        return [self._read(scenario) for scenario in scenarios]
    def save_draft(
        self, value: ScenarioDraftWrite, *, scenario_id: str | None = None
    ) -> ScenarioDraftRead | None:
        user = self._ensure_user()
        if scenario_id is None:
            scenario = Scenario(
                creator_user_id=user.id,
                mode=_MODE_TO_DATABASE[value.mode],
                title=value.title,
                description=value.summary,
                status="PUBLISHED" if value.publish else "DRAFT",
            )
            self.session.add(scenario)
            self.session.flush()
        else:
            scenario = self._owned_scenario(scenario_id, user.id)
            if scenario is None:
                return None
            scenario.mode = _MODE_TO_DATABASE[value.mode]
            scenario.title = value.title
            scenario.description = value.summary
            scenario.status = "PUBLISHED" if value.publish else "DRAFT"
            self.session.execute(delete(ScenarioCharacter).where(ScenarioCharacter.scenario_id == scenario.id))
            self.session.execute(delete(ScenarioScene).where(ScenarioScene.scenario_id == scenario.id))
            self.session.flush()

        character_template_ids = self._resolve_template_ids(value.character_ids)
        for display_order, template_id in enumerate(character_template_ids):
            self.session.add(
                ScenarioCharacter(
                    scenario_id=scenario.id,
                    character_template_id=template_id,
                    scenario_role="STARTER" if display_order == 0 else "PARTICIPANT",
                    display_order=display_order,
                )
            )
        self.session.add(
            ScenarioScene(
                scenario_id=scenario.id,
                sequence=0,
                description=value.opening_guide,
                scene_config_json={"editor_state": value.editor_state},
            )
        )
        self.session.commit()
        return self._read(scenario)

    def _resolve_template_ids(self, public_ids: list[str]) -> list[UUID]:
        context = self.character_repository.ensure_development_context()
        resolved_instance_ids = [context.character_instance_ids.get(item) for item in public_ids]
        if any(instance_id is None for instance_id in resolved_instance_ids):
            raise ValueError("선택한 캐릭터를 찾을 수 없습니다. 캐릭터 라이브러리에서 다시 선택해 주세요.")
        rows = self.session.execute(
            select(CharacterInstance.id, CharacterInstance.template_id).where(
                CharacterInstance.id.in_(resolved_instance_ids)
            )
        ).all()
        template_by_instance = {instance_id: template_id for instance_id, template_id in rows}
        try:
            return [template_by_instance[instance_id] for instance_id in resolved_instance_ids]
        except KeyError as error:
            raise ValueError("선택한 캐릭터를 찾을 수 없습니다.") from error

    def _read(self, scenario: Scenario) -> ScenarioDraftRead:
        scene = self.session.scalar(
            select(ScenarioScene)
            .where(ScenarioScene.scenario_id == scenario.id)
            .order_by(ScenarioScene.sequence.asc())
        )
        rows = self.session.execute(
            select(ScenarioCharacter, CharacterInstance)
            .join(CharacterInstance, CharacterInstance.template_id == ScenarioCharacter.character_template_id)
            .where(
                ScenarioCharacter.scenario_id == scenario.id,
                CharacterInstance.user_id == scenario.creator_user_id,
                CharacterInstance.archived_at.is_(None),
            )
            .order_by(ScenarioCharacter.display_order.asc())
        ).all()
        context = self.character_repository.ensure_development_context()
        public_id_by_instance_id = {
            str(instance_id): public_id
            for public_id, instance_id in context.character_instance_ids.items()
        }
        return ScenarioDraftRead(
            id=str(scenario.id),
            mode=_MODE_FROM_DATABASE[scenario.mode],
            title=scenario.title,
            summary=scenario.description,
            opening_guide=scene.description if scene is not None else "",
            character_ids=[
                public_id_by_instance_id.get(str(instance.id), str(instance.id))
                for _, instance in rows
            ],
            editor_state=(scene.scene_config_json.get("editor_state", {}) if scene is not None else {}),
            status=scenario.status,
        )

    def _owned_scenario(self, scenario_id: str, user_id: UUID) -> Scenario | None:
        try:
            parsed_id = UUID(scenario_id)
        except ValueError:
            return None
        return self.session.scalar(
            select(Scenario).where(Scenario.id == parsed_id, Scenario.creator_user_id == user_id)
        )

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


