from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packaging.release_body import IMAGE, build_release_body


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_highlights_sit_above_the_screenshot() -> None:
    body = build_release_body("- stitch a finished mosaic\n- dim a blocked pad")
    _assert(body.startswith("- stitch a finished mosaic\n"), body)
    _assert(body.index("- dim a blocked pad") < body.index(IMAGE), body)


def test_empty_highlights_start_at_the_screenshot() -> None:
    body = build_release_body("  \n")
    _assert(body.startswith(IMAGE), body)


if __name__ == "__main__":
    test_highlights_sit_above_the_screenshot()
    test_empty_highlights_start_at_the_screenshot()
    print("ok")
