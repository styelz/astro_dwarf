"""Seed an isolated schedule library for the HUD scale test.

Writes templates, sessions, and history through SessionStore. Does not print
device records. Shapes:

  spread        100 templates, 110 sessions, 100 history rows
  crowded-night the same counts, every session and history row on one night
  huge-mosaic   100 templates and 100 panes in one mosaic group
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    CameraSettings,
    HistoryRecord,
    Mosaic,
    Session,
    SessionStatus,
    SessionTemplate,
    Target,
)
from astro_dwarf.storage import SessionStore

PREFIX = "perf-scale"
NEEDLE = "quasar-needle"
NOTE = (
    "Scale-test note with a long haystack for history search. "
    "The unique token is quasar-needle so a keystroke filter has something to match."
)


def _copy_devices(store: SessionStore, source: Path) -> str:
    folder = source / "devices"
    if folder.is_dir():
        for path in folder.glob("*.json"):
            dest = store.devices.folder / path.name
            shutil.copyfile(path, dest)
    store.devices._by_id = None
    devices = store.devices.all()
    if not devices:
        devices = [store.seed_device()]
    return devices[0].id


def _template(index: int, *, group_id: str = "", pane: int = 0, panes: int = 0) -> SessionTemplate:
    if group_id:
        name = f"Perf Mosaic pane {pane} of {panes}"
        mosaic = Mosaic(group_id=group_id, grid_rows=2, grid_columns=max(1, panes // 2), row=((pane - 1) // 5) + 1, column=((pane - 1) % 5) + 1)
    else:
        name = f"Perf Target {index:03d}"
        mosaic = Mosaic()
    return SessionTemplate(
        id=f"{PREFIX}-tpl-{index:03d}",
        name=name,
        target=Target(name=name, ra_hours=(index % 24) + 0.25, dec_degrees=((index * 3) % 120) - 60),
        camera=CameraSettings(exposure_seconds=30, gain=60, frame_count=20),
        mosaic=mosaic,
        notes="" if index % 7 else NOTE,
    )


def _session(
    index: int,
    device_id: str,
    start: datetime,
    *,
    group_id: str = "",
    pane: int = 0,
    panes: int = 0,
    hours: float = 1.0,
) -> Session:
    if group_id:
        name = f"Perf Group pane {pane} of {panes}"
        mosaic = Mosaic(group_id=group_id, grid_rows=2, grid_columns=max(1, panes // 2), row=((pane - 1) // 5) + 1, column=((pane - 1) % 5) + 1)
    else:
        name = f"Perf Session {index:03d}"
        mosaic = Mosaic()
    return Session(
        id=f"{PREFIX}-ses-{index:03d}",
        name=name,
        target=Target(name=name, ra_hours=(index % 24) + 0.5, dec_degrees=((index * 5) % 140) - 70),
        device_id=device_id,
        scheduled_start=start.replace(microsecond=0).isoformat(),
        camera=CameraSettings(exposure_seconds=30, gain=60, frame_count=15),
        mosaic=mosaic,
        status=SessionStatus.PLANNED,
        planned_duration_seconds=hours * 3600,
        notes="" if index % 9 else NOTE,
    )


def _history(index: int, session: Session, start: datetime) -> HistoryRecord:
    ok = index % 2 == 0
    began = start + timedelta(minutes=2)
    ended = began + timedelta(minutes=50 if ok else 12)
    return HistoryRecord(
        id=f"{PREFIX}-hist-{index:03d}",
        session_id=session.id,
        device_id=session.device_id,
        target_name=session.target.name,
        scheduled_start=session.scheduled_start,
        actual_started_at=began.replace(microsecond=0).isoformat(),
        actual_ended_at=ended.replace(microsecond=0).isoformat(),
        planned_duration_seconds=session.planned_duration_seconds,
        actual_duration_seconds=(ended - began).total_seconds(),
        frame_count=session.camera.frame_count,
        captured_frame_count=session.camera.frame_count if ok else 3,
        outcome="completed" if ok else "failed",
        recorded_at=(ended + timedelta(seconds=index)).isoformat(),
        summary=f"{session.camera.frame_count} x {session.camera.exposure_seconds:g}s",
        notes=NOTE if index % 5 == 0 else "",
        exposure_seconds=session.camera.exposure_seconds,
        mosaic_panes=panes_of(session),
        mosaic_group_id=str(session.mosaic.group_id or ""),
        step_seconds={"slew": 40, "expose": 600 if ok else 80},
    )


def panes_of(session: Session) -> int:
    return 10 if session.mosaic.group_id else 1


def _save_templates(store: SessionStore, count: int = 100) -> None:
    for index in range(1, 91):
        store.templates.save(_template(index))
    group = f"{PREFIX}-tpl-group"
    for pane in range(1, 11):
        store.templates.save(_template(90 + pane, group_id=group, pane=pane, panes=10))
    stored = len(list(store.templates.folder.glob("*.json")))
    if stored != count:
        raise SystemExit(f"expected {count} templates, wrote {stored}")


def seed_spread(root: Path, source: Path) -> dict[str, int]:
    store = SessionStore(root)
    device_id = _copy_devices(store, source)
    _save_templates(store)
    night = datetime(2026, 3, 1, 21, 0, 0)
    sessions: list[Session] = []
    index = 1
    for offset in range(70):
        sessions.append(_session(index, device_id, night + timedelta(days=offset)))
        index += 1
    overlap = datetime(2026, 6, 15, 21, 0, 0)
    for slot in range(20):
        sessions.append(_session(index, device_id, overlap + timedelta(minutes=2 * slot), hours=3))
        index += 1
    for group_number, day in ((1, 80), (2, 81)):
        group = f"{PREFIX}-ses-group-{group_number}"
        start = datetime(2026, 3, 1, 22, 0, 0) + timedelta(days=day)
        for pane in range(1, 11):
            sessions.append(_session(index, device_id, start + timedelta(minutes=pane), group_id=group, pane=pane, panes=10))
            index += 1
    for session in sessions:
        store.sessions.save(session)
    for hist_index, session in enumerate(sessions[:100], start=1):
        start = datetime.fromisoformat(session.scheduled_start)
        store.history.save(_history(hist_index, session, start))
    return _counts(store)


def seed_crowded(root: Path, source: Path) -> dict[str, int]:
    store = SessionStore(root)
    device_id = _copy_devices(store, source)
    _save_templates(store)
    night = datetime(2026, 6, 15, 21, 0, 0)
    sessions = [
        _session(index, device_id, night + timedelta(seconds=20 * (index - 1)), hours=4)
        for index in range(1, 111)
    ]
    for session in sessions:
        store.sessions.save(session)
    for hist_index, session in enumerate(sessions[:100], start=1):
        store.history.save(_history(hist_index, session, night))
    return _counts(store)


def seed_huge_mosaic(root: Path, source: Path) -> dict[str, int]:
    store = SessionStore(root)
    device_id = _copy_devices(store, source)
    _save_templates(store)
    group = f"{PREFIX}-huge"
    start = datetime(2026, 7, 1, 21, 0, 0)
    sessions = []
    for pane in range(1, 101):
        sessions.append(
            _session(pane, device_id, start + timedelta(minutes=pane), group_id=group, pane=pane, panes=100, hours=0.5)
        )
    for session in sessions:
        store.sessions.save(session)
    for hist_index, session in enumerate(sessions, start=1):
        store.history.save(_history(hist_index, session, start))
    return _counts(store)


def _counts(store: SessionStore) -> dict[str, int]:
    return {
        "templates": len(list(store.templates.folder.glob("*.json"))),
        "sessions": len(list(store.sessions.folder.glob("*.json"))),
        "history": len(list(store.history.folder.glob("*.json"))),
    }


SHAPES = {
    "spread": seed_spread,
    "crowded-night": seed_crowded,
    "huge-mosaic": seed_huge_mosaic,
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in SHAPES:
        print("usage: seed_scale_library.py spread|crowded-night|huge-mosaic ROOT", file=sys.stderr)
        return 2
    root = Path(args[1])
    counts = SHAPES[args[0]](root, ROOT / "data")
    print(f"{args[0]} {counts['templates']} templates, {counts['sessions']} sessions, {counts['history']} history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
