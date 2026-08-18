from collections.abc import Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import (
    get_development_user_display_name,
    get_development_user_external_id,
    get_groq_api_key,
    get_groq_base_url,
    get_groq_scene_max_attempts,
    get_groq_scene_model,
    get_groq_transcription_fallback_avg_logprob_threshold,
    get_groq_transcription_fallback_model,
    get_groq_transcription_model,
    get_typecast_api_key,
    get_typecast_base_url,
    get_typecast_tts_model,
    get_typecast_voice_map,
)
from app.db.session import SessionLocal
from app.providers.base import SceneDirectorProvider, STTProvider, TTSProvider
from app.providers.groq import GroqSceneDirector, GroqTranscriptionProvider
from app.providers.typecast import TypecastTTSProvider
from app.repositories.characters import SQLAlchemyCharacterRepository
from app.repositories.conversations import SQLAlchemyConversationRepository
from app.repositories.memory import SQLAlchemyMemoryRepository
from app.services.characters import CharacterService
from app.services.conversations import ConversationService


def get_db_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def get_scene_director_provider() -> SceneDirectorProvider:
    return GroqSceneDirector(
        api_key=get_groq_api_key(),
        base_url=get_groq_base_url(),
        model=get_groq_scene_model(),
        max_attempts=get_groq_scene_max_attempts(),
    )


def get_stt_provider() -> STTProvider:
    return GroqTranscriptionProvider(
        api_key=get_groq_api_key(),
        base_url=get_groq_base_url(),
        model=get_groq_transcription_model(),
        fallback_model=get_groq_transcription_fallback_model(),
        fallback_avg_logprob_threshold=(
            get_groq_transcription_fallback_avg_logprob_threshold()
        ),
    )


def get_tts_provider() -> TTSProvider:
    return TypecastTTSProvider(
        api_key=get_typecast_api_key(),
        base_url=get_typecast_base_url(),
        model=get_typecast_tts_model(),
        voice_map=get_typecast_voice_map(),
    )


def get_conversation_service(
    session: Annotated[Session, Depends(get_db_session)],
    scene_director: Annotated[
        SceneDirectorProvider, Depends(get_scene_director_provider)
    ],
) -> ConversationService:
    repository = SQLAlchemyConversationRepository(
        session,
        development_user_external_id=get_development_user_external_id(),
        development_user_display_name=get_development_user_display_name(),
    )
    memory_repository = SQLAlchemyMemoryRepository(session)
    return ConversationService(repository, scene_director, memory_repository)


def get_character_service(
    session: Annotated[Session, Depends(get_db_session)],
) -> CharacterService:
    repository = SQLAlchemyCharacterRepository(
        session,
        development_user_external_id=get_development_user_external_id(),
        development_user_display_name=get_development_user_display_name(),
    )
    return CharacterService(repository)
