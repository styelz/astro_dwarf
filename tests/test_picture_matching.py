from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_TELE_WIDE_PICTURE_MATCHING,
    TYPE_NOTIFICATION,
    TelemetryTap,
    normalize_picture_matching,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _almost(value: float, expected: float, places: int = 5) -> None:
    _assert(round(abs(value - expected), places) == 0, f"{value} != {expected}")


def test_empty_rectangle_is_ignored() -> None:
    _assert(normalize_picture_matching(0, 0, 0, 0) == {}, "zero size")
    _assert(normalize_picture_matching(100, 80, -4, 40) == {}, "negative width")


def test_live_1920_rectangle_stays_in_live_space() -> None:
    # Tele is ~6.5% of the Dwarf 3 wide FOV, so a 1920x1080 box is ~126x69.
    result = normalize_picture_matching(900, 500, 126, 69)
    _assert(result["tele_match_scale"] == 1, result)
    _almost(result["tele_match_nx"], (900 + 63) / 1920)
    _almost(result["tele_match_ny"], (500 + 34.5) / 1080)
    _almost(result["tele_match_nw"], 126 / 1920)
    _almost(result["tele_match_nh"], 69 / 1080)
    _assert(0 < result["tele_match_nw"] < 0.25, result["tele_match_nw"])
    _assert(0 < result["tele_match_nh"] < 0.25, result["tele_match_nh"])


def test_still_3840_rectangle_uses_double_span() -> None:
    result = normalize_picture_matching(1800, 1000, 252, 138)
    _assert(result["tele_match_scale"] == 2, result)
    _almost(result["tele_match_nx"], (1800 + 126) / 3840)
    _almost(result["tele_match_ny"], (1000 + 69) / 2160)
    _almost(result["tele_match_nw"], 252 / 3840)
    _almost(result["tele_match_nh"], 138 / 2160)


def test_full_frame_failed_match_is_not_a_tele_footprint() -> None:
    _assert(normalize_picture_matching(0, 0, 1920, 1080) == {}, "live full frame")
    _assert(normalize_picture_matching(0, 0, 3840, 2160) == {}, "still full frame")


def test_live_footprint_over_ten_percent_stays_in_live_space() -> None:
    # Distortion/padding can put the live tele box over 10% of 1920. That must
    # not be treated as a 3840 still, or the Control overlay shrinks by half.
    result = normalize_picture_matching(860, 480, 220, 120)
    _assert(result["tele_match_scale"] == 1, result)
    _almost(result["tele_match_nw"], 220 / 1920)
    _almost(result["tele_match_nh"], 120 / 1080)


def test_notify_decodes_picture_matching() -> None:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0)
    tap._notify = notify_pb2
    tap._base = object()
    message = notify_pb2.PictureMatching()
    message.x = 900
    message.y = 500
    message.width = 126
    message.height = 69
    changes = tap._decode(
        CMD_NOTIFY_TELE_WIDE_PICTURE_MATCHING,
        TYPE_NOTIFICATION,
        message.SerializeToString(),
    )
    _assert(changes["tele_match_width"] == 126, changes)
    _almost(changes["tele_match_nw"], 126 / 1920)


if __name__ == "__main__":
    test_empty_rectangle_is_ignored()
    test_live_1920_rectangle_stays_in_live_space()
    test_still_3840_rectangle_uses_double_span()
    test_full_frame_failed_match_is_not_a_tele_footprint()
    test_live_footprint_over_ten_percent_stays_in_live_space()
    test_notify_decodes_picture_matching()
    print("ok")
