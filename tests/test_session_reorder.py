from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import Mosaic, Session, SessionStatus, Target, TargetKind
from astro_dwarf.services import insert_reorder_block, planned_reorder_block, reorder_anchor_id


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
    )


def _mosaic() -> list[Session]:
    return [
        _session("pane-1", "2026-09-21T20:00:00", name="LMC pane 1", group="lmc"),
        _session("pane-2", "2026-09-21T20:12:00", name="LMC pane 2", group="lmc"),
        _session("pane-3", "2026-09-21T20:24:00", name="LMC pane 3", group="lmc"),
    ]


def test_planned_block_moves_every_pane() -> None:
    mosaic = _mosaic()
    extra = _session("orion", "2026-09-21T21:00:00", name="Orion")
    block = planned_reorder_block(mosaic + [extra], mosaic[0])
    _assert(block is not None, "planned mosaic can move")
    _assert([item.id for item in block] == ["pane-1", "pane-2", "pane-3"], [item.id for item in block])


def test_running_pane_blocks_the_group() -> None:
    mosaic = _mosaic()
    mosaic[0] = _session(
        "pane-1", "2026-09-21T20:00:00", name="LMC pane 1", group="lmc", status=SessionStatus.RUNNING
    )
    _assert(planned_reorder_block(mosaic, mosaic[1]) is None, "running sibling blocks reorder")


def test_insert_mosaic_after_solo_keeps_panes_together() -> None:
    mosaic = _mosaic()
    orion = _session("orion", "2026-09-21T19:00:00", name="Orion")
    ordered = insert_reorder_block(mosaic + [orion], mosaic, "")
    _assert([item.id for item in ordered] == ["orion", "pane-1", "pane-2", "pane-3"], [item.id for item in ordered])


def test_insert_mosaic_before_solo_keeps_panes_together() -> None:
    mosaic = _mosaic()
    orion = _session("orion", "2026-09-21T21:00:00", name="Orion")
    ordered = insert_reorder_block([orion] + mosaic, mosaic, "orion")
    _assert([item.id for item in ordered] == ["pane-1", "pane-2", "pane-3", "orion"], [item.id for item in ordered])


def test_drop_before_later_pane_still_anchors_on_first_pane() -> None:
    mosaic = _mosaic()
    orion = _session("orion", "2026-09-21T21:00:00", name="Orion")
    _assert(reorder_anchor_id(mosaic, mosaic[2], set()) == "pane-1", "insert before the whole mosaic")
    ordered = insert_reorder_block(mosaic + [orion], [orion], "pane-3")
    _assert([item.id for item in ordered] == ["orion", "pane-1", "pane-2", "pane-3"], [item.id for item in ordered])


if __name__ == "__main__":
    test_planned_block_moves_every_pane()
    test_running_pane_blocks_the_group()
    test_insert_mosaic_after_solo_keeps_panes_together()
    test_insert_mosaic_before_solo_keeps_panes_together()
    test_drop_before_later_pane_still_anchors_on_first_pane()
    print("ok")
