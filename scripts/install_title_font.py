#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

from _shared import project_root

FONT_EXTS = (".ttf", ".otf")
DEFAULT_DEST_BASE = "assets/fonts/title_font"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install a title font from a downloaded zip file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("zip_path", help="Path to the downloaded font zip.")
    parser.add_argument(
        "--font-name",
        help="Substring to pick a specific font file from the zip.",
    )
    parser.add_argument(
        "--dest",
        default=DEFAULT_DEST_BASE,
        help="Destination path for the title font (file or base path).",
    )
    parser.add_argument(
        "--delete-zip",
        action="store_true",
        help="Delete the zip file after installing.",
    )
    parser.add_argument(
        "--config",
        help="Event config JSON file to update with the installed font path.",
    )
    parser.add_argument(
        "--targets",
        help="Comma-separated text object keys to update (default: all).",
    )
    return parser


def list_font_entries(zip_file: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = []
    for info in zip_file.infolist():
        if info.is_dir():
            continue
        if Path(info.filename).suffix.lower() in FONT_EXTS:
            entries.append(info)
    return entries


def select_font(
    entries: list[zipfile.ZipInfo],
    name_hint: str | None,
) -> tuple[zipfile.ZipInfo | None, list[zipfile.ZipInfo]]:
    candidates = entries
    if name_hint:
        hint = name_hint.lower()
        candidates = [
            info
            for info in candidates
            if hint in Path(info.filename).stem.lower() or hint in info.filename.lower()
        ]
    if not candidates:
        return None, []
    if len(candidates) == 1:
        return candidates[0], candidates

    def rank(info: zipfile.ZipInfo) -> tuple[int, int, str]:
        base = Path(info.filename).stem.lower()
        score = 0
        if "regular" in base or "roman" in base:
            score += 4
        if "book" in base:
            score += 3
        if "medium" in base:
            score += 2
        if "bold" in base:
            score += 1
        if "italic" in base or "oblique" in base:
            score -= 4
        return (-score, len(base), base)

    candidates = sorted(candidates, key=rank)
    return candidates[0], candidates


def resolve_dest_path(root: Path, value: str, suffix: str) -> Path:
    dest_path = Path(value).expanduser()
    if not dest_path.is_absolute():
        dest_path = root / dest_path
    if dest_path.exists() and dest_path.is_dir():
        return dest_path / f"title_font{suffix}"
    if dest_path.suffix.lower() not in FONT_EXTS:
        return dest_path.with_suffix(suffix)
    return dest_path


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


def parse_targets(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    targets = [item.strip() for item in raw.split(",") if item.strip()]
    if not targets or targets == ["all"]:
        return None
    return targets


def resolve_config_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def update_config_fonts(
    config_path: Path,
    font_path: Path,
    targets: list[str] | None,
    root: Path,
) -> None:
    payload = load_json_file(config_path)
    text_block = payload.get("text")
    if not isinstance(text_block, dict):
        raise RuntimeError(f"event config missing text block: {config_path}")

    if targets is None:
        keys = [key for key, value in text_block.items() if isinstance(value, dict)]
    else:
        keys = targets

    try:
        font_value = str(font_path.relative_to(root))
    except ValueError:
        font_value = str(font_path)

    for key in keys:
        block = text_block.get(key)
        if not isinstance(block, dict):
            print(
                f"warning: text object '{key}' not found in {config_path}",
                file=sys.stderr,
            )
            continue
        block["font_path"] = font_value

    write_json_file(config_path, payload)
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    root = project_root()
    config_path = resolve_config_path(root, args.config)
    targets = parse_targets(args.targets)
    if args.targets and config_path is None:
        print("error: --targets requires --config", file=sys.stderr)
        return 1
    if config_path is not None and not config_path.is_file():
        print(f"error: config file not found: {config_path}", file=sys.stderr)
        return 1

    zip_path = Path(args.zip_path).expanduser()
    if not zip_path.is_absolute():
        zip_path = root / zip_path
    if not zip_path.is_file():
        print(f"error: zip file not found: {zip_path}", file=sys.stderr)
        return 1

    try:
        with zipfile.ZipFile(zip_path) as zip_file:
            entries = list_font_entries(zip_file)
            if not entries:
                print(
                    f"error: no .ttf or .otf files found in {zip_path}",
                    file=sys.stderr,
                )
                return 1
            selected, candidates = select_font(entries, args.font_name)
            if selected is None:
                available = ", ".join(Path(info.filename).name for info in entries)
                print(
                    f"error: no font files matched '{args.font_name}'. "
                    f"Available: {available}",
                    file=sys.stderr,
                )
                return 1
            if len(candidates) > 1:
                print(
                    f"warning: multiple fonts found, using {Path(selected.filename).name}",
                    file=sys.stderr,
                )

            suffix = Path(selected.filename).suffix.lower()
            dest_path = resolve_dest_path(root, args.dest, suffix)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(selected) as source, dest_path.open("wb") as target:
                shutil.copyfileobj(source, target)
            print(f"ok: installed title font to {dest_path}")
            if config_path is not None:
                update_config_fonts(config_path, dest_path, targets, root)
                print(f"ok: updated font paths in {config_path}")
    except zipfile.BadZipFile:
        print(f"error: invalid zip file: {zip_path}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.delete_zip:
        try:
            zip_path.unlink()
            print(f"ok: removed {zip_path}")
        except OSError as exc:
            print(f"warning: failed to remove {zip_path}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
