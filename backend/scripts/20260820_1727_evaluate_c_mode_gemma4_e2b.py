"""Evaluate the C-mode CSV goldset with a local Gemma 4 E2B server.

This launcher keeps the normal Groq backend unchanged. It starts a second
backend process configured only for Gemma, delegates dataset conversion and
scoring to the existing evaluator, and then stops only that child process.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CSV_EVALUATOR = Path(__file__).with_name(
    "20260818_1514_evaluate_c_mode_goldset_csv.py"
)
DEFAULT_GOLDSET = (
    BACKEND_ROOT / "evals" / "20260820_153027_C_MODE_FAILED13_RETEST.csv"
)
DEFAULT_GEMMA_BASE_URL = "http://127.0.0.1:9379/v1"
DEFAULT_MODEL = "gemma4-e2b"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate C-mode with local Gemma 4 E2B"
    )
    parser.add_argument("--goldset", type=Path, default=DEFAULT_GOLDSET)
    parser.add_argument("--gemma-base-url", default=DEFAULT_GEMMA_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8001)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-model-preflight",
        action="store_true",
        help="Skip GET /v1/models for non-standard compatible servers",
    )
    return parser.parse_args()


def safe_filename_label(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-") or "unknown"


def list_model_ids(base_url: str, timeout: float) -> list[str]:
    response = httpx.get(
        f"{base_url.rstrip('/')}/models",
        timeout=min(max(timeout, 1.0), 30.0),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RuntimeError("GET /v1/models returned an unsupported response")
    model_ids = []
    for item in payload["data"]:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            model_ids.append(item["id"])
    return model_ids


def verify_model_available(base_url: str, model: str, timeout: float) -> None:
    try:
        model_ids = list_model_ids(base_url, timeout)
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot reach the Gemma model server at {base_url}: {exc}"
        ) from exc
    if model not in model_ids:
        available = ", ".join(model_ids) if model_ids else "(none)"
        raise RuntimeError(
            f"Model {model!r} is not registered. Available models: {available}"
        )


def wait_for_backend(api_origin: str, timeout: float) -> None:
    deadline = time.monotonic() + max(timeout, 1.0)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{api_origin}/openapi.json", timeout=2.0)
            if response.status_code == 200:
                return
            last_error = RuntimeError(
                f"backend returned HTTP {response.status_code}"
            )
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(
        f"Gemma backend did not start within {timeout:g} seconds: {last_error}"
    )


def build_backend_environment(args: argparse.Namespace) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "SCENE_DIRECTOR_PROVIDER": "gemma4_e2b",
            "GEMMA_BASE_URL": args.gemma_base_url.rstrip("/"),
            "GEMMA_SCENE_MODEL": args.model,
            "GEMMA_SCENE_TIMEOUT_SECONDS": str(args.timeout),
        }
    )
    return environment


def start_backend(args: argparse.Namespace) -> subprocess.Popen[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        args.backend_host,
        "--port",
        str(args.backend_port),
    ]
    creationflags = (
        subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
    return subprocess.Popen(
        command,
        cwd=BACKEND_ROOT,
        env=build_backend_environment(args),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=creationflags,
    )


def stop_backend(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def build_evaluator_command(
    args: argparse.Namespace, output: Path
) -> list[str]:
    api_url = (
        f"http://{args.backend_host}:{args.backend_port}"
        "/api/v1/conversations"
    )
    command = [
        sys.executable,
        str(CSV_EVALUATOR),
        "--goldset",
        str(args.goldset),
        "--api-url",
        api_url,
        "--output",
        str(output),
        "--timeout",
        str(args.timeout),
        "--provider-label",
        "gemma4_e2b",
        "--model-label",
        args.model,
    ]
    if args.dry_run:
        command.append("--dry-run")
    return command


def main() -> int:
    args = parse_args()
    if not args.skip_model_preflight:
        verify_model_available(args.gemma_base_url, args.model, args.timeout)

    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    model_label = safe_filename_label(args.model)
    output = args.output or (
        BACKEND_ROOT
        / "evals"
        / "runs"
        / f"{timestamp}_c_mode_gemma4_e2b_{model_label}_results.jsonl"
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    process = start_backend(args)
    api_origin = f"http://{args.backend_host}:{args.backend_port}"
    try:
        wait_for_backend(api_origin, args.startup_timeout)
        completed = subprocess.run(
            build_evaluator_command(args, output),
            cwd=BACKEND_ROOT,
            check=False,
        )
        return completed.returncode
    finally:
        stop_backend(process)


if __name__ == "__main__":
    raise SystemExit(main())
