"""Completed mosaic runs can correct the pane-change time in Timing."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import HardwareProfile, HistoryRecord
from astro_dwarf.duration_suggest import suggest_hardware_profile


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def _mosaic_run(pane_gap_seconds: float) -> HistoryRecord:
    # Three gaps on a 4-pane mosaic. The rest of the run matches the profile
    # so the suggestion is only the measured pane change.
    return HistoryRecord(
        session_id="session",
        device_id="device",
        target_name="Mosaic",
        scheduled_start="2026-09-26T12:00:00",
        actual_started_at="2026-09-26T12:00:00",
        actual_ended_at="2026-09-26T12:02:00",
        planned_duration_seconds=98,
        actual_duration_seconds=8 + pane_gap_seconds,
        frame_count=20,
        outcome="Completed",
        captured_frame_count=20,
        mosaic_panes=4,
        step_seconds={
            "Session start": 8,
            "Changing mosaic pane": pane_gap_seconds,
        },
    )


def test_pane_gaps_suggest_pane_slew() -> None:
    hint = suggest_hardware_profile([_mosaic_run(90)], HardwareProfile())
    changes = {item["key"]: item for item in hint["changes"]}
    pane = changes.get("pane_slew_seconds")
    _assert(pane is not None, hint)
    _assert(pane["suggested"] == 30, pane)
    _assert("startup_seconds" not in changes, changes)


def test_matching_pane_gaps_stay_put() -> None:
    hint = suggest_hardware_profile([_mosaic_run(36)], HardwareProfile())
    keys = {item["key"] for item in hint["changes"]}
    _assert("pane_slew_seconds" not in keys, hint)


def main() -> None:
    test_pane_gaps_suggest_pane_slew()
    test_matching_pane_gaps_stay_put()
    print("test_duration_suggest: ok")


if __name__ == "__main__":
    main()
