# Thumbnails

Toolkit for generating Smash Melee set thumbnails.

## Setup
- Python 3 and Pillow: `pip install pillow`
- Set `VIDEO_TOOLS_THUMBNAIL_PATH` in `.env` if you want to use `video_tools`.
- Check the env with `python3 scripts/check_env.sh` or `python3 index.py check_env`.

## Repo hygiene
- `.env` is ignored; keep secrets out of git.
- `output/` and `tmp/` are ignored; they are generated artifacts.

## Quick start (single image)
1. Pick the active event in `configs/main.json`.
2. Edit the event config in `configs/events/<event>.json`.
3. Edit `configs/quick_set_thumbnail.json` (player names, characters, colors, round).
4. Run `python3 scripts/quick_set_thumbnail.py`.

## Batch tests
Edit `scripts/test_sets.json`, then run:
`python3 scripts/test_set_thumbnail_generator.py`

Behavior:
- Generates two images per character (anchor on left, then anchor on right).
- Uses `anchor_character` from the JSON (defaults to Fox).
- Uses `rounds` for the round title.
- Use `--limit N` to cap output count.
- Outputs to `output/set_thumbnail_test_N/`.

## Event config (configs/events/<id>.json)
Common fields:
- `base_image`: background image path.
- `text`: blocks for `event_title`, `event_number`, `round_title`, `vs_logo`, `player_names`.
- `character_overrides`: per-character `left`/`right` overrides for `scale`, `offset_x`, `offset_y`.
- `character_outline`: `enabled`, `size`, `color` for an outline around character art.

Text blocks:
- `enabled`, `text`, `font_path`, `max_size`, `min_size`, `max_width`, `x`, `y`, `fill`,
  `stroke_fill`, `stroke_width`.
- `event_title.segments` supports `size_scale` and optional `x_adjust` per segment.
- `{event_number}` inside segments is replaced with the last `#...` token from the title text.
- `player_names` uses symmetric placement with `x_padding`, `center_gap`, and `y`.

## Font install
Install a font zip and update config font paths:
`python3 scripts/install_title_font.py <zip> --config configs/events/<event>.json`

Limit updates to specific blocks:
`--targets event_title,event_number,round_title,vs_logo,player_names`

## Other commands
- `python3 scripts/set_thumbnail.py ...` (direct CLI; still uses `configs/main.json`)
- `python3 index.py set_thumbnail ...`
