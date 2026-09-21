from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    CameraSettings,
    Mosaic,
    Session,
    Target,
    capture_history_owner,
    history_record_for_manual_stack,
    history_record_for_run,
    history_records_for_live_mosaic,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_capture_history_owner_avoids_double_write() -> None:
    _assert(
        capture_history_owner(session_active=True, mosaic_running=True) == "session",
        "scheduled session owns History",
    )
    _assert(
        capture_history_owner(session_active=False, mosaic_running=True) == "mosaic",
        "live mosaic owns History while running",
    )
    _assert(
        capture_history_owner(session_active=False, mosaic_running=False) == "manual",
        "manual stack writes History",
    )
    _assert(
        capture_history_owner(
            session_active=False, mosaic_running=False, session_finalizing=True
        ) == "session",
        "session finalize does not double-write a manual row",
    )


def test_manual_stack_history_uses_stacked_frames() -> None:
    record = history_record_for_manual_stack(
        device_id="dev-1",
        target_name="Toliman",
        camera=CameraSettings(exposure_seconds=15, frame_count=10),
        started_at="2026-09-19T14:00:00+00:00",
        ended_at="2026-09-19T14:02:30+00:00",
        captured_frame_count=8,
        outcome="Stopped by user",
    )
    _assert(record.target_name == "Toliman", record.target_name)
    _assert(record.captured_frame_count == 8, record.captured_frame_count)
    _assert(record.frame_count == 10, record.frame_count)
    _assert(record.exposure_seconds == 15, record.exposure_seconds)
    _assert(record.outcome == "Stopped by user", record.outcome)
    _assert("8/10" in record.summary, record.summary)


def test_live_mosaic_history_keeps_completed_and_stopped_panes() -> None:
    camera = CameraSettings(exposure_seconds=15, frame_count=10)
    members = [
        Session(
            name="Toliman pane 1",
            target=Target(name="Toliman", ra_hours=14.74, dec_degrees=-61.16),
            device_id="dev-1",
            scheduled_start="2026-09-19T14:00:00+00:00",
            camera=camera,
            mosaic=Mosaic(group_id="g", grid_rows=2, grid_columns=2, row=1, column=1),
            actual_started_at="2026-09-19T14:00:00+00:00",
            actual_ended_at="2026-09-19T14:02:00+00:00",
        ),
        Session(
            name="Toliman pane 2",
            target=Target(name="Toliman", ra_hours=14.58, dec_degrees=-61.16),
            device_id="dev-1",
            scheduled_start="2026-09-19T14:00:00+00:00",
            camera=camera,
            mosaic=Mosaic(group_id="g", grid_rows=2, grid_columns=2, row=1, column=2),
            actual_started_at="2026-09-19T14:02:10+00:00",
        ),
        Session(
            name="Toliman pane 3",
            target=Target(name="Toliman", ra_hours=14.74, dec_degrees=-60.50),
            device_id="dev-1",
            scheduled_start="2026-09-19T14:00:00+00:00",
            camera=camera,
            mosaic=Mosaic(group_id="g", grid_rows=2, grid_columns=2, row=2, column=1),
        ),
    ]
    records = history_records_for_live_mosaic(
        members,
        {1: 10, 2: 4},
        ok=False,
        stopped=True,
        current_index=2,
        ended_at="2026-09-19T14:04:00+00:00",
    )
    _assert(len(records) == 2, records)
    _assert(records[0].outcome == "Completed", records[0].outcome)
    _assert(records[0].captured_frame_count == 10, records[0].captured_frame_count)
    _assert(records[1].outcome == "Stopped by user", records[1].outcome)
    _assert(records[1].captured_frame_count == 4, records[1].captured_frame_count)


def test_live_mosaic_history_keeps_completed_panes_on_failure() -> None:
    camera = CameraSettings(exposure_seconds=15, frame_count=10)
    members = [
        Session(
            name="Toliman pane 1",
            target=Target(name="Toliman", ra_hours=14.74, dec_degrees=-61.16),
            device_id="dev-1",
            scheduled_start="2026-09-19T14:00:00+00:00",
            camera=camera,
            mosaic=Mosaic(group_id="g", grid_rows=2, grid_columns=2, row=1, column=1),
            actual_started_at="2026-09-19T14:00:00+00:00",
            actual_ended_at="2026-09-19T14:02:00+00:00",
        ),
        Session(
            name="Toliman pane 2",
            target=Target(name="Toliman", ra_hours=14.58, dec_degrees=-61.16),
            device_id="dev-1",
            scheduled_start="2026-09-19T14:00:00+00:00",
            camera=camera,
            mosaic=Mosaic(group_id="g", grid_rows=2, grid_columns=2, row=1, column=2),
            actual_started_at="2026-09-19T14:02:10+00:00",
        ),
    ]
    records = history_records_for_live_mosaic(
        members,
        {1: 10, 2: 0},
        ok=False,
        stopped=False,
        current_index=2,
        ended_at="2026-09-19T14:03:00+00:00",
        result="GOTO pane 2 failed: CODE_ASTRO_GOTO_FAILED (-11505)",
    )
    _assert(len(records) == 2, records)
    _assert(records[0].outcome == "Completed", records[0].outcome)
    _assert(records[0].captured_frame_count == 10, records[0].captured_frame_count)
    _assert("GOTO pane 2 failed" in records[1].outcome, records[1].outcome)
    _assert(records[1].captured_frame_count == 0, records[1].captured_frame_count)


def test_scheduled_history_record_stays_stacked_only() -> None:
    session = Session(
        name="Scheduled Toliman",
        target=Target(name="Toliman"),
        device_id="dev-1",
        scheduled_start="2026-09-19T14:00:00+00:00",
        camera=CameraSettings(exposure_seconds=15, frame_count=40),
        actual_started_at="2026-09-19T14:00:00+00:00",
        actual_ended_at="2026-09-19T14:10:00+00:00",
        outcome="Completed",
    )
    record = history_record_for_run(
        session,
        actual_duration_seconds=600,
        captured_frame_count=12,
    )
    _assert(record.captured_frame_count == 12, "scheduled path uses stacked peak")
    _assert(record.frame_count == 40, record.frame_count)


def main() -> int:
    test_capture_history_owner_avoids_double_write()
    test_manual_stack_history_uses_stacked_frames()
    test_live_mosaic_history_keeps_completed_and_stopped_panes()
    test_live_mosaic_history_keeps_completed_panes_on_failure()
    test_scheduled_history_record_stays_stacked_only()
    print("capture history tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
