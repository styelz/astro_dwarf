from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import CameraSettings, SessionStatus, Target, TargetKind
from astro_dwarf.services import command_panel_workflow, sessions_for_command_stack


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_command_panel_workflow_skips_alignment() -> None:
    idle = command_panel_workflow()
    _assert(not idle.calibrate, "no calibrate")
    _assert(not idle.autofocus, "no autofocus")
    _assert(not idle.polar_align, "no polar")
    _assert(not idle.goto, "goto off until coords exist")
    _assert(idle.wait_after_seconds == 0, "no extra wait")
    aimed = command_panel_workflow(goto=True)
    _assert(aimed.goto, "goto when the stack has a pointing")


def test_single_stack_creates_one_session() -> None:
    target = Target(name="LMC", kind=TargetKind.EQUATORIAL, ra_hours=5.4, dec_degrees=-69.8)
    sessions = sessions_for_command_stack(
        target=target,
        device_id="scope-1",
        scheduled_start="2026-09-21T20:00:00",
        camera=CameraSettings(frame_count=20, exposure_seconds=15),
    )
    _assert(len(sessions) == 1, sessions)
    session = sessions[0]
    _assert(session.name == "LMC", session.name)
    _assert(session.device_id == "scope-1", session.device_id)
    _assert(session.status == SessionStatus.PLANNED, session.status)
    _assert(session.workflow.goto, "coords should enable goto")
    _assert(not session.workflow.calibrate, "command-panel stack skips calibrate")
    _assert(not session.mosaic.imported_plan, "single stack is not a mosaic group")


def test_mosaic_stack_creates_pane_sessions() -> None:
    target = Target(name="LMC", kind=TargetKind.EQUATORIAL, ra_hours=5.4, dec_degrees=-69.8)
    panes = [
        {"index": 1, "ra_hours": 5.30, "dec_degrees": -69.5, "row": 1, "column": 1},
        {"index": 2, "ra_hours": 5.50, "dec_degrees": -69.5, "row": 1, "column": 2},
        {"index": 3, "ra_hours": 5.30, "dec_degrees": -70.1, "row": 2, "column": 1},
        {"index": 4, "ra_hours": 5.50, "dec_degrees": -70.1, "row": 2, "column": 2},
    ]
    sessions = sessions_for_command_stack(
        target=target,
        device_id="scope-1",
        scheduled_start="2026-09-21T20:00:00",
        camera=CameraSettings(frame_count=10, exposure_seconds=8),
        panes=panes,
        columns=2,
        rows=2,
        started_at="2026-09-21T10:00:00+00:00",
    )
    _assert(len(sessions) == 4, len(sessions))
    _assert(sessions[0].status == SessionStatus.RUNNING, sessions[0].status)
    _assert(sessions[0].name == "LMC pane 1", sessions[0].name)
    _assert(sessions[1].status == SessionStatus.PLANNED, sessions[1].status)
    group = {item.mosaic.group_id for item in sessions}
    _assert(len(group) == 1 and next(iter(group)), group)
    _assert(all(item.mosaic.imported_plan for item in sessions), "imported-plan panes")
    _assert(sessions[0].mosaic.grid_rows == 2, sessions[0].mosaic.grid_rows)
    _assert(sessions[0].mosaic.grid_columns == 2, sessions[0].mosaic.grid_columns)
    _assert(sessions[0].workflow.goto, "first pane still GOTOs")
    _assert(not sessions[0].workflow.calibrate, "already tracked")
    _assert(sessions[1].workflow.goto, "later panes GOTO")
    _assert(abs(float(sessions[0].target.ra_hours) - 5.30) < 1e-6, sessions[0].target.ra_hours)
    _assert(abs(float(sessions[3].target.dec_degrees) + 70.1) < 1e-6, sessions[3].target.dec_degrees)


def test_one_pane_list_stays_a_single_stack() -> None:
    target = Target(name="Orion", kind=TargetKind.EQUATORIAL, ra_hours=5.6, dec_degrees=-5.4)
    sessions = sessions_for_command_stack(
        target=target,
        device_id="scope-1",
        scheduled_start="2026-09-21T20:00:00",
        camera=CameraSettings(),
        panes=[{"index": 1, "ra_hours": 5.6, "dec_degrees": -5.4, "row": 1, "column": 1}],
        columns=1,
        rows=1,
    )
    _assert(len(sessions) == 1, sessions)
    _assert(not sessions[0].mosaic.imported_plan, "1 pane is a single stack")


def main() -> int:
    test_command_panel_workflow_skips_alignment()
    test_single_stack_creates_one_session()
    test_mosaic_stack_creates_pane_sessions()
    test_one_pane_list_stays_a_single_stack()
    print("command stack session tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
