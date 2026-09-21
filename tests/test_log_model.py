from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.qt_backend import LogListModel


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _line(message: str, level: str = "NOTICE", time: str = "01:00:00", device: str = "DWARF") -> dict:
    return {"time": time, "level": level, "device": device, "message": message, "category": "device"}


def test_consecutive_duplicates_increment_count() -> None:
    model = LogListModel()
    model.append(_line("Stack started", time="01:00:00"))
    model.append(_line("Stack started", time="01:00:01"))
    visible = model.visible_entries()
    _assert(len(visible) == 1, f"expected 1 row, got {len(visible)}")
    _assert(visible[0]["count"] == 2, visible[0])
    _assert(visible[0]["time"] == "01:00:01", visible[0]["time"])


def test_device_filter_coalesces_across_hidden_info() -> None:
    model = LogListModel()
    model.set_filter("device")
    model.append(_line("Stack started", time="01:00:00"))
    model.append(_line("Set count 40", level="INFO", time="01:00:01"))
    model.append(_line("Stack started", time="01:00:02"))
    visible = model.visible_entries()
    _assert(len(visible) == 1, f"device view should keep one row, got {len(visible)}: {visible}")
    _assert(visible[0]["count"] == 2, visible[0])
    _assert(visible[0]["time"] == "01:00:02", visible[0]["time"])
    _assert(len(model._all) == 3, "hidden INFO stays in the unfiltered buffer")


def test_switching_to_device_filter_coalesces_existing_rows() -> None:
    model = LogListModel()
    model.set_filter("debug")
    model.append(_line("Stack started", time="01:00:00"))
    model.append(_line("Set count 40", level="INFO", time="01:00:01"))
    model.append(_line("Stack started", time="01:00:02"))
    _assert(len(model.visible_entries()) == 3, "debug keeps intervening INFO")
    model.set_filter("device")
    visible = model.visible_entries()
    _assert(len(visible) == 1, f"device view should keep one row, got {len(visible)}: {visible}")
    _assert(visible[0]["count"] == 2, visible[0])
    _assert(visible[0]["time"] == "01:00:02", visible[0]["time"])


def test_all_filter_coalesces_across_hidden_debug() -> None:
    model = LogListModel()
    model.set_filter("all")
    model.append(_line("Opening stream", level="INFO", time="01:00:00"))
    model.append(_line("ws ping", level="DEBUG", time="01:00:01"))
    model.append(_line("Opening stream", level="INFO", time="01:00:02"))
    visible = model.visible_entries()
    _assert(len(visible) == 1, f"all view should keep one row, got {len(visible)}: {visible}")
    _assert(visible[0]["count"] == 2, visible[0])


def test_different_messages_stay_separate() -> None:
    model = LogListModel()
    model.set_filter("device")
    model.append(_line("Stack started"))
    model.append(_line("Set count 40", level="INFO"))
    model.append(_line("Stack stopped"))
    visible = model.visible_entries()
    _assert(len(visible) == 2, f"expected two device rows, got {len(visible)}")
    _assert(visible[0]["count"] == 1, visible[0])
    _assert(visible[1]["count"] == 1, visible[1])


if __name__ == "__main__":
    test_consecutive_duplicates_increment_count()
    test_device_filter_coalesces_across_hidden_info()
    test_switching_to_device_filter_coalesces_existing_rows()
    test_all_filter_coalesces_across_hidden_debug()
    test_different_messages_stay_separate()
    print("ok")
