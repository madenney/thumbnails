#!/usr/bin/env python3
"""Character position editor — Flask server.

Provides a visual drag-and-drop interface for adjusting character_overrides
(scale, offset_x, raise) in the active event config.  Reuses the rendering
pipeline from set_thumbnail.py so previews are pixel-perfect.

Usage:
    pip install flask          # one-time
    python3 scripts/editor_server.py
"""
from __future__ import annotations

import copy
import io
import json
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Bootstrap project imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared import load_dotenv, project_root

import set_thumbnail as st

try:
    from flask import Flask, Response, jsonify, render_template, request
except ImportError:
    print("error: flask is required (pip install flask)", file=sys.stderr)
    raise SystemExit(1)

ROOT = project_root()

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=str(Path(__file__).resolve().parent / "editor_templates"),
    static_folder=str(Path(__file__).resolve().parent / "editor_static"),
    static_url_path="/static",
)

# ---------------------------------------------------------------------------
# Character list (sorted directory names from vs_screen)
# ---------------------------------------------------------------------------
CHARACTER_SET = "vs_screen"
CHARACTER_DIR = ROOT / "assets" / "melee" / "characters" / CHARACTER_SET

CHARACTERS: list[str] = sorted(
    p.name for p in CHARACTER_DIR.iterdir() if p.is_dir()
)

OPPONENT = "Fox"  # fixed opponent for the other side


# ---------------------------------------------------------------------------
# Editor state
# ---------------------------------------------------------------------------
class EditorState:
    """Mutable working copy of character_overrides + caches."""

    def __init__(self, event_config: dict, event_config_path: Path):
        self.event_config_path = event_config_path

        # Working copy — deep-cloned so edits don't touch disk until save
        self.overrides_raw: dict = copy.deepcopy(
            event_config.get("character_overrides") or {}
        )
        self.overrides: dict = st.load_character_overrides_data(self.overrides_raw)

        # Track which (character, side) pages have been edited
        self.dirty_pages: set[tuple[str, str]] = set()

        # Text overlay cache: keyed by (left_name, right_name)
        self.text_overlay_cache: dict[tuple[str, str], Image.Image] = {}

    def rebuild_overrides(self) -> None:
        """Re-parse overrides_raw into the resolved form."""
        self.overrides = st.load_character_overrides_data(self.overrides_raw)

    def resolve(self, character: str, side: str) -> dict:
        """Get merged override values for a character+side."""
        return st.resolve_character_override(self.overrides, character, side)

    def get_raw_side_block(self, character: str, side: str) -> dict:
        """Get the raw per-side override block (or empty dict)."""
        chars = self.overrides_raw.get("characters", {})
        char_block = chars.get(character, {})
        return dict(char_block.get(side.lower(), {}))

    def set_values(
        self, character: str, side: str, scale: float, offset_x: int, raise_val: int,
        mirror: bool = False, use_other_side: bool = False,
    ) -> None:
        """Store values for a character+side in the working raw overrides."""
        if "characters" not in self.overrides_raw:
            self.overrides_raw["characters"] = {}
        chars = self.overrides_raw["characters"]
        if character not in chars:
            chars[character] = {}
        char_block = chars[character]
        side_key = side.lower()
        if side_key not in char_block:
            char_block[side_key] = {}
        side_block = char_block[side_key]
        side_block["scale"] = scale
        side_block["offset_x"] = offset_x
        side_block["raise"] = raise_val
        # Remove legacy mirror_left, use new flags
        side_block.pop("mirror_left", None)
        if mirror:
            side_block["mirror"] = True
        else:
            side_block.pop("mirror", None)
        if use_other_side:
            side_block["use_other_side"] = True
        else:
            side_block.pop("use_other_side", None)
        self.rebuild_overrides()
        self.dirty_pages.add((character, side.lower()))

    def save_to_disk(self) -> None:
        """Write overrides_raw back into the event config JSON on disk."""
        with self.event_config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        config["character_overrides"] = copy.deepcopy(self.overrides_raw)
        with self.event_config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        self.dirty_pages.clear()

    def reload_from_disk(self) -> None:
        """Discard working state and reload from disk."""
        with self.event_config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        self.overrides_raw = copy.deepcopy(config.get("character_overrides") or {})
        self.rebuild_overrides()
        self.dirty_pages.clear()
        self.text_overlay_cache.clear()


# ---------------------------------------------------------------------------
# Pre-loaded data (populated in init())
# ---------------------------------------------------------------------------
state: EditorState | None = None
base_image: Image.Image | None = None
event_config: dict = {}
width: int = 0
height: int = 0
scale_x: float = 1.0
scale_y: float = 1.0
outline_px: int = 0
outline_color: str = "#000000"
border: int = 0
margin_x: int = 0
margin_y: int = 0
character_max_width: int = 0
character_max_height: int = 0

# Pre-loaded character images: (character_name, "Left"|"Right") -> (image, mirror_flag)
# Images are loaded, cropped, and scaled-to-fit but NOT override-scaled yet.
char_images: dict[tuple[str, str], Image.Image] = {}


def init() -> None:
    """Load configs, base image, and pre-load all character images."""
    global state, base_image, event_config, width, height
    global scale_x, scale_y, outline_px, outline_color
    global border, margin_x, margin_y
    global character_max_width, character_max_height

    load_dotenv(ROOT / ".env")

    main_config = st.load_main_config(ROOT)
    event_config_path, event_config = st.resolve_event_config(ROOT, main_config)

    state = EditorState(event_config, event_config_path)

    # Base image
    base_image_value = event_config.get("base_image") or st.DEFAULT_BASE_IMAGE
    base_image_path = st.resolve_path(ROOT, base_image_value)
    if base_image_path is None or not base_image_path.is_file():
        print(f"error: base image not found: {base_image_path}", file=sys.stderr)
        raise SystemExit(1)

    base_image = Image.open(base_image_path).convert("RGBA")
    width, height = base_image.size
    scale_x = width / st.BASE_WIDTH
    scale_y = height / st.BASE_HEIGHT

    oc = st.parse_character_outline_config(event_config.get("character_outline"))
    outline_px = max(0, st.scale_value(oc["size"], scale_y)) if oc["enabled"] else 0
    outline_color = oc["color"]

    border = st.scale_value(st.BASE_BORDER, scale_y)
    margin_x = st.scale_value(st.BASE_MARGIN_X, scale_x)
    margin_y = st.scale_value(st.BASE_MARGIN_Y, scale_y)
    character_max_width = int(round(width * 0.396))
    character_max_height = int(round(height * 0.63))

    # Pre-load all character images (raw per-side, no config mirroring baked in)
    print("Pre-loading character images...")
    for char_name in CHARACTERS:
        for side in ("Left", "Right"):
            try:
                img_path, do_mirror, _ = st.resolve_character_image(
                    CHARACTER_DIR,
                    char_name,
                    "Default",
                    side,
                    CHARACTER_SET,
                    character_max_width,
                    character_max_height,
                )
                img = st.load_character_image(img_path, do_mirror)
                img = st.crop_transparent(img)
                img = st.scale_to_fit(img, character_max_width, character_max_height)
                char_images[(char_name, side)] = img
            except RuntimeError as exc:
                print(f"warning: failed to load {char_name} {side}: {exc}", file=sys.stderr)
    print(f"Loaded {len(char_images)} character images.")


def get_text_overlay(left_name: str, right_name: str) -> Image.Image:
    """Render (and cache) the text overlay for given player names."""
    key = (left_name, right_name)
    if key in state.text_overlay_cache:
        return state.text_overlay_cache[key]

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    text_config = event_config.get("text", {})
    stack_y = None
    stack_y = st.draw_text_block(
        draw, ROOT, "event_title", text_config.get("event_title"),
        scale_x, scale_y, st.BASE_LINE_SPACING, st.BASE_TEXT_STROKE_WIDTH, stack_y,
    )
    stack_y = st.draw_text_block(
        draw, ROOT, "event_number", text_config.get("event_number"),
        scale_x, scale_y, st.BASE_LINE_SPACING, st.BASE_TEXT_STROKE_WIDTH, stack_y,
    )
    stack_y = st.draw_text_block(
        draw, ROOT, "round_title", text_config.get("round_title"),
        scale_x, scale_y, st.BASE_LINE_SPACING, st.BASE_TEXT_STROKE_WIDTH, stack_y,
    )
    st.draw_text_block(
        draw, ROOT, "vs_logo", text_config.get("vs_logo"),
        scale_x, scale_y, st.BASE_LINE_SPACING, st.BASE_TEXT_STROKE_WIDTH, None,
    )
    st.draw_player_names(
        draw, ROOT, text_config.get("player_names"),
        left_name, right_name,
        scale_x, scale_y, width, st.BASE_LINE_SPACING, st.BASE_TEXT_STROKE_WIDTH,
    )

    state.text_overlay_cache[key] = overlay
    return overlay


def render_thumbnail(
    character: str, side: str, scale: float, offset_x: int, raise_val: int,
    flip: bool = False, use_other: bool = False,
) -> bytes:
    """Render a full thumbnail JPEG with the given overrides applied to character+side."""
    side_cap = side.capitalize()
    opp_side = "Right" if side_cap == "Left" else "Left"

    # Editing character image — optionally swap to the other side's source
    if use_other:
        edit_key = (character, opp_side)
    else:
        edit_key = (character, side_cap)
    if edit_key not in char_images:
        raise RuntimeError(f"No image for {edit_key[0]} {edit_key[1]}")
    edit_img = char_images[edit_key].copy()

    # Flip horizontally if requested
    if flip:
        edit_img = edit_img.transpose(Image.FLIP_LEFT_RIGHT)

    # Opponent (Fox) image — respect its config mirror/use_other_side too
    opp_override = state.resolve(OPPONENT, opp_side)
    if opp_override.get("use_other_side"):
        opp_load_side = "Left" if opp_side == "Right" else "Right"
    else:
        opp_load_side = opp_side
    opp_key = (OPPONENT, opp_load_side)
    if opp_key not in char_images:
        raise RuntimeError(f"No image for {OPPONENT} {opp_load_side}")
    opp_img = char_images[opp_key].copy()
    if opp_override.get("mirror"):
        opp_img = opp_img.transpose(Image.FLIP_LEFT_RIGHT)

    # Apply overrides to editing character
    edit_override = {"scale": scale, "offset_x": offset_x, "raise": raise_val}
    edit_img, edit_ox, edit_oy = st.apply_character_override(edit_img, edit_override, scale_x, scale_y)

    # Apply overrides to opponent
    opp_img, opp_ox, opp_oy = st.apply_character_override(opp_img, opp_override, scale_x, scale_y)

    # Record base dimensions before outline
    edit_bw, edit_bh = edit_img.width, edit_img.height
    opp_bw, opp_bh = opp_img.width, opp_img.height

    # Apply outline
    offset = outline_px if outline_px > 0 else 0
    if offset:
        edit_img = st.apply_character_outline(edit_img, offset, outline_color)
        opp_img = st.apply_character_outline(opp_img, offset, outline_color)

    # Determine which is left and which is right
    if side_cap == "Left":
        left_img, left_bw, left_bh, left_ox, left_oy = edit_img, edit_bw, edit_bh, edit_ox, edit_oy
        right_img, right_bw, right_bh, right_ox, right_oy = opp_img, opp_bw, opp_bh, opp_ox, opp_oy
        left_name, right_name = character, OPPONENT
    else:
        left_img, left_bw, left_bh, left_ox, left_oy = opp_img, opp_bw, opp_bh, opp_ox, opp_oy
        right_img, right_bw, right_bh, right_ox, right_oy = edit_img, edit_bw, edit_bh, edit_ox, edit_oy
        left_name, right_name = OPPONENT, character

    # Compute positions (same formula as set_thumbnail.py main())
    left_x = border + margin_x + left_ox - offset
    left_y = height - border - margin_y - left_bh + left_oy - offset
    right_x = width - border - margin_x - right_bw + right_ox - offset
    right_y = height - border - margin_y - right_bh + right_oy - offset

    # Composite
    canvas = base_image.copy()
    canvas.paste(left_img, (left_x, left_y), left_img)
    canvas.paste(right_img, (right_x, right_y), right_img)

    # Text overlay
    text_overlay = get_text_overlay(left_name, right_name)
    canvas = Image.alpha_composite(canvas, text_overlay)

    # Encode JPEG
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="JPEG", quality=80)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("editor.html")


@app.route("/api/characters")
def api_characters():
    return jsonify(CHARACTERS)


@app.route("/api/page")
def api_page():
    character = request.args.get("character", CHARACTERS[0])
    side = request.args.get("side", "left")
    resolved = state.resolve(character, side.capitalize())
    dirty = (character, side.lower()) in state.dirty_pages
    return jsonify({
        "character": character,
        "side": side.lower(),
        "scale": resolved.get("scale", 1.0),
        "offset_x": resolved.get("offset_x", 0),
        "raise": resolved.get("raise", 0),
        "mirror": bool(resolved.get("mirror")),
        "use_other_side": bool(resolved.get("use_other_side")),
        "dirty": dirty,
    })


@app.route("/api/render")
def api_render():
    character = request.args.get("character", CHARACTERS[0])
    side = request.args.get("side", "left")
    scale = float(request.args.get("scale", 1.0))
    offset_x = int(float(request.args.get("offset_x", 0)))
    raise_val = int(float(request.args.get("raise", 0)))
    flip = request.args.get("flip", "0") == "1"
    use_other = request.args.get("use_other", "0") == "1"
    try:
        data = render_thumbnail(character, side, scale, offset_x, raise_val, flip, use_other)
    except Exception as exc:
        return str(exc), 500
    return Response(data, mimetype="image/jpeg")


@app.route("/api/commit", methods=["POST"])
def api_commit():
    body = request.get_json(force=True)
    character = body["character"]
    side = body["side"]
    scale = float(body["scale"])
    offset_x = int(body["offset_x"])
    raise_val = int(body["raise"])
    mirror = bool(body.get("mirror", False))
    use_other_side = bool(body.get("use_other_side", False))
    state.set_values(character, side, scale, offset_x, raise_val, mirror, use_other_side)
    return jsonify({"ok": True})


@app.route("/api/save", methods=["POST"])
def api_save():
    state.save_to_disk()
    return jsonify({"ok": True, "message": "Saved to disk"})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    state.reload_from_disk()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init()
    # Open browser after a short delay
    Timer(1.0, lambda: webbrowser.open("http://localhost:5000")).start()
    print("Starting editor at http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
