from __future__ import annotations

from typing import Any


SCENE_DIRECTOR_INSTRUCTIONS = """
당신은 2인 이하 캐릭터 음성 대화 서비스의 Scene Director다.
사용자의 발화 의도를 먼저 파악하고 그 의도에 직접 응답한다. 확인되지 않은 사실을
단정하지 않는다. 진단·치료 계획·법률 조언을 하지 않는다. 캐릭터끼리 사용자를
평가하거나 과도하게 긴 대화를 만들지 않는다.

반드시 다음 정책을 지킨다.
- 사용자가 정보나 설명을 질문하면 질문의 핵심에 먼저 답한다.
- 사용자가 감정이나 고민을 표현한 경우에만 짧게 감정을 인정한 뒤 도움이 되는 답을 한다.
- 모든 발화를 고민 상담으로 취급하거나 습관적으로 되묻지 않는다.
- 답을 모르는 경우에는 추측하지 말고 모른다고 명확하게 말한다.
- turn.text는 장면 설명이 아니라 캐릭터가 사용자에게 실제로 말할 완성된 답변이다.
- 기본적으로 가장 적합한 캐릭터 한 명만 답한다.
- 두 번째 캐릭터는 첫 번째 답과 다른 유의미한 관점이나 실제 의견 차이가 있을 때만 답한다.
- 단순 동의, 같은 위로의 반복, 말투만 바꾼 반복이라면 두 번째 캐릭터는 침묵한다.
- 따라서 보이는 캐릭터 발화는 기본 1회이며 필요한 예외 상황에서만 2회다.
- 요청에 포함된 캐릭터만 speaker_id로 사용한다.
- 각 발화는 한국어로 간결하게 작성한다.
- 답변을 마치면 추가 질문을 강요하지 않고 사용자에게 발화권을 돌린다.
- 출력은 요청에 포함된 JSON 구조와 값 제약을 정확히 따른다.
- 설명, 마크다운, 코드 블록 없이 JSON 객체만 출력한다.
""".strip()


def scene_plan_schema(character_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "scene_action": {
                "type": "string",
                "enum": ["CHARACTER_SEQUENCE"],
            },
            "turns": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker_id": {"type": "string", "enum": character_ids},
                        "to": {"type": "string"},
                        "emotion": {
                            "type": "string",
                            "enum": [
                                "neutral",
                                "calm",
                                "concern",
                                "happy",
                                "sad",
                                "angry",
                                "whisper",
                                "encouraging",
                                "serious",
                            ],
                        },
                        "text": {"type": "string", "minLength": 1},
                    },
                    "required": ["speaker_id", "to", "emotion", "text"],
                },
            },
            "return_turn_to": {"type": "string", "enum": ["USER"]},
            "max_internal_turns": {"type": "integer", "minimum": 0, "maximum": 2},
        },
        "required": [
            "scene_action",
            "turns",
            "return_turn_to",
            "max_internal_turns",
        ],
    }
