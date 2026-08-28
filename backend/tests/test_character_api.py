from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.dependencies import get_character_service
from app.main import app
from app.schemas.character import CharacterListResponse, CharacterRead, CharacterWrite


CHARACTER = CharacterRead(
    id="character_a",
    version=2,
    name="루미",
    nickname=None,
    age=24,
    occupation="시계 공방 주인",
    gender="female",
    concept="오래된 골목의 시계 공방에서 일하며 상대의 말을 차분하게 듣고 이전 대화의 구체적인 내용을 오래 기억하는 동반자 캐릭터다.",
    persona="일상적인 대화에서는 과도한 상담 문구 없이 자연스럽고 짧게 반응한다.",
    traits=["차분한", "섬세한"],
    speech_style="관계에 따라 변화",
    response_length="짧게 말함",
    relationship_style="차분하게 이끌어주는 선배",
    voice_label="낮고 차분한 목소리",
)


class FakeCharacterService:
    def list_characters(self) -> CharacterListResponse:
        return CharacterListResponse(items=[CHARACTER])

    def get_character(self, character_id: str) -> CharacterRead:
        assert character_id == "character_a"
        return CHARACTER

    def create_character(self, request: CharacterWrite) -> CharacterRead:
        return CHARACTER.model_copy(update=request.model_dump())

    def update_character(
        self, character_id: str, request: CharacterWrite
    ) -> CharacterRead:
        assert character_id == "character_a"
        return CHARACTER.model_copy(update={**request.model_dump(), "version": 3})


client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_character_service] = FakeCharacterService


def teardown_function() -> None:
    app.dependency_overrides = {}


def test_list_characters() -> None:
    response = client.get("/api/v1/characters")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "character_a"


def test_update_character_creates_new_version_contract() -> None:
    payload = CHARACTER.model_dump(exclude={"id", "version", "image_url"})
    payload["age"] = 25
    payload["occupation"] = "시계 공방 운영자"
    payload["gender"] = "female"
    payload["persona"] = "과장된 위로 대신 사용자의 일상 표현에 자연스럽고 구체적으로 반응한다."

    response = client.put("/api/v1/characters/character_a", json=payload)

    assert response.status_code == 200
    assert response.json()["version"] == 3
    assert response.json()["age"] == 25
    assert response.json()["occupation"] == "시계 공방 운영자"
    assert response.json()["gender"] == "female"
    assert response.json()["persona"] == payload["persona"]
