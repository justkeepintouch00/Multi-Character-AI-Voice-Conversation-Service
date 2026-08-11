from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import httpx


DEFAULT_TEXT = "오늘 해야 할 일이 많아서 조금 지쳤어."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Call the local Groq Scene Director and save Typecast MP3 responses."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument(
        "--characters",
        nargs="+",
        default=["character_a", "character_b"],
        choices=["character_a", "character_b"],
    )
    return parser.parse_args()


async def response_error(response: httpx.Response, stage: str) -> RuntimeError:
    body = (await response.aread()).decode("utf-8", errors="replace")
    return RuntimeError(
        f"{stage} failed with HTTP {response.status_code}: {body[:1000]}"
    )


async def run(args: argparse.Namespace) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (
        Path(__file__).resolve().parents[1]
        / "test_outputs"
        / f"{timestamp}_groq_typecast"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    timeout = httpx.Timeout(120.0)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        scene_response = await client.post(
            "/api/v1/scene-plans",
            json={
                "user_text": args.text,
                "character_ids": args.characters,
                "recent_messages": [],
            },
        )
        if scene_response.is_error:
            raise await response_error(scene_response, "Groq Scene Director")
        scene_plan: dict[str, Any] = scene_response.json()

        scene_path = output_dir / f"{timestamp}_scene_plan.json"
        scene_path.write_text(
            json.dumps(scene_plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        audio_files: list[dict[str, Any]] = []
        for index, turn in enumerate(scene_plan["turns"], start=1):
            filename = f"{timestamp}_{index:02d}_{turn['speaker_id']}.mp3"
            audio_path = output_dir / filename
            async with client.stream(
                "POST",
                "/api/v1/tts/stream",
                json={
                    "speaker_id": turn["speaker_id"],
                    "text": turn["text"],
                    "emotion": turn["emotion"],
                    "emotion_intensity": 1.0,
                    "audio_format": "mp3",
                },
            ) as tts_response:
                if tts_response.is_error:
                    raise await response_error(
                        tts_response, f"Typecast TTS for {turn['speaker_id']}"
                    )
                with audio_path.open("wb") as audio_file:
                    async for chunk in tts_response.aiter_bytes():
                        audio_file.write(chunk)

            audio_files.append(
                {
                    "speaker_id": turn["speaker_id"],
                    "emotion": turn["emotion"],
                    "text": turn["text"],
                    "file": str(audio_path),
                    "bytes": audio_path.stat().st_size,
                }
            )

    manifest = {
        "created_at": datetime.now().astimezone().isoformat(),
        "input_text": args.text,
        "character_ids": args.characters,
        "scene_plan_file": str(scene_path),
        "audio_files": audio_files,
    }
    manifest_path = output_dir / f"{timestamp}_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return output_dir


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    output_dir = asyncio.run(run(args))
    print(f"\nSaved test artifacts to: {output_dir}")


if __name__ == "__main__":
    main()
