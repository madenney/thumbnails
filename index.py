#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


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


def check_video_tools_path() -> bool:
    thumb_path = os.environ.get("VIDEO_TOOLS_THUMBNAIL_PATH", "").strip()
    if not thumb_path:
        print("warning: VIDEO_TOOLS_THUMBNAIL_PATH is not set", file=sys.stderr)
        return False
    if not Path(thumb_path).is_file():
        print(
            f"warning: VIDEO_TOOLS_THUMBNAIL_PATH does not exist: {thumb_path}",
            file=sys.stderr,
        )
        return False
    print(f"ok: VIDEO_TOOLS_THUMBNAIL_PATH exists: {thumb_path}")
    return True


def print_usage() -> None:
    print(
        "usage: python index.py <command> [args]\n"
        "\n"
        "commands:\n"
        "  set_thumbnail    Generate a melee set thumbnail\n"
        "  lunar_thumbnail  Generate a lunar channel thumbnail\n"
        "  event_thumbnail  Generate a full event VOD thumbnail\n"
        "  check_env        Validate VIDEO_TOOLS_THUMBNAIL_PATH\n"
        "\n"
        "aliases:\n"
        "  set, lunar, event\n"
        "\n"
        "notes:\n"
        "  - set_thumbnail needs player names + character names.\n"
        "  - Run without args to show this help plus env status."
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")

    if not argv:
        ok = check_video_tools_path()
        print_usage()
        return 0 if ok else 1

    if argv[0] in {"-h", "--help"}:
        ok = check_video_tools_path()
        print_usage()
        return 0 if ok else 1

    if argv[0] in {"check_env", "check"}:
        return 0 if check_video_tools_path() else 1

    if not check_video_tools_path():
        return 1

    delegator = root / "scripts" / "delegator.py"
    if not delegator.is_file():
        print(f"error: missing delegator script at {delegator}", file=sys.stderr)
        return 1

    return subprocess.run([sys.executable, str(delegator), *argv], cwd=str(root)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
