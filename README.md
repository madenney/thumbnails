# Thumbnails

YouTube thumbnail generator that wraps the `video_tools` thumbnail script.

## Setup
- Set `VIDEO_TOOLS_THUMBNAIL_PATH` in `.env` to the `video_tools/thumbnail.py` path.
- Run `scripts/check_env.sh` to warn if the path is missing.

## Usage
- `python index.py check_env` validates `VIDEO_TOOLS_THUMBNAIL_PATH`.
- `python index.py set_thumbnail --player1 "P1" --player2 "P2" --p1-character "Fox" --p2-character "Marth" --round "Winners Quarters"`
- `python index.py lunar_thumbnail --title "Lunar Melee" --subtitle "Highlights"`
- `python index.py event_thumbnail --event "Event Name" --tagline "Top 8"`

## Set Thumbnail Config
- `configs/main.json` selects the active event (`current_event`) and points at event configs.
- Event configs (for example `configs/events/jungle.json`) control event title/number/VS text, positions, sizes, colors, font paths, and character overrides; `--round` overrides the round title text.
- Install a font zip and update config font paths with `python scripts/install_title_font.py <zip> --config configs/events/jungle.json --targets event_title,event_number,round_title,vs_logo`.

Each generator:
- `set_thumbnail` uses `assets/test6.jpg` as the default base image.
- `lunar_thumbnail` and `event_thumbnail` call `video_tools/thumbnail -e` unless `--skip-export` is provided.
- Writes the generated thumbnail PNG for `set_thumbnail` to `output/set_thumbnail/` and removes intermediate files.
- `lunar_thumbnail` and `event_thumbnail` write metadata JSON files to `output/<command>/`.

Character assets:
- Default set is `assets/melee/characters/vs_screen` for `set_thumbnail`.
- Use `--character-set portraits` or `--character-set stock_icons` to switch.
