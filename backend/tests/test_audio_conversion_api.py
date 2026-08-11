from fastapi.testclient import TestClient

from app.api.routes import audio
from app.main import app


client = TestClient(app)


def test_convert_recording_to_mp3(monkeypatch) -> None:
    def fake_convert(content: bytes, input_suffix: str) -> bytes:
        assert content == b"browser-audio"
        assert input_suffix == ".webm"
        return b"ID3fake-mp3"

    monkeypatch.setattr(audio, "convert_audio_to_mp3", fake_convert)

    response = client.post(
        "/api/v1/audio/convert/mp3",
        files={"file": ("recording.webm", b"browser-audio", "audio/webm")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3fake-mp3"


def test_convert_recording_rejects_non_audio_file() -> None:
    response = client.post(
        "/api/v1/audio/convert/mp3",
        files={"file": ("notes.txt", b"not-audio", "text/plain")},
    )

    assert response.status_code == 415
