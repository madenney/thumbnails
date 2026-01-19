#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

COMMANDS = {
    "set_thumbnail": "set_thumbnail.py",
    "lunar_thumbnail": "lunar_thumbnail.py",
    "event_thumbnail": "event_thumbnail.py",
}

ALIASES = {
    "set": "set_thumbnail",
    "lunar": "lunar_thumbnail",
    "event": "event_thumbnail",
}


def print_usage() -> None:
    print(
        "usage: python scripts/delegator.py <command> [args]\n"
        "\n"
        "commands:\n"
        "  set_thumbnail    Generate a melee set thumbnail\n"
        "  lunar_thumbnail  Generate a lunar channel thumbnail\n"
        "  event_thumbnail  Generate a full event VOD thumbnail\n"
        "\n"
        "aliases:\n"
        "  set, lunar, event"
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print_usage()
        return 0

    command = ALIASES.get(argv[0], argv[0])
    script_name = COMMANDS.get(command)
    if script_name is None:
        print(f"error: unknown command '{argv[0]}'", file=sys.stderr)
        print_usage()
        return 2

    script_path = Path(__file__).resolve().parent / script_name
    if not script_path.is_file():
        print(f"error: missing script: {script_path}", file=sys.stderr)
        return 2

    return subprocess.run([sys.executable, str(script_path), *argv[1:]]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
