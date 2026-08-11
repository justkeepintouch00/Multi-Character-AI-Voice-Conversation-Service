from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv


# A local .env keeps development credentials available across terminal sessions.
# Explicit process environment variables take precedence over .env values.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE_PATH = BACKEND_ROOT / ".env"
load_dotenv(dotenv_path=ENV_FILE_PATH, override=False)


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/character_companion"
)


def get_database_url() -> str:
    """Return the configured SQLAlchemy database URL."""

    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_cors_origins() -> list[str]:
    raw_value = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def get_development_user_external_id() -> str:
    return os.getenv("DEV_USER_EXTERNAL_ID", "local-development-user")


def get_development_user_display_name() -> str:
    return os.getenv("DEV_USER_DISPLAY_NAME", "개발 사용자")


def get_groq_api_key() -> str | None:
    value = os.getenv("GROQ_API_KEY", "").strip()
    return value or None


def get_groq_base_url() -> str:
    return os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")


def get_groq_scene_model() -> str:
    return os.getenv("GROQ_SCENE_MODEL", "openai/gpt-oss-120b")


def get_groq_scene_max_attempts() -> int:
    raw_value = os.getenv("GROQ_SCENE_MAX_ATTEMPTS", "2")
    try:
        value = int(raw_value)
    except ValueError:
        return 2
    return min(max(value, 1), 3)


def get_groq_transcription_model() -> str:
    return os.getenv("GROQ_TRANSCRIPTION_MODEL", "whisper-large-v3-turbo")


def get_typecast_api_key() -> str | None:
    value = os.getenv("TYPECAST_API_KEY", "").strip()
    return value or None


def get_typecast_base_url() -> str:
    return os.getenv("TYPECAST_BASE_URL", "https://api.typecast.ai").rstrip("/")


def get_typecast_tts_model() -> str:
    return os.getenv("TYPECAST_TTS_MODEL", "ssfm-v30")


def get_typecast_voice_map() -> dict[str, str]:
    raw_value = os.getenv("TYPECAST_VOICE_MAP", "{}")
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}
    return {
        str(speaker_id): str(voice_id)
        for speaker_id, voice_id in parsed.items()
        if isinstance(speaker_id, str) and isinstance(voice_id, str)
    }
