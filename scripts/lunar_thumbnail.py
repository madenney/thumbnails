#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from _shared import (
    load_dotenv,
    parse_video_tools_args,
    project_root,
    require_video_tools_path,
    run_video_tools,
    slugify,
    utc_now,
    write_metadata,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a channel thumbnail using video_tools.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--title", required=True, help="Main title text")
    parser.add_argument("--subtitle", help="Secondary title text")
    parser.add_argument("--tagline", help="Optional tagline")
    parser.add_argument(
        "--output-dir",
        default="output/lunar_thumbnail",
        help="Directory to write metadata JSON",
    )
    parser.add_argument("--slug", help="Override output file slug")
    parser.add_argument(
        "--skip-export",
        action="store_true",
        help="Skip calling video_tools/thumbnail -e",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, unknown_args = parser.parse_known_args(argv)
    video_tools_args = parse_video_tools_args(unknown_args)

    root = project_root()
    load_dotenv(root / ".env")

    try:
        video_tools_path = require_video_tools_path()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    slug_source = args.slug or args.title
    slug = slugify(slug_source)
    output_dir = root / args.output_dir
    metadata_path = output_dir / f"{slug}.json"

    export_ran = False
    if not args.skip_export:
        export_ran = True
        exit_code = run_video_tools(video_tools_path, video_tools_args, root)
        if exit_code != 0:
            return exit_code

    metadata = {
        "kind": "lunar_thumbnail",
        "created_at": utc_now(),
        "text": {
            "title": args.title,
            "subtitle": args.subtitle,
            "tagline": args.tagline,
        },
        "video_tools": {
            "path": str(video_tools_path),
            "args": video_tools_args,
            "export_ran": export_ran,
        },
    }
    write_metadata(metadata_path, metadata)

    print(f"ok: wrote metadata to {metadata_path}")
    print("ok: video_tools export completed" if export_ran else "ok: video_tools export skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
