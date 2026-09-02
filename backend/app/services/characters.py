from app.repositories.characters import SQLAlchemyCharacterRepository
from app.schemas.character import CharacterListResponse, CharacterRead, CharacterWrite
from app.schemas.profile import ProfileRead, ProfileUpdate
from app.services.errors import ResourceNotFoundError


class CharacterService:
    def __init__(self, repository: SQLAlchemyCharacterRepository) -> None:
        self.repository = repository

    def get_profile(self) -> ProfileRead:
        context = self.repository.ensure_development_context()
        return ProfileRead(display_name=context.user_display_name)

    def update_profile(self, request: ProfileUpdate) -> ProfileRead:
        context = self.repository.update_display_name(request.display_name)
        return ProfileRead(display_name=context.user_display_name)

    def list_characters(self) -> CharacterListResponse:
        return CharacterListResponse(items=self.repository.list_characters())

    def get_character(self, character_id: str) -> CharacterRead:
        character = self.repository.get_character(character_id)
        if character is None:
            raise ResourceNotFoundError("캐릭터를 찾을 수 없습니다.")
        return character

    def create_character(self, request: CharacterWrite) -> CharacterRead:
        return self.repository.create_character(request)

    def update_character(
        self, character_id: str, request: CharacterWrite
    ) -> CharacterRead:
        character = self.repository.update_character(character_id, request)
        if character is None:
            raise ResourceNotFoundError("캐릭터를 찾을 수 없습니다.")
        return character
    def upload_portrait(
        self, character_id: str, *, content: bytes, mime_type: str
    ) -> CharacterRead:
        character = self.repository.upload_portrait(
            character_id, content=content, mime_type=mime_type
        )
        if character is None:
            raise ResourceNotFoundError("캐릭터를 찾을 수 없습니다.")
        return character
