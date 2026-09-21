from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_telemetry import _stacking_progress_changes
from astro_dwarf.telemetry_view import format_telemetry


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _view(raw: dict) -> dict:
    return format_telemetry(raw, updated_at=1.0, now=1.0)


def test_capture_accepted_is_not_exposing() -> None:
    view = _view({"capture_active": True, "capture_state": "running", "capture_total": 40})
    _assert(view["capture_active"] is True, "accepted capture stays active")
    _assert(view["capture_progress_seen"] is False, "synthetic 0/0 is not a firmware packet")
    _assert(view["exposure_running"] is False, "0/0 waits for a progress packet")
    _assert(view["exposure_elapsed_s"] == 0, "no leftover elapsed")


def test_capture_accepted_with_exposure_waits() -> None:
    view = _view({
        "capture_active": True,
        "capture_state": "running",
        "capture_total": 10,
        "exposure_text": "15s",
    })
    _assert(view["exposure_running"] is False, "synthetic 0/0 waits even with a configured exposure")
    _assert(view["exposure_total_s"] == 15, "uses the configured exposure")


def test_firmware_zero_zero_starts_exposure() -> None:
    view = _view({
        "capture_active": True,
        "capture_state": "running",
        "capture_current": 0,
        "capture_stacked": 0,
        "capture_total": 5,
        "capture_progress_seen": True,
        "exposure_text": "15s",
    })
    _assert(view["capture_progress_seen"] is True, "firmware 0/0 is live")
    _assert(view["exposure_running"] is True, "0/0 starts the first frame cycle")


def test_current_ahead_keeps_running() -> None:
    view = _view({
        "capture_active": True,
        "capture_state": "running",
        "capture_current": 1,
        "capture_stacked": 0,
        "capture_total": 10,
        "exposure_text": "15s",
    })
    _assert(view["exposure_running"] is True, "1/0 is an open shutter")
    _assert(view["capture_text"] == "0/10", "HUD still follows stacked frames")
    _assert(view["capture_progress_seen"] is True, "non-zero current counts as seen")


def test_stacked_caught_up_starts_next() -> None:
    view = _view({
        "capture_active": True,
        "capture_state": "running",
        "capture_current": 1,
        "capture_stacked": 1,
        "capture_total": 10,
        "exposure_text": "15s",
        "exposure_elapsed_s": 15,
    })
    _assert(view["exposure_running"] is True, "1/1 stays inside the exposure that opened at 1/0")
    _assert(view["capture_text"] == "1/10", "HUD shows the stacked frame")


def test_next_current_keeps_running() -> None:
    view = _view({
        "capture_active": True,
        "capture_state": "running",
        "capture_current": 2,
        "capture_stacked": 1,
        "capture_total": 10,
        "exposure_text": "15s",
    })
    _assert(view["exposure_running"] is True, "2/1 is the next open shutter")
    _assert(view["capture_text"] == "1/10", "HUD stays on stacked frames")


def test_last_frame_stacked_holds() -> None:
    view = _view({
        "capture_active": True,
        "capture_state": "running",
        "capture_current": 5,
        "capture_stacked": 5,
        "capture_total": 5,
        "exposure_text": "15s",
    })
    _assert(view["exposure_running"] is False, "5/5 holds after the last subframe")
    _assert(view["capture_progress_seen"] is True, "last packet still counts as seen")
    _assert(view["capture_text"] == "5/5", "HUD shows the finished stack")


def test_last_frame_processing_still_runs() -> None:
    view = _view({
        "capture_active": True,
        "capture_current": 5,
        "capture_stacked": 4,
        "capture_total": 5,
        "exposure_text": "15s",
    })
    _assert(view["exposure_running"] is True, "5/4 is still processing the last subframe")


def test_firmware_elapsed_at_zero_does_not_start() -> None:
    view = _view({
        "capture_active": True,
        "exposure_elapsed_s": 1.2,
        "exposure_total_s": 15,
    })
    _assert(view["exposure_running"] is False, "leftover long-exp at synthetic 0/0 is still waiting")


def test_firmware_elapsed_while_live_is_exposing() -> None:
    view = _view({
        "capture_active": True,
        "capture_current": 0,
        "capture_stacked": 0,
        "capture_progress_seen": True,
        "exposure_elapsed_s": 1.2,
        "exposure_total_s": 15,
    })
    _assert(view["exposure_running"] is True, "long-exp progress after firmware 0/0")


def test_taken_frame_starts_exposure() -> None:
    view = _view({"capture_state": "running", "capture_current": 1, "capture_total": 40})
    _assert(view["exposure_running"] is True, "a taken frame is stacking")


def test_idle_is_not_exposing() -> None:
    view = _view({"capture_active": False, "capture_current": 3, "exposure_elapsed_s": 8})
    _assert(view["exposure_running"] is False, "leftover counts after stop are idle")
    _assert(view["capture_progress_seen"] is False, "idle hides the live-progress flag")


def test_stack_counter_uses_stacked_when_taken_is_ahead() -> None:
    view = _view({
        "capture_active": True,
        "capture_current": 5,
        "capture_stacked": 4,
        "capture_total": 50,
    })
    _assert(view["capture_text"] == "4/50", "stack counter follows stacked frames")
    _assert(view["capture_current"] == 5, "taken count stays distinct")
    _assert(view["capture_stacked"] == 4, "stacked count is preserved")
    _assert(view["exposure_running"] is True, "current ahead of stacked stays in the cycle")


def test_stack_counter_falls_back_to_taken() -> None:
    view = _view({
        "capture_state": "running",
        "capture_current": 3,
        "capture_total": 40,
    })
    _assert(view["capture_text"] == "3/40", "taken is used before stacked arrives")
    _assert(view["capture_current"] == 3, "taken count is not overwritten")


def test_taken_ahead_does_not_bump_capture_text() -> None:
    view = _view({
        "capture_active": True,
        "capture_current": 6,
        "capture_stacked": 4,
        "capture_total": 10,
        "exposure_text": "15",
    })
    _assert(view["capture_text"] == "4/10", "HUD ignores the taken-ahead counter")
    _assert(view["exposure_running"] is True, "timer is already running")


def test_progress_packet_marks_zero_zero_seen() -> None:
    message = SimpleNamespace(
        total_count=5,
        target_name="Atria pane 4",
        current_count=0,
        stacked_count=0,
        update_type=2,
    )
    changes = _stacking_progress_changes(message)
    _assert(changes["capture_progress_seen"] is True, "firmware 0/0 is a real progress packet")
    _assert(changes["capture_current"] == 0, "current stays 0")
    _assert(changes["capture_stacked"] == 0, "stacked stays 0")
    _assert(changes["capture_active"] is True, "progress packet arms capture")


def main() -> int:
    test_capture_accepted_is_not_exposing()
    test_capture_accepted_with_exposure_waits()
    test_firmware_zero_zero_starts_exposure()
    test_current_ahead_keeps_running()
    test_stacked_caught_up_starts_next()
    test_next_current_keeps_running()
    test_last_frame_stacked_holds()
    test_last_frame_processing_still_runs()
    test_firmware_elapsed_at_zero_does_not_start()
    test_firmware_elapsed_while_live_is_exposing()
    test_taken_frame_starts_exposure()
    test_idle_is_not_exposing()
    test_stack_counter_uses_stacked_when_taken_is_ahead()
    test_stack_counter_falls_back_to_taken()
    test_taken_ahead_does_not_bump_capture_text()
    test_progress_packet_marks_zero_zero_seen()
    print("exposure running tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
