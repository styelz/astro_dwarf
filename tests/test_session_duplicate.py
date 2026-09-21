from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import HardwareProfile, Mosaic, Session, SessionStatus, Target, TargetKind
from astro_dwarf.services import (
    copy_session_name,
    duplicate_session_drafts,
    duplicate_session_scope,
    stagger_mosaic_sessions,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _session(
    session_id: str,
    start: str,
    *,
    name: str = "",
    group: str = "",
    status: SessionStatus = SessionStatus.PLANNED,
    device: str = "scope-1",
) -> Session:
    return Session(
        id=session_id,
        name=name or session_id,
        target=Target(name="LMC", kind=TargetKind.EQUATORIAL, ra_hours=5.4, dec_degrees=-69.8),
        device_id=device,
        scheduled_start=start,
        status=status,
        mosaic=Mosaic(group_id=group or None, grid_rows=2 if group else 0, grid_columns=2 if group else 0),
        planned_duration_seconds=600,
        actual_started_at="2026-09-21T20:00:00" if status != SessionStatus.PLANNED else None,
        outcome="Completed" if status == SessionStatus.DONE else "",
    )


def _mosaic() -> list[Session]:
    return [
        _session("pane-1", "2026-09-21T20:00:00", name="LMC pane 1", group="lmc"),
        _session("pane-2", "2026-09-21T20:12:00", name="LMC pane 2", group="lmc"),
        _session("pane-3", "2026-09-21T20:24:00", name="LMC pane 3", group="lmc", status=SessionStatus.DONE),
    ]


def test_copy_session_name() -> None:
    _assert(copy_session_name("Orion") == "Orion copy", copy_session_name("Orion"))
    _assert(copy_session_name("Orion copy") == "Orion copy", "already a copy")
    _assert(copy_session_name("") == "Session copy", copy_session_name(""))


def test_scope_defaults_to_whole_mosaic() -> None:
    mosaic = _mosaic()
    _assert(duplicate_session_scope(mosaic[0], mosaic, "") == "mosaic", "grouped default")
    _assert(duplicate_session_scope(mosaic[1], mosaic, "pane") == "pane", "expanded pane")
    _assert(duplicate_session_scope(mosaic[0], mosaic, "mosaic") == "mosaic", "explicit mosaic")
    solo = _session("orion", "2026-09-21T21:00:00", name="Orion")
    _assert(duplicate_session_scope(solo, [solo], "mosaic") == "session", "solo cannot mosaic")
    _assert(duplicate_session_scope(solo, [solo], "pane") == "session", "solo cannot pane")


def test_session_duplicate_is_planned_copy() -> None:
    source = _session("orion", "2026-09-21T21:00:00", name="Orion", status=SessionStatus.DONE)
    scope, drafts = duplicate_session_drafts(source, [source], mode="session", scheduled_start="2026-09-22T22:00")
    _assert(scope == "session", scope)
    _assert(len(drafts) == 1, drafts)
    copy = drafts[0]
    _assert(copy.id != source.id, copy.id)
    _assert(copy.name == "Orion copy", copy.name)
    _assert(copy.status == SessionStatus.PLANNED, copy.status)
    _assert(copy.mosaic.group_id is None, copy.mosaic)
    _assert(copy.actual_started_at is None, copy.actual_started_at)
    _assert(copy.outcome == "", copy.outcome)
    _assert(copy.scheduled_start == "2026-09-22T22:00", copy.scheduled_start)
    _assert(source.name == "Orion", "original name stays")


def test_mosaic_duplicate_copies_every_pane() -> None:
    mosaic = _mosaic()
    scope, drafts = duplicate_session_drafts(
        mosaic[1], mosaic, mode="mosaic", scheduled_start="2026-09-22T21:00"
    )
    _assert(scope == "mosaic", scope)
    _assert(len(drafts) == 3, len(drafts))
    names = [item.name for item in drafts]
    _assert(names == ["LMC pane 1", "LMC pane 2", "LMC pane 3"], names)
    groups = {item.mosaic.group_id for item in drafts}
    _assert(len(groups) == 1, groups)
    _assert("lmc" not in groups, groups)
    _assert(all(item.status == SessionStatus.PLANNED for item in drafts), [item.status for item in drafts])
    _assert({item.id for item in drafts}.isdisjoint({"pane-1", "pane-2", "pane-3"}), [item.id for item in drafts])
    _assert(mosaic[0].mosaic.group_id == "lmc", "original group stays")
    _assert(mosaic[2].status == SessionStatus.DONE, "original completed pane stays")
    timed = stagger_mosaic_sessions(drafts, datetime(2026, 9, 22, 21, 0), HardwareProfile())
    starts = [item.scheduled_start for item in timed]
    _assert(starts[0].startswith("2026-09-22T21:00"), starts)
    _assert(starts[0] < starts[1] < starts[2], starts)


def test_pane_duplicate_stays_in_the_mosaic() -> None:
    mosaic = _mosaic()
    scope, drafts = duplicate_session_drafts(
        mosaic[1], mosaic, mode="pane", name="LMC pane 2 extra", scheduled_start="2026-09-21T21:00"
    )
    _assert(scope == "pane", scope)
    _assert(len(drafts) == 1, drafts)
    copy = drafts[0]
    _assert(copy.mosaic.group_id == "lmc", copy.mosaic)
    _assert(copy.name == "LMC pane 2 extra", copy.name)
    _assert(copy.device_id == "scope-1", copy.device_id)
    _assert(copy.target.ra_hours == mosaic[1].target.ra_hours, copy.target)


if __name__ == "__main__":
    test_copy_session_name()
    test_scope_defaults_to_whole_mosaic()
    test_session_duplicate_is_planned_copy()
    test_mosaic_duplicate_copies_every_pane()
    test_pane_duplicate_stays_in_the_mosaic()
    print("ok")
