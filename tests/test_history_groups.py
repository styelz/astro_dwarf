from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    Mosaic,
    Session,
    Target,
    history_from_dict,
    history_record_for_run,
    to_dict,
)
from astro_dwarf.qt_backend import AppBackend
from astro_dwarf.services import is_mosaic_pane_name, mosaic_group_title


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_history_record_stores_mosaic_group() -> None:
    session = Session(
        name="LMC pane 1",
        target=Target(name="LMC pane 1"),
        device_id="dev-1",
        scheduled_start="2026-09-21T20:00",
        mosaic=Mosaic(rows=2, columns=1, group_id="lmc-abc"),
        outcome="Completed",
    )
    record = history_record_for_run(session, actual_duration_seconds=12, captured_frame_count=8)
    _assert(record.mosaic_group_id == "lmc-abc", record.mosaic_group_id)
    restored = history_from_dict(to_dict(record))
    _assert(restored.mosaic_group_id == "lmc-abc", restored.mosaic_group_id)


def test_history_from_dict_defaults_missing_group() -> None:
    record = history_from_dict(
        {
            "session_id": "s1",
            "device_id": "d1",
            "target_name": "Orion",
            "scheduled_start": "2026-09-21T20:00",
            "actual_started_at": None,
            "actual_ended_at": None,
            "planned_duration_seconds": 10,
            "actual_duration_seconds": 9,
            "frame_count": 4,
            "outcome": "Completed",
        }
    )
    _assert(record.mosaic_group_id == "", repr(record.mosaic_group_id))


def test_decorate_history_groups_clusters_pane_rows() -> None:
    items = [
        {"id": "h-2", "group_key": "lmc|dev-1|2026-09-20"},
        {"id": "h-1", "group_key": "lmc|dev-1|2026-09-20"},
        {"id": "solo", "group_key": "session:solo"},
    ]
    out = AppBackend._decorate_history_groups(None, items)
    grouped = [item for item in out if item["id"] != "solo"]
    _assert(all(item["is_grouped"] for item in grouped), grouped)
    _assert(all(item["pane_count"] == 2 for item in grouped), grouped)
    solo = next(item for item in out if item["id"] == "solo")
    _assert(not solo["is_grouped"], solo)
    _assert(solo["group_key"] == "session:solo", solo["group_key"])
    _assert(solo["pane_count"] == 1, solo["pane_count"])


def test_old_pane_names_share_fallback_group() -> None:
    _assert(is_mosaic_pane_name("Pane 1"), "Pane 1")
    _assert(is_mosaic_pane_name("LMC pane 3"), "LMC pane 3")
    _assert(not is_mosaic_pane_name("Gamma Muscae"), "Gamma Muscae")
    title = mosaic_group_title("Pane 1")
    _assert(title == "Mosaic", title)
    key = f"{title}|dev-1|2026-09-20"
    rows = [
        {"id": "a", "group_key": key},
        {"id": "b", "group_key": key},
        {"id": "c", "group_key": key},
    ]
    out = AppBackend._decorate_history_groups(None, rows)
    _assert(all(item["pane_count"] == 3 and item["is_grouped"] for item in out), out)


def test_history_calendar_uses_observing_night() -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Australia/Sydney")
    done = AppBackend.history_calendar_placement(
        scheduled_start="2026-09-22T01:30:00+10:00",
        actual_started_at="2026-09-22T01:30:00+10:00",
        actual_ended_at="2026-09-22T02:00:00+10:00",
        actual_duration_seconds=1800,
        planned_duration_seconds=3600,
        outcome="Completed",
        ok=True,
        zone=zone,
        cutoff_hour=12,
    )
    _assert(done["observing_date"] == "2026-09-21", done)
    _assert(done["start_time"] == "01:30", done)
    _assert(done["status"] == "done" and done["from_history"], done)
    _assert(done["end_epoch_ms"] > done["start_epoch_ms"], done)
    _assert(
        datetime.fromtimestamp(done["start_epoch_ms"] / 1000, zone).hour == 1,
        done,
    )
    stopped = AppBackend.history_calendar_placement(
        scheduled_start="2026-09-21T22:00:00+10:00",
        actual_started_at="2026-09-21T22:00:00+10:00",
        actual_ended_at=None,
        actual_duration_seconds=600,
        planned_duration_seconds=3600,
        outcome="Stopped by user",
        ok=False,
        zone=zone,
        cutoff_hour=12,
    )
    _assert(stopped["observing_date"] == "2026-09-21", stopped)
    _assert(stopped["status"] == "skipped", stopped)
    _assert(stopped["end_epoch_ms"] == stopped["start_epoch_ms"] + 600_000, stopped)
    failed = AppBackend.history_calendar_placement(
        scheduled_start="2026-09-21T22:00:00+10:00",
        actual_started_at="2026-09-21T22:00:00+10:00",
        actual_ended_at="2026-09-21T22:05:00+10:00",
        actual_duration_seconds=300,
        planned_duration_seconds=3600,
        outcome="plate solve failed",
        ok=False,
        zone=zone,
        cutoff_hour=12,
    )
    _assert(failed["status"] == "error", failed)


if __name__ == "__main__":
    test_history_record_stores_mosaic_group()
    test_history_from_dict_defaults_missing_group()
    test_decorate_history_groups_clusters_pane_rows()
    test_old_pane_names_share_fallback_group()
    test_history_calendar_uses_observing_night()
    print("ok")
