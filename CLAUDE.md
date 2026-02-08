# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python CLI tool for generating Super Smash Bros. Melee esports thumbnails (set thumbnails, event thumbnails, channel thumbnails). Uses Pillow for image composition and integrates with an external `video_tools` project for final export.

## Commands

```bash
# Generate a single set thumbnail (edit configs/quick_set_thumbnail.json first)
python3 scripts/quick_set_thumbnail.py

# Generate with explicit arguments
python3 index.py set_thumbnail --player1 NAME --player2 NAME --p1-character FOX --p2-character FALCON --round "ROUND TITLE"

# Batch test generation
python3 scripts/test_set_thumbnail_generator.py
python3 scripts/test_set_thumbnail_generator.py --limit N --seed S

# Other thumbnail types
python3 index.py lunar_thumbnail --title "Title" --subtitle "Subtitle"
python3 index.py event_thumbnail --event "Event Name"

# Install a title font from ZIP
python3 scripts/install_title_font.py <zip> --config configs/events/<event>.json
```

There is no test suite, linter, or build system configured.

## Architecture

**Entry flow:** `index.py` → `delegator.py` → specific script (`set_thumbnail.py`, `lunar_thumbnail.py`, `event_thumbnail.py`)

- **index.py** — Loads `.env`, validates `VIDEO_TOOLS_THUMBNAIL_PATH`, delegates to `delegator.py`
- **delegator.py** — Routes commands (with aliases like `set`, `lunar`, `event`) to the appropriate script
- **_shared.py** — Shared utilities: env loading, video_tools subprocess wrapper, slugify, metadata writer
- **set_thumbnail.py** (~1200 lines) — The core script. Handles the full image composition pipeline: character image loading/positioning, text rendering, and thumbnail assembly
- **quick_set_thumbnail.py** — Convenience wrapper that reads `configs/quick_set_thumbnail.json` and calls `set_thumbnail.py`
- **test_set_thumbnail_generator.py** — Batch generator using `scripts/test_sets.json`, outputs pairs (anchor left/right) to `output/`

## Configuration System

- `configs/main.json` — Points to the active event config via `current_event`
- `configs/events/<event>.json` — Event-specific styling: background image, text block positions/fonts/colors, character outline settings, and per-character positioning overrides (scale, offset_x, offset_y)
- `configs/quick_set_thumbnail.json` — Quick-set defaults (player names, characters, colors, round)

## Key Implementation Details

- **Character resolution** uses fuzzy matching (case/accent-insensitive) and falls back to Default color if a requested color variant is missing
- **Character assets** are side-aware (Left/Right pairs in `vs_screen/`); Roy has special mirroring logic, Falco has a dedicated fix script
- **Text rendering** supports adaptive font sizing to fit constraints, multi-segment event titles with variable sizing, stroke/outline effects, and symmetric player name placement
- **External dependency:** Requires `VIDEO_TOOLS_THUMBNAIL_PATH` env var pointing to `video_tools/thumbnail.py` (set in `.env`)
- Character assets live under `assets/melee/characters/` with subdirectories: `vs_screen/`, `portraits/`, `stock_icons/`, `css/`, `saga_icons/`
