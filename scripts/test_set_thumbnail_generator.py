#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from _shared import slugify
OUTPUT_PREFIX = "set_thumbnail_test_"
REQUIRED_KEYS = {
    "round",
    "player1",
    "player2",
    "p1_character",
    "p2_character",
}
DEFAULT_EVENT_TITLE = "Event Title #54"
DEFAULT_MAIN_CONFIG = "configs/main.json"
DEFAULT_ANCHOR_CHARACTER = "Fox"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a batch of set thumbnails from test_sets.json.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--sets",
        default=str(Path(__file__).with_name("test_sets.json")),
        help="Path to the test sets JSON file",
    )
    parser.add_argument(
        "--output-root",
        default="output",
        help="Root output directory for set_thumbnail_test_N",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit how many test sets to run",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed (overrides test_sets.json)",
    )
    return parser.parse_args()


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower().replace("&", "and"))


def resolve_character_name(characters: list[str], requested: str) -> str | None:
    target = normalize_token(requested)
    for name in characters:
        if normalize_token(name) == target:
            return name
    return None


def load_json_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON file must be an object: {path}")
    return payload


def write_json_file(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def load_main_config(root: Path) -> dict:
    path = root / DEFAULT_MAIN_CONFIG
    if not path.is_file():
        raise RuntimeError(f"main config not found: {path}")
    payload = load_json_file(path)
    current = payload.get("current_event")
    events = payload.get("events")
    if not current or not isinstance(events, list):
        raise RuntimeError("main config must include current_event and events list")
    return payload


def resolve_event_config_path(root: Path, main_config: dict) -> Path:
    current = main_config.get("current_event")
    for entry in main_config.get("events", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("id") != current:
            continue
        path = resolve_path(root, entry.get("config_path"))
        if not path.is_file():
            raise RuntimeError(f"event config not found: {path}")
        return path
    raise RuntimeError(f"current_event '{current}' not found in main config")


def update_event_text(config_path: Path, event_title: str) -> None:
    payload = load_json_file(config_path)
    text_block = payload.get("text")
    if not isinstance(text_block, dict):
        raise RuntimeError(f"event config missing text block: {config_path}")

    title_block = text_block.get("event_title")
    if not isinstance(title_block, dict):
        raise RuntimeError(f"event_title config missing in {config_path}")

    if event_title:
        title_block["text"] = event_title

    write_json_file(config_path, payload)


def next_output_dir(output_root: Path) -> Path:
    pattern = re.compile(rf"^{re.escape(OUTPUT_PREFIX)}(\d+)$")
    max_index = 0
    if output_root.is_dir():
        for entry in output_root.iterdir():
            if not entry.is_dir():
                continue
            match = pattern.match(entry.name)
            if match:
                max_index = max(max_index, int(match.group(1)))
    return output_root / f"{OUTPUT_PREFIX}{max_index + 1}"


def validate_set(payload: dict, index: int) -> bool:
    missing = sorted(key for key in REQUIRED_KEYS if key not in payload)
    if missing:
        print(
            f"error: test set #{index} missing keys: {', '.join(missing)}",
            file=sys.stderr,
        )
        return False
    return True


def available_vs_colors(character_dir: Path) -> list[str]:
    colors: set[str] = set()
    for path in character_dir.glob("*.png"):
        stem = path.stem
        if stem.endswith(" Left") or stem.endswith(" Right"):
            colors.add(stem.rsplit(" ", 1)[0])
    return sorted(colors)


def available_colors(character_dir: Path, character_set: str) -> list[str]:
    if character_set == "vs_screen":
        return available_vs_colors(character_dir)
    return sorted({path.stem for path in character_dir.glob("*.png")})


def load_character_pool(
    root: Path,
    config: dict,
) -> tuple[list[str], dict[str, list[str]], str, str]:
    character_set = config.get("character_set", "vs_screen")
    character_dir_value = config.get("character_dir", "assets/melee/characters")
    character_root = resolve_path(root, character_dir_value) / character_set
    if not character_root.is_dir():
        raise RuntimeError(f"character set directory missing: {character_root}")

    characters = config.get("characters")
    if characters is None:
        characters = sorted(
            path.name for path in character_root.iterdir() if path.is_dir()
        )
    if not characters:
        raise RuntimeError(f"no characters found in {character_root}")

    color_map: dict[str, list[str]] = {}
    for character in characters:
        character_dir = character_root / character
        if not character_dir.is_dir():
            raise RuntimeError(f"character directory missing: {character_dir}")
        colors = available_colors(character_dir, character_set)
        if not colors:
            colors = ["Default"]
        color_map[character] = colors

    return characters, color_map, character_set, character_dir_value


def choose_two(pool: list[str]) -> tuple[str, str]:
    if len(pool) >= 2:
        first, second = random.sample(pool, 2)
        return first, second
    if not pool:
        raise RuntimeError("player pool is empty")
    return pool[0], pool[0]


def build_random_sets(
    root: Path,
    config: dict,
) -> tuple[list[dict], dict]:
    rounds = config.get("rounds") or []

    if not rounds:
        raise RuntimeError("random test config missing rounds")

    characters, color_map, character_set, character_dir = load_character_pool(
        root, config
    )

    anchor_value = config.get("anchor_character", DEFAULT_ANCHOR_CHARACTER)
    anchor_character = resolve_character_name(characters, anchor_value)
    if anchor_character is None:
        raise RuntimeError(
            f"anchor character '{anchor_value}' not found in character pool"
        )

    sets: list[dict] = []
    for character in characters:
        anchor_slug = slugify(anchor_character)
        character_slug = slugify(character)
        sets.append(
            {
                "round": random.choice(rounds),
                "player1": anchor_character,
                "player2": character,
                "p1_character": anchor_character,
                "p2_character": character,
                "p1_color": random.choice(color_map[anchor_character]),
                "p2_color": random.choice(color_map[character]),
                "slug": f"left_{anchor_slug}_right_{character_slug}",
            }
        )
        sets.append(
            {
                "round": random.choice(rounds),
                "player1": character,
                "player2": anchor_character,
                "p1_character": character,
                "p2_character": anchor_character,
                "p1_color": random.choice(color_map[character]),
                "p2_color": random.choice(color_map[anchor_character]),
                "slug": f"right_{anchor_slug}_left_{character_slug}",
            }
        )

    defaults = {
        "character_set": character_set,
        "character_dir": character_dir,
    }
    return sets, defaults


def build_command(
    root: Path,
    script_path: Path,
    output_dir: Path,
    payload: dict,
    defaults: dict | None = None,
) -> list[str]:
    merged = {}
    if defaults:
        merged.update(defaults)
    merged.update(payload)
    relative_output = output_dir.relative_to(root)
    cmd = [
        sys.executable,
        str(script_path),
        "--player1",
        merged["player1"],
        "--player2",
        merged["player2"],
        "--p1-character",
        merged["p1_character"],
        "--p2-character",
        merged["p2_character"],
        "--round",
        merged["round"],
        "--output-dir",
        str(relative_output),
    ]
    if merged.get("p1_color"):
        cmd.extend(["--p1-color", merged["p1_color"]])
    if merged.get("p2_color"):
        cmd.extend(["--p2-color", merged["p2_color"]])
    if merged.get("slug"):
        cmd.extend(["--slug", merged["slug"]])
    if merged.get("character_set"):
        cmd.extend(["--character-set", merged["character_set"]])
    if merged.get("character_dir"):
        cmd.extend(["--character-dir", merged["character_dir"]])
    return cmd


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]

    sets_path = resolve_path(root, args.sets)
    if not sets_path.is_file():
        print(f"error: test sets file not found: {sets_path}", file=sys.stderr)
        return 1

    try:
        with sets_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {sets_path}: {exc}", file=sys.stderr)
        return 1

    defaults: dict | None = None
    if isinstance(payload, list):
        sets = payload[: args.limit] if args.limit else payload
    elif isinstance(payload, dict):
        seed = args.seed if args.seed is not None else payload.get("seed")
        if seed is not None:
            random.seed(seed)
            print(f"ok: using random seed {seed}")

        try:
            sets, defaults = build_random_sets(root, payload)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        print(
            "error: test sets JSON must be a list of objects or a random config object",
            file=sys.stderr,
        )
        return 1
    if args.limit:
        sets = sets[: args.limit]
    output_root = resolve_path(root, args.output_root)
    output_dir = next_output_dir(output_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    script_path = root / "scripts" / "set_thumbnail.py"
    if not script_path.is_file():
        print(f"error: missing set_thumbnail script at {script_path}", file=sys.stderr)
        return 1

    try:
        main_config = load_main_config(root)
        event_config_path = resolve_event_config_path(root, main_config)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        update_event_text(event_config_path, DEFAULT_EVENT_TITLE)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"ok: writing thumbnails to {output_dir}")

    failures = 0
    for index, entry in enumerate(sets, start=1):
        if not isinstance(entry, dict):
            print(f"error: test set #{index} must be an object", file=sys.stderr)
            failures += 1
            continue
        if not validate_set(entry, index):
            failures += 1
            continue

        cmd = build_command(root, script_path, output_dir, entry, defaults)
        result = subprocess.run(cmd, cwd=str(root))
        if result.returncode != 0:
            failures += 1
            print(f"error: test set #{index} failed", file=sys.stderr)

    if failures:
        print(f"error: {failures} test set(s) failed", file=sys.stderr)
        return 1

    print("ok: all test thumbnails generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
