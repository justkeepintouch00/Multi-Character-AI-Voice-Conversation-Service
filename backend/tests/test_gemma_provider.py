from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.api import dependencies
from app.providers.base import ProviderConfigurationError
from app.providers.gemma import GemmaSceneDirector
from app.providers.groq import GroqSceneDirector
from app.schemas.scene_plan import SceneCharacter
from app.schemas.speaker_turn import SpeakerTurnRequest


CHARACTER = SceneCharacter(
    id="character_a",
    name="루미",
    concept="사용자의 말을 차분하게 듣는 대화 캐릭터입니다.",
    persona="차분하게 반응한다.",
    traits=["차분한"],
)


def primary_turn_payload() -> dict[str, object]:
    return {
        "speaker_id": "character_a",
        "to": "USER",
        "emotion": "calm",
        "text": "천천히 이야기해도 괜찮아.",
        "needs_second_speaker": False,
        "second_speaker_reason": "NONE",
        "extracted_memory": {
            "has_memory": False,
            "content": "",
            "sensitivity": "PERSONAL",
        },
        "disclosed_memory_ids": [],
    }


def test_gemma_scene_director_uses_openai_compatible_chat_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers.get("authorization") is None
        payload = json.loads(request.content)
        assert payload["model"] == "gemma4-e2b"
        assert payload["temperature"] == 0.2
        assert payload["top_p"] == 0.95
        assert payload["max_tokens"] == 768
        assert payload["stream"] is True
        assert payload["response_format"] == {"type": "json_object"}

        prompt = json.loads(payload["messages"][1]["content"])
        assert prompt["speaker"]["id"] == "character_a"
        assert prompt["required_output_schema"]["properties"]["speaker_id"]["enum"] == ["character_a"]
        chunks = [
            {"choices": [{"delta": {"content": part}}]}
            for part in ("Result:\n```json\n", json.dumps(primary_turn_payload(), ensure_ascii=False), "\n```")
        ]
        body = "".join(
            f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n" for chunk in chunks
        )
        body += "data: [DONE]\n\n"
        return httpx.Response(
            200,
            text=body,
            headers={"content-type": "text/event-stream"},
        )

    provider = GemmaSceneDirector(
        base_url="http://127.0.0.1:9379/v1",
        model="gemma4-e2b",
        transport=httpx.MockTransport(handler),
    )
    turn = asyncio.run(
        provider.create_speaker_turn(
            SpeakerTurnRequest(
                role="PRIMARY",
                user_text="오늘 조금 힘들었어.",
                speaker=CHARACTER,
            )
        )
    )

    assert turn.speaker_id == "character_a"
    assert turn.text == "천천히 이야기해도 괜찮아."


def test_scene_director_selection_keeps_groq_and_adds_gemma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies, "get_scene_director_provider_name", lambda: "groq"
    )
    assert isinstance(
        dependencies.get_scene_director_provider(), GroqSceneDirector
    )

    monkeypatch.setattr(
        dependencies,
        "get_scene_director_provider_name",
        lambda: "gemma4_e2b",
    )
    assert isinstance(
        dependencies.get_scene_director_provider(), GemmaSceneDirector
    )


def test_scene_director_selection_rejects_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies,
        "get_scene_director_provider_name",
        lambda: "unknown",
    )
    with pytest.raises(
        ProviderConfigurationError,
        match="Unsupported SCENE_DIRECTOR_PROVIDER",
    ):
        dependencies.get_scene_director_provider()


