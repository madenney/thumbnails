#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None


def mirror_left_to_right(base_dir: Path, color: str) -> None:
    left_path = base_dir / f"{color} Left.png"
    right_path = base_dir / f"{color} Right.png"
    if not left_path.is_file():
        raise FileNotFoundError(f"missing left asset: {left_path}")
    if Image is None:
        raise RuntimeError("Pillow is required (pip install pillow)")

    image = Image.open(left_path).convert("RGBA")
    image = image.transpose(Image.FLIP_LEFT_RIGHT)
    right_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(right_path)
    print(f"ok: wrote {right_path}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    falco_dir = root / "assets" / "melee" / "characters" / "vs_screen" / "Falco"
    if not falco_dir.is_dir():
        print(f"error: Falco asset dir not found: {falco_dir}", file=sys.stderr)
        return 1

    try:
        mirror_left_to_right(falco_dir, "Default")
        mirror_left_to_right(falco_dir, "Green")
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("ok: Falco right assets replaced with mirrored lefts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
