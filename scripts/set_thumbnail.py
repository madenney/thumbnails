#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
except ImportError:  # pragma: no cover - handled at runtime
    Image = None
    ImageChops = None
    ImageDraw = None
    ImageFilter = None
    ImageFont = None

from _shared import (
    load_dotenv,
    project_root,
    require_video_tools_path,
    run_video_tools,
    slugify,
)

BASE_WIDTH = 1920
BASE_HEIGHT = 1080
BASE_BORDER = 50
BASE_MARGIN_X = 80
BASE_MARGIN_Y = 60
BASE_NAME_FONT_SIZE = 220
BASE_NAME_CENTER_GAP = 160
BASE_LINE_SPACING = 10
BASE_TEXT_STROKE_WIDTH = 8
MAX_NAME_LINES = 1
MAX_UPSCALE = 1.6
RIGHT_SIDE_HEIGHT_RATIO = 0.9
DEFAULT_BASE_IMAGE = "assets/test6.jpg"
DEFAULT_MAIN_CONFIG = "configs/main.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a melee set thumbnail using video_tools.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--player1", required=True, help="Left-side player name")
    parser.add_argument("--player2", required=True, help="Right-side player name")
    parser.add_argument("--p1-character", required=True, help="Player 1 character name")
    parser.add_argument("--p2-character", required=True, help="Player 2 character name")
    parser.add_argument("--p1-color", default="Default", help="Player 1 character color")
    parser.add_argument("--p2-color", default="Default", help="Player 2 character color")
    parser.add_argument("--round", required=True, help="Round title")
    parser.add_argument(
        "--output-dir",
        default="output/set_thumbnail",
        help="Directory to write metadata JSON",
    )
    parser.add_argument("--slug", help="Override output file slug")
    parser.add_argument(
        "--character-dir",
        default="assets/melee/characters",
        help="Base character asset directory",
    )
    parser.add_argument(
        "--character-set",
        default="vs_screen",
        choices=("vs_screen", "portraits", "stock_icons"),
        help="Character art set to use",
    )
    parser.add_argument(
        "--base-image",
        default=DEFAULT_BASE_IMAGE,
        help="Use an existing base image instead of generating one",
    )
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip calling video_tools/thumbnail -e",
    )
    return parser


def scale_value(value: int, scale: float) -> int:
    return int(round(value * scale))


def resolve_path(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower().replace("&", "and"))


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    left, top, right, bottom = draw.textbbox((0, 0), text=text, font=font)
    return right - left


def line_height(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> int:
    left, top, right, bottom = draw.textbbox((0, 0), text="Ag", font=font)
    return bottom - top


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str] | None:
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]
    if text_width(draw, current, font) > max_width:
        return None

    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue

        lines.append(current)
        current = word
        if text_width(draw, current, font) > max_width:
            return None
        if len(lines) >= max_lines:
            return None

    lines.append(current)
    if len(lines) > max_lines:
        return None

    return lines


def truncate_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> str:
    if text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "..."
    trimmed = text
    while trimmed and text_width(draw, f"{trimmed}{ellipsis}", font) > max_width:
        trimmed = trimmed[:-1].rstrip()
    return f"{trimmed}{ellipsis}" if trimmed else text


def fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: Path,
    max_size: int,
    min_size: int,
    max_width: int,
    max_lines: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(max_size, min_size - 1, -2):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap_text(draw, text, font, max_width, max_lines)
        if lines is not None:
            return font, lines

    font = ImageFont.truetype(str(font_path), min_size)
    lines = wrap_text(draw, text, font, max_width, max_lines)
    if lines is None:
        lines = [truncate_text(draw, text, font, max_width)]
    return font, lines


def draw_text_with_stroke(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    stroke_fill: str,
    stroke_width: int,
) -> None:
    try:
        draw.text(
            position,
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        return
    except (TypeError, OSError):
        pass

    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx == 0 and dy == 0:
                continue
            draw.text(
                (position[0] + dx, position[1] + dy),
                text,
                font=font,
                fill=stroke_fill,
            )
    draw.text(position, text, font=font, fill=fill)


def resolve_character_dir(character_root: Path, character: str) -> Path:
    candidate = character_root / character
    if candidate.is_dir():
        return candidate

    target = normalize_token(character)
    for path in character_root.iterdir():
        if path.is_dir() and normalize_token(path.name) == target:
            return path

    available = ", ".join(sorted(path.name for path in character_root.iterdir() if path.is_dir()))
    raise RuntimeError(f"Unknown character '{character}'. Available: {available}")


def find_image_file(character_dir: Path, stem: str) -> Path | None:
    direct = character_dir / f"{stem}.png"
    if direct.is_file():
        return direct
    target = normalize_token(stem)
    for path in character_dir.glob("*.png"):
        if normalize_token(path.stem) == target:
            return path
    return None


def available_vs_colors(character_dir: Path) -> list[str]:
    colors: set[str] = set()
    for path in character_dir.glob("*.png"):
        stem = path.stem
        if stem.endswith(" Left") or stem.endswith(" Right"):
            colors.add(stem.rsplit(" ", 1)[0])
    return sorted(colors)


def crop_transparent(image: Image.Image) -> Image.Image:
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    alpha = image.split()[-1]
    bbox = alpha.getbbox()
    return image.crop(bbox) if bbox else image


def scale_to_fit(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    if max_width <= 0 or max_height <= 0:
        return image
    scale = min(max_width / image.width, max_height / image.height)
    scale = min(scale, MAX_UPSCALE)
    if scale == 1:
        return image
    size = (max(1, int(round(image.width * scale))), max(1, int(round(image.height * scale))))
    return image.resize(size, Image.LANCZOS)


def apply_character_outline(image: Image.Image, outline_px: int, color: str) -> Image.Image:
    if outline_px <= 0 or ImageFilter is None:
        return image
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    pad = outline_px
    padded = Image.new(
        "RGBA",
        (image.width + pad * 2, image.height + pad * 2),
        (0, 0, 0, 0),
    )
    padded.paste(image, (pad, pad), image)
    alpha = padded.split()[-1]
    filter_size = max(3, pad * 2 + 1)
    expanded = alpha.filter(ImageFilter.MaxFilter(filter_size))
    if ImageChops is not None:
        outline_mask = ImageChops.subtract(expanded, alpha)
    else:
        outline_mask = expanded
    outline = Image.new("RGBA", padded.size, color)
    outline.putalpha(outline_mask)
    return Image.alpha_composite(outline, padded)


def parse_character_outline_config(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {"enabled": False, "size": 0, "color": "#000000"}
    enabled = bool(payload.get("enabled", False))
    try:
        size = int(payload.get("size", 0))
    except (TypeError, ValueError):
        size = 0
    if size < 0:
        size = 0
    color_value = payload.get("color", "#000000")
    color = color_value if isinstance(color_value, str) else "#000000"
    return {"enabled": enabled, "size": size, "color": color}


def parse_override_block(block: dict | None, allow_missing: bool = False) -> dict:
    if not isinstance(block, dict):
        return {} if allow_missing else {"scale": 1.0, "offset_x": 0, "offset_y": 0}
    result: dict[str, float | int] = {}
    for key, default_value, caster in (
        ("scale", 1.0, float),
        ("offset_x", 0, int),
        ("offset_y", 0, int),
    ):
        if allow_missing and key not in block:
            continue
        result[key] = caster(block.get(key, default_value))
    return result


def merge_overrides(base: dict, extra: dict) -> dict:
    merged = dict(base)
    for key in ("scale", "offset_x", "offset_y"):
        if key in extra:
            merged[key] = extra[key]
    return merged


def apply_center_offset(offset_x: int, side: str) -> int:
    # Positive values move away from center; right side keeps sign, left flips.
    return offset_x if side.lower() == "right" else -offset_x


def load_json_file(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON file must be an object: {path}")
    return payload


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


def resolve_event_config(root: Path, main_config: dict) -> tuple[Path, dict]:
    current = main_config.get("current_event")
    for entry in main_config.get("events", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("id") != current:
            continue
        config_path = resolve_path(root, entry.get("config_path"))
        if config_path is None:
            raise RuntimeError(f"event config path missing for event '{current}'")
        if not config_path.is_file():
            raise RuntimeError(f"event config not found: {config_path}")
        return config_path, load_json_file(config_path)
    raise RuntimeError(f"current_event '{current}' not found in main config")


def load_character_overrides_data(payload: dict | None) -> dict:
    defaults = {"scale": 1.0, "offset_x": 0, "offset_y": 0}
    overrides = {"defaults": defaults, "characters": {}}
    if payload is None:
        return overrides
    if not isinstance(payload, dict):
        raise RuntimeError("character overrides must be an object")

    overrides["defaults"] = parse_override_block(payload.get("defaults"))
    for name, block in (payload.get("characters") or {}).items():
        if not isinstance(block, dict):
            continue
        entry = {
            "base": parse_override_block(block),
            "left": parse_override_block(block.get("left"), allow_missing=True),
            "right": parse_override_block(block.get("right"), allow_missing=True),
        }
        overrides["characters"][normalize_token(name)] = entry
    return overrides


def load_character_overrides(path: Path | None) -> dict:
    if path is None:
        return load_character_overrides_data(None)
    if not path.is_file():
        print(f"warning: character overrides file not found: {path}", file=sys.stderr)
        return load_character_overrides_data(None)
    payload = load_json_file(path)
    return load_character_overrides_data(payload)


def resolve_character_override(overrides: dict, character: str, side: str) -> dict:
    merged = dict(overrides["defaults"])
    entry = overrides["characters"].get(normalize_token(character))
    if not entry:
        merged["offset_x"] = apply_center_offset(int(merged.get("offset_x", 0)), side)
        return merged

    merged = merge_overrides(merged, entry.get("base", {}))
    offset_x = int(merged.get("offset_x", 0))
    if side.lower() == "left":
        side_block = entry.get("left", {})
    else:
        side_block = entry.get("right", {})
    merged = merge_overrides(merged, side_block)
    if "offset_x" in side_block:
        offset_x = int(merged.get("offset_x", 0))
    else:
        offset_x = apply_center_offset(offset_x, side)
    merged["offset_x"] = offset_x
    return merged


def apply_character_override(
    image: Image.Image,
    override: dict,
    scale_x: float,
    scale_y: float,
) -> tuple[Image.Image, int, int]:
    scale = float(override.get("scale", 1.0))
    offset_x = scale_value(int(override.get("offset_x", 0)), scale_x)
    offset_y = scale_value(int(override.get("offset_y", 0)), scale_y)
    if scale != 1.0:
        new_size = (
            max(1, int(round(image.width * scale))),
            max(1, int(round(image.height * scale))),
        )
        image = image.resize(new_size, Image.LANCZOS)
    return image, offset_x, offset_y


def scaled_height_for_path(path: Path, max_width: int, max_height: int) -> float:
    image = Image.open(path).convert("RGBA")
    image = crop_transparent(image)
    scale = min(max_width / image.width, max_height / image.height)
    scale = min(scale, MAX_UPSCALE)
    return image.height * scale


def resolve_character_image(
    character_root: Path,
    character: str,
    color: str,
    side: str,
    character_set: str,
    max_width: int | None = None,
    max_height: int | None = None,
) -> tuple[Path, bool, str]:
    character_dir = resolve_character_dir(character_root, character)
    requested = color
    candidates = [color]
    if normalize_token(color) != "default":
        candidates.append("Default")

    if character_set == "vs_screen":
        if side == "Right" and normalize_token(character) == "roy":
            for candidate in candidates:
                left_path = find_image_file(character_dir, f"{candidate} Left")
                if left_path:
                    if normalize_token(candidate) != normalize_token(requested):
                        print(
                            f"warning: {character} {side} color '{requested}' not found, using '{candidate}'",
                            file=sys.stderr,
                        )
                    print(
                        "warning: Roy right side forced to mirrored left asset",
                        file=sys.stderr,
                    )
                    return left_path, True, candidate

        for candidate in candidates:
            if side == "Left":
                path = find_image_file(character_dir, f"{candidate} Left")
                if path:
                    if normalize_token(candidate) != normalize_token(requested):
                        print(
                            f"warning: {character} {side} color '{requested}' not found, using '{candidate}'",
                            file=sys.stderr,
                        )
                    return path, False, candidate
                continue

            right_path = find_image_file(character_dir, f"{candidate} Right")
            left_path = find_image_file(character_dir, f"{candidate} Left")
            if right_path and left_path and max_width and max_height:
                right_height = scaled_height_for_path(right_path, max_width, max_height)
                left_height = scaled_height_for_path(left_path, max_width, max_height)
                if right_height < left_height * RIGHT_SIDE_HEIGHT_RATIO:
                    if normalize_token(candidate) != normalize_token(requested):
                        print(
                            f"warning: {character} {side} color '{requested}' not found, using '{candidate}'",
                            file=sys.stderr,
                        )
                    print(
                        f"warning: {character} {side} asset is smaller than left, using left mirrored",
                        file=sys.stderr,
                    )
                    return left_path, True, candidate

            if right_path:
                if normalize_token(candidate) != normalize_token(requested):
                    print(
                        f"warning: {character} {side} color '{requested}' not found, using '{candidate}'",
                        file=sys.stderr,
                    )
                return right_path, False, candidate
            if left_path:
                if normalize_token(candidate) != normalize_token(requested):
                    print(
                        f"warning: {character} {side} color '{requested}' not found, using '{candidate}'",
                        file=sys.stderr,
                    )
                return left_path, True, candidate

        available = ", ".join(available_vs_colors(character_dir))
        raise RuntimeError(
            f"Missing image for {character} ({color} {side}) in {character_dir}. "
            f"Available colors: {available}"
        )

    for candidate in candidates:
        path = find_image_file(character_dir, candidate)
        if path:
            if normalize_token(candidate) != normalize_token(requested):
                print(
                    f"warning: {character} color '{requested}' not found, using '{candidate}'",
                    file=sys.stderr,
                )
            return path, False, candidate
    available = ", ".join(sorted(path.stem for path in character_dir.glob("*.png")))
    raise RuntimeError(
        f"Missing image for {character} ({color}) in {character_dir}. "
        f"Available colors: {available}"
    )


def load_character_image(path: Path, mirror: bool) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    if mirror:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    return image


def resolve_font_path(video_tools_path: Path) -> Path:
    path = video_tools_path.parent / "assets" / "cour_bold.ttf"
    if not path.is_file():
        raise RuntimeError(f"Font file does not exist: {path}")
    return path


def resolve_config_font_path(root: Path, value: str | None, name: str) -> Path:
    path = resolve_path(root, value)
    if path is None or not path.is_file():
        raise RuntimeError(f"{name} font file does not exist: {path}")
    return path


def int_or_default(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_text_block_enabled(block: dict | None) -> bool:
    if not isinstance(block, dict):
        return False
    enabled = block.get("enabled")
    return True if enabled is None else bool(enabled)


def text_block_text(block: dict | None) -> str:
    if not is_text_block_enabled(block):
        return ""
    return str(block.get("text", "")).strip()


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    root: Path,
    name: str,
    block: dict | None,
    scale_x: float,
    scale_y: float,
    default_line_spacing: int,
    default_stroke_width: int,
    stack_y: int | None,
    text_override: str | None = None,
) -> int | None:
    if not is_text_block_enabled(block):
        return stack_y
    text = (
        str(text_override).strip()
        if text_override is not None
        else str(block.get("text", "")).strip()
    )
    segments = block.get("segments")
    text_source = text
    event_number_token = ""
    if text_source:
        matches = re.findall(r"#\S+", text_source)
        if matches:
            event_number_token = matches[-1]
    if isinstance(segments, list) and segments:
        max_size_base = int_or_default(block.get("max_size"), 0)
        min_size_base = int_or_default(block.get("min_size"), max_size_base)
        if max_size_base <= 0:
            raise RuntimeError(f"{name} max_size must be a positive integer")
        max_size = scale_value(max_size_base, scale_y)
        min_size = scale_value(min_size_base, scale_y)

        max_width_base = int_or_default(block.get("max_width"), BASE_WIDTH)
        if max_width_base <= 0:
            max_width_base = BASE_WIDTH
        max_width = scale_value(max_width_base, scale_x)

        align = str(block.get("align", "left")).lower()
        anchor = str(block.get("anchor", "top")).lower()
        fill = str(block.get("fill", "white"))
        stroke_fill = str(block.get("stroke_fill", "black"))
        stroke_width_base = int_or_default(block.get("stroke_width"), default_stroke_width)
        line_spacing_base = int_or_default(block.get("line_spacing"), default_line_spacing)
        stroke_width = max(1, scale_value(stroke_width_base, scale_y))
        _ = scale_value(line_spacing_base, scale_y)

        x = scale_value(int_or_default(block.get("x"), 0), scale_x)
        y = scale_value(int_or_default(block.get("y"), 0), scale_y)
        if block.get("stack") and stack_y is not None:
            gap = scale_value(int_or_default(block.get("stack_gap"), 0), scale_y)
            y = stack_y + gap

        base_font_path = resolve_config_font_path(root, block.get("font_path"), name)

        def build_segments(
            base_size: int,
        ) -> tuple[int, int, int, list[tuple[str, ImageFont.FreeTypeFont, int, int]]]:
            total_width = 0
            max_ascent = 0
            max_descent = 0
            built: list[tuple[str, ImageFont.FreeTypeFont, int, int]] = []
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                seg_text = str(segment.get("text", ""))
                if event_number_token:
                    seg_text = seg_text.replace("{event_number}", event_number_token)
                if not seg_text:
                    continue
                seg_scale = float(segment.get("size_scale", 1.0))
                seg_adjust_base = segment.get("x_adjust")
                seg_font_path_value = segment.get("font_path")
                if seg_font_path_value:
                    seg_font_path = resolve_config_font_path(root, seg_font_path_value, name)
                else:
                    seg_font_path = base_font_path
                seg_size = max(1, int(round(base_size * seg_scale)))
                seg_font = ImageFont.truetype(str(seg_font_path), seg_size)
                seg_width = text_width(draw, seg_text, seg_font)
                seg_adjust = scale_value(int_or_default(seg_adjust_base, 0), scale_x)
                total_width += seg_width + seg_adjust
                ascent, descent = seg_font.getmetrics()
                max_ascent = max(max_ascent, ascent)
                max_descent = max(max_descent, descent)
                built.append((seg_text, seg_font, seg_width, seg_adjust))
            return total_width, max_ascent, max_descent, built

        chosen = None
        for size in range(max_size, min_size - 1, -2):
            total_width, max_ascent, max_descent, built = build_segments(size)
            if not built:
                return stack_y
            if max_width <= 0 or total_width <= max_width:
                chosen = (total_width, max_ascent, max_descent, built)
                break

        if chosen is None:
            total_width, max_ascent, max_descent, built = build_segments(min_size)
        else:
            total_width, max_ascent, max_descent, built = chosen

        total_height = max_ascent + max_descent
        if anchor == "center":
            start_y = y - (total_height // 2)
        elif anchor == "bottom":
            start_y = y - total_height
        else:
            start_y = y

        if align == "center":
            start_x = x - (total_width // 2)
        elif align == "right":
            start_x = x - total_width
        else:
            start_x = x

        baseline_y = start_y + max_ascent
        current_x = start_x
        for seg_text, seg_font, seg_width, seg_adjust in built:
            ascent, _ = seg_font.getmetrics()
            seg_y = baseline_y - ascent
            draw_text_with_stroke(
                draw,
                (current_x, seg_y),
                seg_text,
                seg_font,
                fill,
                stroke_fill,
                stroke_width,
            )
            current_x += seg_width + seg_adjust
        return start_y + total_height

    if not text:
        return stack_y

    font_path = resolve_config_font_path(root, block.get("font_path"), name)
    max_size_base = int_or_default(block.get("max_size"), 0)
    min_size_base = int_or_default(block.get("min_size"), max_size_base)
    if max_size_base <= 0:
        raise RuntimeError(f"{name} max_size must be a positive integer")
    max_size = scale_value(max_size_base, scale_y)
    min_size = scale_value(min_size_base, scale_y)

    max_width_base = int_or_default(block.get("max_width"), BASE_WIDTH)
    if max_width_base <= 0:
        max_width_base = BASE_WIDTH
    max_width = scale_value(max_width_base, scale_x)
    max_lines = int_or_default(block.get("max_lines"), 1)

    align = str(block.get("align", "left")).lower()
    anchor = str(block.get("anchor", "top")).lower()
    fill = str(block.get("fill", "white"))
    stroke_fill = str(block.get("stroke_fill", "black"))
    stroke_width_base = int_or_default(block.get("stroke_width"), default_stroke_width)
    line_spacing_base = int_or_default(block.get("line_spacing"), default_line_spacing)
    stroke_width = max(1, scale_value(stroke_width_base, scale_y))
    line_spacing = scale_value(line_spacing_base, scale_y)

    x = scale_value(int_or_default(block.get("x"), 0), scale_x)
    y = scale_value(int_or_default(block.get("y"), 0), scale_y)
    if block.get("stack") and stack_y is not None:
        gap = scale_value(int_or_default(block.get("stack_gap"), 0), scale_y)
        y = stack_y + gap

    font, lines = fit_text(
        draw,
        text,
        font_path,
        max_size,
        min_size,
        max_width,
        max_lines,
    )

    line_height_px = line_height(draw, font)
    total_height = line_height_px * len(lines) + line_spacing * max(0, len(lines) - 1)
    if anchor == "center":
        start_y = y - (total_height // 2)
    elif anchor == "bottom":
        start_y = y - total_height
    else:
        start_y = y

    current_y = start_y
    for line in lines:
        line_width = text_width(draw, line, font)
        if align == "center":
            line_x = x - (line_width // 2)
        elif align == "right":
            line_x = x - line_width
        else:
            line_x = x
        draw_text_with_stroke(
            draw,
            (line_x, current_y),
            line,
            font,
            fill,
            stroke_fill,
            stroke_width,
        )
        current_y += line_height_px + line_spacing

    return start_y + total_height


def text_block_height(
    draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, line_count: int, line_spacing: int
) -> int:
    if line_count <= 0:
        return 0
    return line_height(draw, font) * line_count + line_spacing * max(0, line_count - 1)


def draw_player_names(
    draw: ImageDraw.ImageDraw,
    root: Path,
    block: dict | None,
    left_text: str,
    right_text: str,
    scale_x: float,
    scale_y: float,
    width: int,
    default_line_spacing: int,
    default_stroke_width: int,
) -> None:
    if not is_text_block_enabled(block):
        return

    left_text = left_text.strip()
    right_text = right_text.strip()
    if not left_text and not right_text:
        return

    font_path = resolve_config_font_path(root, block.get("font_path"), "player_names")
    max_size_base = int_or_default(block.get("max_size"), BASE_NAME_FONT_SIZE)
    min_size_base = int_or_default(block.get("min_size"), 28)
    max_lines = int_or_default(block.get("max_lines"), MAX_NAME_LINES)

    align = str(block.get("align", "edge")).lower()
    x_padding_base = int_or_default(block.get("x_padding"), BASE_BORDER + BASE_MARGIN_X)
    center_gap_base = int_or_default(block.get("center_gap"), BASE_NAME_CENTER_GAP)
    y_base = int_or_default(block.get("y"), BASE_MARGIN_Y)

    max_width_base = block.get("max_width")
    if max_width_base is None:
        max_width_base = 0
    max_width_value = int_or_default(max_width_base, 0)

    stroke_width_base = int_or_default(block.get("stroke_width"), default_stroke_width)
    line_spacing_base = int_or_default(block.get("line_spacing"), default_line_spacing)

    max_size = scale_value(max_size_base, scale_y)
    min_size = scale_value(min_size_base, scale_y)
    stroke_width = max(1, scale_value(stroke_width_base, scale_y))
    line_spacing = scale_value(line_spacing_base, scale_y)

    x_padding = scale_value(x_padding_base, scale_x)
    center_gap = scale_value(center_gap_base, scale_x)
    y = scale_value(y_base, scale_y)

    if max_width_value > 0:
        name_max_width = scale_value(max_width_value, scale_x)
    else:
        name_max_width = int(max(1, round((width / 2) - center_gap - x_padding)))

    left_font, left_lines = fit_text(
        draw,
        left_text,
        font_path,
        max_size,
        min_size,
        name_max_width,
        max_lines,
    )
    right_font, right_lines = fit_text(
        draw,
        right_text,
        font_path,
        max_size,
        min_size,
        name_max_width,
        max_lines,
    )

    left_height = text_block_height(draw, left_font, len(left_lines), line_spacing)
    right_height = text_block_height(draw, right_font, len(right_lines), line_spacing)
    max_height = max(left_height, right_height)

    left_y = y + (max_height - left_height) // 2
    right_y = y + (max_height - right_height) // 2
    fill = str(block.get("fill", "white"))
    stroke_fill = str(block.get("stroke_fill", "black"))

    if align == "center":
        left_center = x_padding + ((width / 2) - center_gap - x_padding) / 2
        right_center = (width / 2) + center_gap + ((width / 2) - center_gap - x_padding) / 2

        current_y = left_y
        for line in left_lines:
            line_width = text_width(draw, line, left_font)
            draw_text_with_stroke(
                draw,
                (int(round(left_center - (line_width / 2))), current_y),
                line,
                left_font,
                fill,
                stroke_fill,
                stroke_width,
            )
            current_y += line_height(draw, left_font) + line_spacing

        current_y = right_y
        for line in right_lines:
            line_width = text_width(draw, line, right_font)
            draw_text_with_stroke(
                draw,
                (int(round(right_center - (line_width / 2))), current_y),
                line,
                right_font,
                fill,
                stroke_fill,
                stroke_width,
            )
            current_y += line_height(draw, right_font) + line_spacing
    else:
        left_x = x_padding
        current_y = left_y
        for line in left_lines:
            draw_text_with_stroke(
                draw,
                (left_x, current_y),
                line,
                left_font,
                fill,
                stroke_fill,
                stroke_width,
            )
            current_y += line_height(draw, left_font) + line_spacing

        right_x = width - x_padding
        current_y = right_y
        for line in right_lines:
            line_width = text_width(draw, line, right_font)
            draw_text_with_stroke(
                draw,
                (right_x - line_width, current_y),
                line,
                right_font,
                fill,
                stroke_fill,
                stroke_width,
            )
            current_y += line_height(draw, right_font) + line_spacing


def main(argv: list[str] | None = None) -> int:
    if Image is None or ImageDraw is None or ImageFont is None:
        print("error: Pillow is required (pip install pillow)", file=sys.stderr)
        return 1

    parser = build_parser()
    args = parser.parse_args(argv)

    root = project_root()
    load_dotenv(root / ".env")

    try:
        video_tools_path = require_video_tools_path()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        main_config = load_main_config(root)
        event_config_path, event_config = resolve_event_config(root, main_config)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    text_config = event_config.get("text")
    if not isinstance(text_config, dict):
        print(f"error: event config missing text block: {event_config_path}", file=sys.stderr)
        return 1

    event_title_block = text_config.get("event_title")
    event_number_block = text_config.get("event_number")
    round_block = text_config.get("round_title")

    round_arg = args.round.strip()
    if round_arg:
        if not isinstance(round_block, dict):
            print(
                f"error: round_title config missing for event: {event_config_path}",
                file=sys.stderr,
            )
            return 1
        if is_text_block_enabled(round_block):
            round_block["text"] = round_arg
        else:
            print(
                "warning: round_title disabled in config; ignoring --round",
                file=sys.stderr,
            )

    event_title_text = text_block_text(event_title_block)
    event_number_text = text_block_text(event_number_block)
    round_title_text = text_block_text(round_block)
    slug_parts = [args.player1, "vs", args.player2]
    for part in (round_title_text, event_title_text, event_number_text):
        if part:
            slug_parts.append(part)
    slug = args.slug or slugify(" ".join(slug_parts))
    output_dir = root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug}.png"

    metadata_path = output_dir / f"{slug}.json"
    base_image_value = event_config.get("base_image") or args.base_image
    base_image_path = resolve_path(root, base_image_value)
    export_ran = False
    # Video tools export is disabled for now; keep the flow commented for later.
    # video_tools_output_path = video_tools_path.parent / "output" / "thumbnail.png"
    # if base_image_path is None:
    #     if args.skip_export:
    #         print(
    #             "error: --skip-export requires --base-image when no base exists",
    #             file=sys.stderr,
    #         )
    #         return 1
    #     export_ran = True
    #     exit_code = run_video_tools(video_tools_path, [], root)
    #     if exit_code != 0:
    #         return exit_code
    #     if not video_tools_output_path.is_file():
    #         print(
    #             f"error: video_tools output not found: {video_tools_output_path}",
    #             file=sys.stderr,
    #         )
    #         return 1
    #     base_image_path = video_tools_output_path
    if base_image_path is None:
        print("error: base image path could not be resolved", file=sys.stderr)
        return 1

    if not base_image_path.is_file():
        print(f"error: base image not found: {base_image_path}", file=sys.stderr)
        return 1

    try:
        font_path = resolve_font_path(video_tools_path)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if "character_overrides" in event_config:
            overrides = load_character_overrides_data(event_config.get("character_overrides"))
        elif event_config.get("character_overrides_path"):
            overrides_path = resolve_path(root, event_config.get("character_overrides_path"))
            overrides = load_character_overrides(overrides_path)
        else:
            overrides = load_character_overrides(None)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    outline_config = parse_character_outline_config(event_config.get("character_outline"))
    base_image = Image.open(base_image_path).convert("RGBA")
    width, height = base_image.size
    scale_x = width / BASE_WIDTH
    scale_y = height / BASE_HEIGHT
    outline_px = 0
    if outline_config["enabled"]:
        outline_px = max(0, scale_value(outline_config["size"], scale_y))
    outline_color = outline_config["color"]
    border = scale_value(BASE_BORDER, scale_y)
    margin_x = scale_value(BASE_MARGIN_X, scale_x)
    margin_y = scale_value(BASE_MARGIN_Y, scale_y)
    line_spacing = scale_value(BASE_LINE_SPACING, scale_y)
    player_stroke_width = max(2, scale_value(8, scale_y))

    character_max_width = int(round(width * 0.396))
    character_max_height = int(round(height * 0.63))

    character_root = root / args.character_dir / args.character_set
    if not character_root.is_dir():
        print(f"error: character set directory missing: {character_root}", file=sys.stderr)
        return 1

    try:
        p1_image_path, p1_mirror, _p1_color_used = resolve_character_image(
            character_root,
            args.p1_character,
            args.p1_color,
            "Left",
            args.character_set,
            character_max_width,
            character_max_height,
        )
        p2_image_path, p2_mirror, _p2_color_used = resolve_character_image(
            character_root,
            args.p2_character,
            args.p2_color,
            "Right",
            args.character_set,
            character_max_width,
            character_max_height,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    p1_image = load_character_image(p1_image_path, p1_mirror)
    p1_image = crop_transparent(p1_image)
    p1_image = scale_to_fit(p1_image, character_max_width, character_max_height)
    p1_override = resolve_character_override(overrides, args.p1_character, "Left")
    p1_image, p1_offset_x, p1_offset_y = apply_character_override(
        p1_image, p1_override, scale_x, scale_y
    )

    p2_image = load_character_image(p2_image_path, p2_mirror)
    p2_image = crop_transparent(p2_image)
    p2_image = scale_to_fit(p2_image, character_max_width, character_max_height)
    p2_override = resolve_character_override(overrides, args.p2_character, "Right")
    p2_image, p2_offset_x, p2_offset_y = apply_character_override(
        p2_image, p2_override, scale_x, scale_y
    )

    p1_base_width = p1_image.width
    p1_base_height = p1_image.height
    p2_base_width = p2_image.width
    p2_base_height = p2_image.height
    outline_offset = outline_px if outline_px > 0 else 0
    if outline_offset:
        p1_image = apply_character_outline(p1_image, outline_offset, outline_color)
        p2_image = apply_character_outline(p2_image, outline_offset, outline_color)

    p1_x = border + margin_x + p1_offset_x - outline_offset
    p1_y = height - border - margin_y - p1_base_height + p1_offset_y - outline_offset
    p2_x = width - border - margin_x - p2_base_width + p2_offset_x - outline_offset
    p2_y = height - border - margin_y - p2_base_height + p2_offset_y - outline_offset

    canvas = base_image.copy()
    canvas.paste(p1_image, (p1_x, p1_y), p1_image)
    canvas.paste(p2_image, (p2_x, p2_y), p2_image)

    draw = ImageDraw.Draw(canvas)
    stack_y = None
    stack_y = draw_text_block(
        draw,
        root,
        "event_title",
        event_title_block,
        scale_x,
        scale_y,
        BASE_LINE_SPACING,
        BASE_TEXT_STROKE_WIDTH,
        stack_y,
    )
    stack_y = draw_text_block(
        draw,
        root,
        "event_number",
        event_number_block,
        scale_x,
        scale_y,
        BASE_LINE_SPACING,
        BASE_TEXT_STROKE_WIDTH,
        stack_y,
    )
    stack_y = draw_text_block(
        draw,
        root,
        "round_title",
        round_block,
        scale_x,
        scale_y,
        BASE_LINE_SPACING,
        BASE_TEXT_STROKE_WIDTH,
        stack_y,
    )
    _ = draw_text_block(
        draw,
        root,
        "vs_logo",
        text_config.get("vs_logo"),
        scale_x,
        scale_y,
        BASE_LINE_SPACING,
        BASE_TEXT_STROKE_WIDTH,
        None,
    )

    draw_player_names(
        draw,
        root,
        text_config.get("player_names"),
        args.player1,
        args.player2,
        scale_x,
        scale_y,
        width,
        BASE_LINE_SPACING,
        BASE_TEXT_STROKE_WIDTH,
    )

    canvas.convert("RGB").save(output_path)

    print(f"ok: wrote thumbnail to {output_path}")
    if export_ran:
        print("ok: video_tools export completed")
    else:
        print("ok: video_tools export skipped")

    for path in (metadata_path, output_dir / f"{slug}_base.png"):
        if path.is_file():
            try:
                path.unlink()
                print(f"ok: removed {path}")
            except OSError as exc:
                print(f"warning: failed to remove {path}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
