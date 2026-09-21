from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.services import next_free_start


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_next_free_start_advances_past_sub_minute_block_end() -> None:
    start = datetime(2026, 9, 21, 8, 15, 30)
    occupied = [(datetime(2026, 9, 21, 8, 11, 0), datetime(2026, 9, 21, 8, 15, 30))]
    free = next_free_start(occupied, start, timedelta(minutes=4))
    _assert(free >= datetime(2026, 9, 21, 8, 16, 0), f"cursor stuck at {free}")


def test_next_free_start_empty_occupied_keeps_minute() -> None:
    start = datetime(2026, 9, 21, 6, 43, 12)
    free = next_free_start([], start, timedelta(seconds=90))
    _assert(free == datetime(2026, 9, 21, 6, 43, 0), f"snapped to {free}")


if __name__ == "__main__":
    test_next_free_start_advances_past_sub_minute_block_end()
    test_next_free_start_empty_occupied_keeps_minute()
    print("next_free_start tests ok")
