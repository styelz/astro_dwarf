"""GitHub release text. User highlights sit above the screenshot."""

from __future__ import annotations

import argparse
from pathlib import Path

IMAGE = (
    "![Astro Dwarf Control page]"
    "(https://raw.githubusercontent.com/styelz/astro_dwarf/main/docs/screens/control-live.jpg)"
)
BLURB = (
    "Desktop scheduler and multi-telescope controller for Dwarf II, Dwarf 3, and Dwarf Mini. "
    "Unattended imaging, mosaics, Stellarium targeting, and live control from one HUD."
)


def build_release_body(highlights: str) -> str:
    notes = highlights.strip()
    tail = f"{IMAGE}\n\n{BLURB}\n"
    if not notes:
        return tail
    return f"{notes}\n\n{tail}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the GitHub release body")
    parser.add_argument("--highlights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = ""
    if args.highlights.is_file():
        text = args.highlights.read_text(encoding="utf-8")
    args.output.write_text(build_release_body(text), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
