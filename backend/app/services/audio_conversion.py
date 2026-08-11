from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


class AudioConversionError(RuntimeError):
    """Raised when a development audio recording cannot be converted."""


def convert_audio_to_mp3(content: bytes, input_suffix: str) -> bytes:
    """Convert browser audio bytes to a real MP3 file with bundled FFmpeg."""

    from imageio_ffmpeg import get_ffmpeg_exe

    with TemporaryDirectory(prefix="character-companion-audio-") as directory:
        temp_directory = Path(directory)
        input_path = temp_directory / f"input{input_suffix}"
        output_path = temp_directory / "recording.mp3"
        input_path.write_bytes(content)

        command = [
            get_ffmpeg_exe(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_path),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AudioConversionError("FFmpeg 실행에 실패했습니다.") from exc

        if result.returncode != 0 or not output_path.exists():
            raise AudioConversionError("지원하지 않거나 손상된 오디오 파일입니다.")

        mp3_content = output_path.read_bytes()
        if not mp3_content:
            raise AudioConversionError("MP3 변환 결과가 비어 있습니다.")
        return mp3_content
