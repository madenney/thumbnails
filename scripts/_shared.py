#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    # Minimal .env parser to avoid external deps.
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


def require_video_tools_path() -> Path:
    thumb_path = os.environ.get("VIDEO_TOOLS_THUMBNAIL_PATH", "").strip()
    if not thumb_path:
        raise RuntimeError("VIDEO_TOOLS_THUMBNAIL_PATH is not set")
    path = Path(thumb_path)
    if not path.is_file():
        raise RuntimeError(f"VIDEO_TOOLS_THUMBNAIL_PATH does not exist: {path}")
    return path


def run_video_tools(path: Path, extra_args: Iterable[str], cwd: Path) -> int:
    cmd = [str(path)]
    if not os.access(path, os.X_OK):
        cmd = [sys.executable, str(path)]
    cmd.append("-e")
    cmd.extend(extra_args)
    result = subprocess.run(cmd, cwd=str(cwd))
    return result.returncode


def parse_video_tools_args(unknown_args: list[str]) -> list[str]:
    if unknown_args and unknown_args[0] == "--":
        return unknown_args[1:]
    return unknown_args


def slugify(text: str) -> str:
    normalized = text.strip().lower()
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return normalized or "thumbnail"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_metadata(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
