from __future__ import annotations

import json
import os
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Generic, Iterable, TypeVar

from .domain import (
    Device,
    HistoryRecord,
    Session,
    SessionStatus,
    SessionTemplate,
    device_from_dict,
    history_from_dict,
    session_from_dict,
    template_from_dict,
    to_dict,
)

T = TypeVar("T")


class JsonRepository(Generic[T]):
    def __init__(self, folder: Path, loader: Callable[[dict], T]):
        self.folder = folder
        self.loader = loader
        folder.mkdir(parents=True, exist_ok=True)

    def all(self) -> list[T]:
        values: list[T] = []
        for path in sorted(self.folder.glob("*.json")):
            try:
                values.append(self.loader(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError):
                continue
        return values

    def get(self, item_id: str) -> T | None:
        path = self.folder / f"{item_id}.json"
        if not path.exists():
            return None
        return self.loader(json.loads(path.read_text(encoding="utf-8")))

    def save(self, value: T) -> T:
        item_id = getattr(value, "id")
        path = self.folder / f"{item_id}.json"
        temporary = path.with_suffix(f".{os.getpid()}.{id(value)}.tmp")
        temporary.write_text(json.dumps(to_dict(value), indent=2), encoding="utf-8")
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 7:
                    temporary.unlink(missing_ok=True)
                    raise
                time.sleep(0.01 * (attempt + 1))
        return value

    def delete(self, item_id: str) -> bool:
        path = self.folder / f"{item_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def clear(self) -> None:
        for path in self.folder.glob("*.json"):
            try:
                path.unlink()
            except OSError:
                continue


class SessionStore:
    VALID_TRANSITIONS = {
        SessionStatus.PLANNED: {SessionStatus.RUNNING, SessionStatus.SKIPPED},
        SessionStatus.RUNNING: {SessionStatus.DONE, SessionStatus.ERROR, SessionStatus.PLANNED},
        SessionStatus.ERROR: {SessionStatus.PLANNED},
        SessionStatus.SKIPPED: {SessionStatus.PLANNED},
        SessionStatus.DONE: set(),
    }

    def __init__(self, root: Path):
        self.root = root
        self.devices = JsonRepository(root / "devices", device_from_dict)
        self.templates = JsonRepository(root / "templates", template_from_dict)
        self.sessions = JsonRepository(root / "sessions", session_from_dict)
        self.history = JsonRepository(root / "history", history_from_dict)

    def transition(self, session_id: str, status: SessionStatus, **changes) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        if status not in self.VALID_TRANSITIONS[session.status]:
            raise ValueError(f"Cannot move {session.status} to {status}")
        session = replace(session, status=status, **changes)
        return self.sessions.save(session)

    def upcoming(self, device_id: str | None = None) -> list[Session]:
        values = [s for s in self.sessions.all() if s.status == SessionStatus.PLANNED]
        if device_id:
            values = [s for s in values if s.device_id == device_id]
        return sorted(values, key=lambda s: s.scheduled_start)

    def for_day(self, day: str, cutoff_hour: int = 0) -> list[Session]:
        def observing_day(session: Session) -> str:
            value = datetime.fromisoformat(session.scheduled_start)
            if value.hour < cutoff_hour:
                value -= timedelta(days=1)
            return value.date().isoformat()

        return sorted(
            [s for s in self.sessions.all() if observing_day(s) == day],
            key=lambda s: s.scheduled_start,
        )

    def recover_running(self) -> list[Session]:
        recovered: list[Session] = []
        for session in self.sessions.all():
            if session.status == SessionStatus.RUNNING:
                recovered.append(
                    self.transition(
                        session.id,
                        SessionStatus.PLANNED,
                        current_step="Recovered after restart",
                        actual_started_at=None,
                    )
                )
        return recovered

    def clone_template(self, template: SessionTemplate, device_id: str, start: datetime) -> Session:
        return Session(
            name=template.name,
            target=template.target,
            device_id=device_id,
            scheduled_start=start.isoformat(timespec="minutes"),
            template_id=template.id,
            camera=template.camera,
            workflow=template.workflow,
            mosaic=template.mosaic,
            notes=template.notes,
        )

    def seed_device(self) -> Device:
        current = self.devices.all()
        if current:
            return current[0]
        return self.devices.save(Device(name="Dwarf 3"))

    def import_old_sessions(self, paths: Iterable[Path], device_id: str) -> tuple[int, int]:
        imported = failed = 0
        for path in paths:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))["command"]
                meta = raw["id_command"]
                goto = raw.get("goto_manual", {})
                camera = raw.get("setup_camera", {})
                start = f"{meta['date']}T{meta['time'][:5]}"
                from .domain import CameraSettings, Target, Workflow

                session = Session(
                    name=meta.get("description") or goto.get("target") or path.stem,
                    target=Target(
                        name=goto.get("target", meta.get("description", path.stem)),
                        ra_hours=float(goto["ra_coord"]) if goto.get("ra_coord") is not None else None,
                        dec_degrees=float(goto["dec_coord"]) if goto.get("dec_coord") is not None else None,
                    ),
                    device_id=device_id,
                    scheduled_start=start,
                    camera=CameraSettings(
                        exposure_seconds=float(camera.get("exposure", 15)),
                        gain=int(float(camera.get("gain", 80))),
                        frame_count=int(camera.get("count", 1)),
                    ),
                    workflow=Workflow(
                        calibrate=bool(raw.get("calibration", {}).get("do_action", False)),
                        autofocus=bool(raw.get("auto_focus", {}).get("do_action", False)),
                        infinite_focus=bool(raw.get("infinite_focus", {}).get("do_action", False)),
                        polar_align=bool(raw.get("eq_solving", {}).get("do_action", False)),
                        goto=bool(goto.get("do_action", False)),
                    ),
                )
                self.sessions.save(session)
                imported += 1
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                failed += 1
        return imported, failed
