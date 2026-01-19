#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from _shared import project_root

DEFAULT_CONFIG_PATH = "configs/quick_set_thumbnail.json"
REQUIRED_KEYS = {
    "player1",
    "player2",
    "p1_character",
    "p2_character",
    "round",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a single set thumbnail from a config file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to the set thumbnail config JSON.",
    )
    return parser


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def load_json_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON file must be an object: {path}")
    return payload


def build_command(
    root: Path,
    script_path: Path,
    payload: dict,
) -> list[str]:
    cmd = [
        sys.executable,
        str(script_path),
        "--player1",
        payload["player1"],
        "--player2",
        payload["player2"],
        "--p1-character",
        payload["p1_character"],
        "--p2-character",
        payload["p2_character"],
        "--round",
        payload["round"],
    ]
    if payload.get("p1_color"):
        cmd.extend(["--p1-color", payload["p1_color"]])
    if payload.get("p2_color"):
        cmd.extend(["--p2-color", payload["p2_color"]])
    if payload.get("slug"):
        cmd.extend(["--slug", payload["slug"]])
    if payload.get("output_dir"):
        cmd.extend(["--output-dir", payload["output_dir"]])
    if payload.get("character_set"):
        cmd.extend(["--character-set", payload["character_set"]])
    if payload.get("character_dir"):
        cmd.extend(["--character-dir", payload["character_dir"]])
    if payload.get("base_image"):
        cmd.extend(["--base-image", payload["base_image"]])
    if payload.get("skip_export"):
        cmd.append("--skip-export")
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = project_root()
    config_path = resolve_path(root, args.config)
    if not config_path.is_file():
        print(f"error: config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        payload = load_json_file(config_path)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    missing = [key for key in sorted(REQUIRED_KEYS) if not payload.get(key)]
    if missing:
        print(
            f"error: config missing keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    script_path = root / "scripts" / "set_thumbnail.py"
    if not script_path.is_file():
        print(f"error: missing set_thumbnail script at {script_path}", file=sys.stderr)
        return 1

    cmd = build_command(root, script_path, payload)
    return subprocess.run(cmd, cwd=str(root)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
