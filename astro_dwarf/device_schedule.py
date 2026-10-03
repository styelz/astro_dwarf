"""On-device shooting schedule: which sessions the telescope can run alone.

The firmware schedule is one deep-sky night plan (module 13). Polar alignment,
infinity focus, a wide lens, a custom mosaic grid, and solar targets stay on
the computer. A session marked pending or shooting here must not also be
started by the PC scheduler.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .domain import (
    Camera,
    Session,
    SessionAction,
    SessionStatus,
    TargetKind,
    firmware_exposure_name,
    session_action_value,
)

SCOPE_OWNS = frozenset({"pending", "shooting", "stale"})

_SCHEDULE_STATE = {
    0: "initialized",
    1: "pending",
    2: "shooting",
    3: "completed",
    4: "expired",
}
_SCHEDULE_RESULT = {
    0: "pending",
    1: "completed",
    2: "partial",
    3: "failed",
}
_TASK_STATE = {
    0: "idle",
    1: "shooting",
    2: "success",
    3: "failed",
    4: "interrupted",
}
_SCHEDULE_ERRORS = {
    -16300: "This schedule is for a different telescope",
    -16301: "A session is too short for the telescope",
    -16302: "That time is already on the telescope",
    -16305: "The telescope could not store the schedule",
    -16306: "The schedule password was rejected",
    -16307: "The telescope is already shooting that schedule",
    -16308: "The start time is too far ahead for the telescope",
    -16309: "The telescope is busy",
    -16310: "The telescope interrupted the schedule",
    -16311: "The schedule is not synced",
}
SCHEDULE_BUSY_CODES = frozenset({-16307, -16309})
CODE_TIME_CONFLICT = -16302


def device_schedule_id_for(device_id: str) -> str:
    return f"astro-dwarf-{device_id}"


def schedule_state_name(value: Any) -> str:
    try:
        return _SCHEDULE_STATE.get(int(value), "pending")
    except (TypeError, ValueError):
        return "pending"


def schedule_result_name(value: Any) -> str:
    try:
        return _SCHEDULE_RESULT.get(int(value), "pending")
    except (TypeError, ValueError):
        return "pending"


def task_state_name(value: Any) -> str:
    try:
        return _TASK_STATE.get(int(value), "idle")
    except (TypeError, ValueError):
        return "idle"


def schedule_error_text(code: Any) -> str:
    try:
        number = int(code)
    except (TypeError, ValueError):
        return "The telescope did not accept the schedule"
    return _SCHEDULE_ERRORS.get(number, f"The telescope rejected the schedule ({number})")


def host_should_start(session: Session) -> bool:
    """False when this planned session is already handed to the telescope."""
    if session.status != SessionStatus.PLANNED:
        return False
    if session.device_schedule_id and session.device_schedule_state in SCOPE_OWNS:
        return False
    return True


def next_host_session(entries: list[tuple[Session, bool]]) -> tuple[Session | None, bool]:
    """Pick the PC session to start, and whether any session is already due.

    ``entries`` are ``(session, is_due)`` in start order. A due session that
    belongs to the telescope holds the queue so a later computer session does
    not start on top of it. ``is_due`` is still true in that case so a leftover
    mosaic can yield the mount.
    """
    session: Session | None = None
    due = False
    scope_blocks = False
    for candidate, is_due in entries:
        if not is_due:
            break
        due = True
        if not host_should_start(candidate):
            scope_blocks = True
            continue
        if not scope_blocks:
            session = candidate
        break
    return session, due


def session_schedule_blocker(session: Session) -> str:
    """Why this session stays on the computer. Empty when the telescope can run it."""
    if session_action_value(session) != SessionAction.ASTRO.value:
        return "Photo, video, burst, and timelapse stay on this computer"
    if session.status != SessionStatus.PLANNED:
        return "Only a planned session can be copied to the telescope"
    kind = session.target.kind.value if isinstance(session.target.kind, TargetKind) else str(session.target.kind)
    if kind != TargetKind.EQUATORIAL.value:
        return "Solar-system targets stay on this computer"
    if session.target.ra_hours is None or session.target.dec_degrees is None:
        return "This target has no sky position"
    camera = session.camera.camera.value if isinstance(session.camera.camera, Camera) else str(session.camera.camera)
    if camera == Camera.WIDE.value:
        return "Wide-camera sessions stay on this computer"
    try:
        if int(session.camera.binning or 1) >= 2:
            return "2K binning stays on this computer"
    except (TypeError, ValueError):
        return "2K binning stays on this computer"
    if session.workflow.polar_align:
        return "Polar alignment stays on this computer"
    if session.workflow.infinite_focus:
        return "Infinity focus stays on this computer"
    try:
        if float(session.workflow.wait_before_seconds or 0) > 0:
            return "A wait before the shot stays on this computer"
    except (TypeError, ValueError):
        return "A wait before the shot stays on this computer"
    if session.mosaic.imported_plan:
        return "A custom mosaic stays on this computer"
    return ""


def schedule_fingerprint(session: Session) -> tuple[Any, ...]:
    """Fields that change what the telescope would shoot."""
    kind = session.target.kind.value if isinstance(session.target.kind, TargetKind) else str(session.target.kind)
    camera = session.camera.camera.value if isinstance(session.camera.camera, Camera) else str(session.camera.camera)
    return (
        session_action_value(session),
        session.burst_count,
        session.burst_interval_seconds,
        session.video_seconds,
        session.timelapse_interval_seconds,
        session.timelapse_video_seconds,
        session.scheduled_start,
        session.target.name,
        kind,
        session.target.ra_hours,
        session.target.dec_degrees,
        camera,
        session.camera.exposure_seconds,
        session.camera.gain,
        session.camera.frame_count,
        session.camera.binning,
        session.camera.ir_filter,
        session.workflow.calibrate,
        session.workflow.autofocus,
        session.workflow.infinite_focus,
        session.workflow.polar_align,
        session.workflow.wait_before_seconds,
        session.mosaic.rows,
        session.mosaic.columns,
        session.mosaic.horizontal_scale,
        session.mosaic.vertical_scale,
        session.mosaic.rotation_degrees,
        session.mosaic.grid_rows,
        session.mosaic.grid_columns,
    )


def carry_device_schedule(existing: Session | None, updated: Session) -> tuple[Session, bool]:
    """Keep or drop the telescope mark when a planned session is saved.

    The second value is true when the stored copy should be rewritten.
    Status changes driven by a run are left alone.
    """
    from dataclasses import replace

    if existing is None or not existing.device_schedule_id:
        return updated, False
    if existing.status != SessionStatus.PLANNED or updated.status != SessionStatus.PLANNED:
        return replace(
            updated,
            device_schedule_id=existing.device_schedule_id,
            device_schedule_state=existing.device_schedule_state,
        ), False
    if existing.device_id != updated.device_id:
        return replace(updated, device_schedule_id="", device_schedule_state=""), True
    if schedule_fingerprint(existing) == schedule_fingerprint(updated):
        return replace(
            updated,
            device_schedule_id=existing.device_schedule_id,
            device_schedule_state=existing.device_schedule_state,
        ), False
    if session_schedule_blocker(updated):
        return replace(updated, device_schedule_id="", device_schedule_state=""), True
    return replace(
        updated,
        device_schedule_id=existing.device_schedule_id,
        device_schedule_state="stale",
    ), True


def _parse_start(value: str) -> datetime:
    text = str(value or "").replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def session_span_seconds(session: Session) -> float:
    try:
        planned = float(session.planned_duration_seconds or 0)
    except (TypeError, ValueError):
        planned = 0
    if planned > 0:
        return planned
    try:
        frames = max(1, int(session.camera.frame_count or 1))
    except (TypeError, ValueError):
        frames = 1
    try:
        exposure = max(1.0, float(session.camera.exposure_seconds or 1))
    except (TypeError, ValueError):
        exposure = 1.0
    return frames * exposure + 180.0


def _task_payload(session: Session, start: datetime, end: datetime) -> dict[str, Any]:
    layout = session.mosaic.firmware_layout()
    if layout is None:
        mosaic = False
        horizontal, vertical = 100, 100
    else:
        _columns, _rows, horizontal, vertical = layout
        mosaic = True
    try:
        rotation = int(round(float(session.mosaic.rotation_degrees or 0)))
    except (TypeError, ValueError):
        rotation = 0
    try:
        gain_name = str(int(session.camera.gain))
    except (TypeError, ValueError):
        gain_name = "0"
    try:
        frames = max(1, int(session.camera.frame_count or 1))
    except (TypeError, ValueError):
        frames = 1
    return {
        "name": session.target.name or session.name,
        "ra": float(session.target.ra_hours),
        "dec": float(session.target.dec_degrees),
        "startTime": int(start.timestamp()),
        "endTime": int(end.timestamp()),
        "shutterName": firmware_exposure_name(session.camera.exposure_seconds),
        "gainName": gain_name,
        "count": frames,
        "stacked": frames,
        "filterModeName": str(session.camera.ir_filter or ""),
        "schedule_task_id": session.id,
        "isMosaicMode": mosaic,
        "horizontalScale": int(horizontal),
        "verticalScale": int(vertical),
        "rotation": rotation if rotation else -1,
    }


def plan_device_schedule(
    device_id: str,
    device_name: str,
    latitude: float,
    longitude: float,
    sessions: list[Session],
) -> tuple[dict[str, Any] | None, list[tuple[Session, str]]]:
    """Build one firmware schedule and the sessions that stay on the computer.

    Overlapping eligible sessions are reported on the later one and left out.
    An empty plan means there is nothing to push.
    """
    blocked: list[tuple[Session, str]] = []
    chosen: list[tuple[Session, datetime, datetime]] = []
    ordered = sorted(sessions, key=lambda item: item.scheduled_start)
    for session in ordered:
        reason = session_schedule_blocker(session)
        if reason:
            blocked.append((session, reason))
            continue
        start = _parse_start(session.scheduled_start)
        end = start + _span(session)
        if chosen and start < chosen[-1][2]:
            blocked.append((session, "Overlaps an earlier session on this telescope"))
            continue
        chosen.append((session, start, end))
    if not chosen:
        return None, blocked
    calibrate = all(item.workflow.calibrate for item, _start, _end in chosen)
    focus = all(item.workflow.autofocus for item, _start, _end in chosen)
    first = chosen[0][1]
    last = chosen[-1][2]
    name = str(device_name or "").strip() or "Astro Dwarf"
    schedule = {
        "scheduleId": device_schedule_id_for(device_id),
        "scheduleName": f"{name} {first:%Y-%m-%d}",
        "startTime": int(first.timestamp()),
        "endTime": int(last.timestamp()),
        "paramsMode": 0,
        "params": {
            "longitude": float(longitude),
            "latitude": float(latitude),
            "calibrationMode": 1 if calibrate else 0,
            "focusMode": 1 if focus else 0,
        },
        "shooting_tasks": [_task_payload(item, start, end) for item, start, end in chosen],
    }
    return schedule, blocked


def _span(session: Session) -> timedelta:
    return timedelta(seconds=session_span_seconds(session))


def _terminal_update(session: Session, state: str, outcome: str, status: str) -> dict[str, Any]:
    return {
        "id": session.id,
        "device_schedule_id": session.device_schedule_id,
        "device_schedule_state": state,
        "status": status,
        "outcome": outcome,
        "current_step": outcome,
    }


def _live_update(session: Session, state: str, step: str) -> dict[str, Any]:
    return {
        "id": session.id,
        "device_schedule_id": session.device_schedule_id or device_schedule_id_for(session.device_id),
        "device_schedule_state": state,
        "status": None,
        "outcome": session.outcome,
        "current_step": step,
    }


def _outcome_for_result(result: str, task_state: str, code: int | None = None) -> dict[str, str] | None:
    if task_state == "failed" or (result == "failed" and task_state != "success"):
        text = schedule_error_text(code) if code else "Failed on the telescope"
        return {"status": "error", "state": "completed", "outcome": text}
    if task_state == "interrupted":
        return {"status": "skipped", "state": "expired", "outcome": "Interrupted on the telescope"}
    if task_state == "success" or result == "completed":
        return {"status": "done", "state": "completed", "outcome": "Completed on the telescope"}
    if result == "partial":
        if task_state == "success":
            return {"status": "done", "state": "completed", "outcome": "Completed on the telescope"}
        return {"status": "done", "state": "completed", "outcome": "Partially completed on the telescope"}
    return None


def updates_for_task_notice(
    sessions: list[Session],
    *,
    task_id: str,
    task_state: str,
    code: int | None = None,
) -> list[dict[str, Any]]:
    task = str(task_id or "")
    if not task:
        return []
    updates: list[dict[str, Any]] = []
    for session in sessions:
        if session.id != task or session.status != SessionStatus.PLANNED:
            continue
        if task_state == "shooting":
            updates.append(_live_update(session, "shooting", "On the telescope"))
            continue
        if task_state in {"idle", "pending"}:
            updates.append(_live_update(session, "pending", session.current_step or "Waiting"))
            continue
        outcome = _outcome_for_result("", task_state, code)
        if outcome is None:
            continue
        updates.append(_terminal_update(session, outcome["state"], outcome["outcome"], outcome["status"]))
    return updates


def updates_for_schedule_notice(
    sessions: list[Session],
    *,
    schedule_id: str,
    state: str,
    result: str,
) -> list[dict[str, Any]]:
    """Apply a schedule-level result to every planned task still on that plan."""
    owner = str(schedule_id or "")
    if not owner:
        return []
    if state == "shooting":
        return []
    if state not in {"completed", "expired"} and result in {"", "pending"}:
        return []
    updates: list[dict[str, Any]] = []
    for session in sessions:
        if session.status != SessionStatus.PLANNED or session.device_schedule_id != owner:
            continue
        if state == "expired":
            updates.append(_terminal_update(session, "expired", "Schedule expired on the telescope", "skipped"))
            continue
        outcome = _outcome_for_result(result, "")
        if outcome is None:
            continue
        updates.append(_terminal_update(session, outcome["state"], outcome["outcome"], outcome["status"]))
    return updates


def updates_for_device_copy(
    sessions: list[Session],
    schedules: list[dict[str, Any]],
    schedule_id: str,
) -> list[dict[str, Any]]:
    """Match a GET_ALL reply to planned sessions for this telescope."""
    ours = next((item for item in schedules if str(item.get("schedule_id") or "") == schedule_id), None)
    updates: list[dict[str, Any]] = []
    if ours is None:
        for session in sessions:
            if session.status == SessionStatus.PLANNED and session.device_schedule_id == schedule_id:
                updates.append({
                    "id": session.id,
                    "device_schedule_id": "",
                    "device_schedule_state": "",
                    "status": None,
                    "outcome": session.outcome,
                    "current_step": session.current_step,
                })
        return updates
    tasks = {
        str(item.get("schedule_task_id") or ""): item
        for item in ours.get("tasks") or []
        if isinstance(item, dict)
    }
    schedule_state = schedule_state_name(ours.get("state"))
    schedule_result = schedule_result_name(ours.get("result"))
    for session in sessions:
        if session.status != SessionStatus.PLANNED:
            continue
        task = tasks.get(session.id)
        if task is None:
            if session.device_schedule_id == schedule_id:
                updates.append({
                    "id": session.id,
                    "device_schedule_id": "",
                    "device_schedule_state": "",
                    "status": None,
                    "outcome": session.outcome,
                    "current_step": session.current_step,
                })
            continue
        task_state = task_state_name(task.get("state"))
        try:
            code = int(task.get("code") or 0)
        except (TypeError, ValueError):
            code = 0
        if schedule_state == "expired":
            updates.append(_terminal_update(session, "expired", "Schedule expired on the telescope", "skipped"))
            continue
        outcome = _outcome_for_result(schedule_result if schedule_state == "completed" else "", task_state, code or None)
        if outcome is not None and (schedule_state == "completed" or task_state in {"success", "failed", "interrupted"}):
            marked = _terminal_update(session, outcome["state"], outcome["outcome"], outcome["status"])
            marked["device_schedule_id"] = schedule_id
            updates.append(marked)
            continue
        state = "shooting" if task_state == "shooting" or schedule_state == "shooting" else "pending"
        step = "On the telescope" if state == "shooting" else (session.current_step or "Waiting")
        update = _live_update(session, state, step)
        update["device_schedule_id"] = schedule_id
        updates.append(update)
    return updates
