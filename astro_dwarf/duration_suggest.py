from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .domain import CameraSettings, HardwareProfile, HistoryRecord, Mosaic, Session, Target, Workflow
from .services import DurationEngine

_STEP_BUCKETS = {
    "session start": "startup",
    "connecting": "startup",
    "starting worker": "startup",
    "joining capture": "startup",
    "closing previous capture": "startup",
    "entering astro mode": "startup",
    "entering solar mode": "startup",
    "entering solar-system mode": "startup",
    "preparing": "startup",
    "calibration exposure": "startup",
    "calibration gain": "startup",
    "calibration filter": "startup",
    "calibration binning": "startup",
    "set exposure": "startup",
    "set gain": "startup",
    "set filter": "startup",
    "set count": "startup",
    "set binning": "startup",
    "set mosaic count": "startup",
    "setting exposure": "startup",
    "setting gain": "startup",
    "setting ir filter": "startup",
    "setting frame count": "startup",
    "setting binning": "startup",
    "setting mosaic frame count": "startup",
    "auto focus": "autofocus",
    "infinity focus": "infinite_focus",
    "infinite focus": "infinite_focus",
    "infinity focus before polar alignment": "polar",
    "polar alignment": "polar",
    "calibration": "calibration",
    "calibrating": "calibration",
    "goto target": "slew",
    "goto solar target": "slew",
    "slewing": "slew",
    "slewing to solar target": "slew",
    "start mosaic": "imaging",
    "waiting for mosaic": "imaging",
    "starting mosaic": "imaging",
    "start wide capture": "imaging",
    "waiting for wide capture": "imaging",
    "imaging (wide)": "imaging",
    "waiting for wide stack": "imaging",
    "start capture": "imaging",
    "waiting for capture": "imaging",
    "imaging": "imaging",
    "waiting for stack": "imaging",
}

_FIELD_META = {
    "startup_seconds": {"label": "Startup", "min": 3.0, "max": 180.0, "threshold": 5.0},
    "slew_seconds": {"label": "Slew", "min": 5.0, "max": 180.0, "threshold": 5.0},
    "calibration_seconds": {"label": "Calibrate", "min": 20.0, "max": 400.0, "threshold": 8.0},
    "autofocus_seconds": {"label": "Autofocus", "min": 10.0, "max": 180.0, "threshold": 5.0},
    "infinite_focus_seconds": {"label": "Infinity", "min": 5.0, "max": 60.0, "threshold": 3.0},
    "polar_seconds": {"label": "Polar", "min": 30.0, "max": 600.0, "threshold": 10.0},
    "readout_seconds": {"label": "Readout", "min": 0.3, "max": 15.0, "threshold": 0.2},
}


def format_delta(seconds: float) -> str:
    sign = "over" if seconds > 0 else "under"
    amount = abs(seconds)
    if amount >= 3600:
        hours = amount / 3600
        text = f"{hours:.1f}h" if hours < 10 else f"{hours:.0f}h"
        return f"{text} {sign}"
    if amount >= 60:
        minutes = int(amount // 60)
        secs = int(round(amount % 60))
        if secs == 60:
            minutes += 1
            secs = 0
        return f"{minutes}m {secs}s {sign}" if secs else f"{minutes}m {sign}"
    return f"{int(round(amount))}s {sign}"


def suggest_hardware_profile(
    records: list[HistoryRecord],
    profile: HardwareProfile,
    sessions: dict[str, Session] | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    usable = []
    for record in records:
        if device_id and record.device_id != device_id:
            continue
        ctx = _context(record, profile, sessions or {})
        if ctx is not None:
            usable.append(ctx)
    empty: dict[str, Any] = {
        "available": False,
        "run_count": 0,
        "median_delta_seconds": 0,
        "summary": "",
        "note": "",
        "source": "",
        "changes": [],
        "change_text": "",
    }
    if not usable:
        return empty
    median_delta = _median([item["residual"] for item in usable])
    stepped = [item for item in usable if item["buckets"] and not item["resumed"]]
    if stepped:
        changes, source, note = _from_steps(stepped, profile)
    else:
        changes, source, note = _from_totals(usable, profile)
    count = len(usable)
    if not changes:
        if abs(median_delta) < 30:
            return {
                **empty,
                "run_count": count,
                "median_delta_seconds": round(median_delta, 1),
                "summary": (
                    f"{count} completed run{'s' if count != 1 else ''} match "
                    "the current duration profile."
                ),
            }
        return empty
    return {
        "available": True,
        "run_count": count,
        "median_delta_seconds": round(median_delta, 1),
        "summary": (
            f"{count} completed run{'s' if count != 1 else ''} ran a median "
            f"{format_delta(median_delta)} the current profile."
        ),
        "note": note,
        "source": source,
        "changes": changes,
        "change_text": "  ·  ".join(
            f"{item['label']} {item['current']} → {item['suggested']}"
            for item in changes
        ),
    }


def _context(record: HistoryRecord, profile: HardwareProfile, sessions: dict[str, Session]) -> dict[str, Any] | None:
    if str(record.outcome or "").strip().lower() != "completed":
        return None
    captured = record.captured_frame_count
    if captured is None:
        captured = record.frame_count
    try:
        captured = int(captured)
    except (TypeError, ValueError):
        return None
    planned_frames = max(0, int(record.frame_count or 0))
    if captured <= 0 or float(record.actual_duration_seconds or 0) < 30:
        return None
    if planned_frames and captured < max(1, round(0.8 * planned_frames)):
        return None
    session = sessions.get(record.session_id)
    workflow_data = dict(record.workflow or {})
    if not workflow_data and session is not None:
        workflow_data = asdict(session.workflow)
    exposure = record.exposure_seconds
    if exposure is None and session is not None:
        exposure = session.camera.exposure_seconds
    panes = max(1, int(record.mosaic_panes or 1))
    if session is not None:
        panes = max(panes, int(session.mosaic.panes))
    frames = max(1, captured if captured else planned_frames)
    engine_frames = max(1, planned_frames or captured)
    workflow = _workflow(workflow_data) if workflow_data else None
    planned = float(record.planned_duration_seconds or 0)
    if workflow is not None and exposure is not None:
        planned = DurationEngine.calculate(
            Session(
                name=record.target_name,
                target=Target(name=record.target_name),
                device_id=record.device_id,
                scheduled_start=record.scheduled_start or "",
                camera=CameraSettings(exposure_seconds=float(exposure), frame_count=engine_frames),
                workflow=workflow,
                mosaic=Mosaic(rows=max(1, panes), columns=1),
            ),
            profile,
        )
    wait_before = float(workflow.wait_before_seconds) if workflow else 0.0
    wait_after = float(workflow.wait_after_seconds) if workflow else 0.0
    buckets = _bucket_steps(record.step_seconds)
    return {
        "residual": float(record.actual_duration_seconds) - planned,
        "actual": float(record.actual_duration_seconds),
        "frames": frames,
        "panes": panes,
        "exposure": float(exposure) if exposure is not None else None,
        "workflow": workflow,
        "buckets": buckets,
        "resumed": _is_resumed(record.step_seconds),
        "wait_before": wait_before,
        "wait_after": wait_after,
    }


def _from_steps(items: list[dict[str, Any]], profile: HardwareProfile) -> tuple[list[dict[str, Any]], str, str]:
    observed: dict[str, list[float]] = {key: [] for key in _FIELD_META}
    for item in items:
        buckets = dict(item["buckets"])
        leftover = item["actual"] - sum(buckets.values()) - item["wait_before"] - item["wait_after"]
        startup = buckets.get("startup", 0.0) + max(0.0, leftover)
        if startup > 0:
            observed["startup_seconds"].append(startup)
        if "calibration" in buckets:
            observed["calibration_seconds"].append(buckets["calibration"])
        if "autofocus" in buckets:
            observed["autofocus_seconds"].append(buckets["autofocus"])
        if "infinite_focus" in buckets:
            observed["infinite_focus_seconds"].append(buckets["infinite_focus"])
        if "polar" in buckets:
            observed["polar_seconds"].append(buckets["polar"])
        if "slew" in buckets:
            slew = max(0.0, buckets["slew"] - profile.settle_seconds)
            observed["slew_seconds"].append(slew)
        readout = _readout_from_imaging(item)
        if readout is not None:
            observed["readout_seconds"].append(readout)
    changes = []
    for key, samples in observed.items():
        change = _change_for(key, profile, samples)
        if change is not None:
            changes.append(change)
    note = "From timed session steps on completed runs."
    return changes, "steps", note


def _from_totals(items: list[dict[str, Any]], profile: HardwareProfile) -> tuple[list[dict[str, Any]], str, str]:
    residuals = [item["residual"] for item in items]
    counts = sorted({item["frames"] * item["panes"] for item in items})
    span = (counts[-1] - counts[0]) if len(counts) >= 2 else 0
    if len(counts) >= 2 and span >= 20:
        intercept, slope = _ols(
            [item["frames"] * item["panes"] for item in items],
            residuals,
        )
        changes = []
        startup = _change_for("startup_seconds", profile, [profile.startup_seconds + intercept])
        readout = _change_for("readout_seconds", profile, [profile.readout_seconds + slope])
        if startup is not None:
            changes.append(startup)
        if readout is not None:
            changes.append(readout)
        note = "From completed runs with mixed frame counts. Extra per-frame time is readout; the rest is startup."
        return changes, "totals", note
    median_residual = _median(residuals)
    startup = _change_for("startup_seconds", profile, [profile.startup_seconds + median_residual])
    frames = counts[0] if counts else 0
    note = (
        f"These runs all used the same {frames}-frame recipe, so the extra time is applied to startup. "
        "A longer session will separate readout from setup."
    )
    return ([startup] if startup is not None else []), "totals", note


def _readout_from_imaging(item: dict[str, Any]) -> float | None:
    imaging = item["buckets"].get("imaging")
    exposure = item["exposure"]
    if imaging is None or exposure is None:
        return None
    frames = max(1, int(item["frames"]))
    panes = max(1, int(item["panes"]))
    imaging_frames = frames * panes
    leftover = imaging - exposure * imaging_frames
    if leftover < 0:
        return None
    return leftover / imaging_frames


def _change_for(key: str, profile: HardwareProfile, samples: list[float]) -> dict[str, Any] | None:
    meta = _FIELD_META[key]
    if not samples:
        return None
    suggested = _round_field(key, _clamp(_median(samples), meta["min"], meta["max"]))
    current = _round_field(key, float(getattr(profile, key)))
    if abs(float(suggested) - float(current)) < meta["threshold"]:
        return None
    if suggested == current:
        return None
    return {
        "key": key,
        "label": meta["label"],
        "current": current,
        "suggested": suggested,
        "delta": _round_field(key, float(suggested) - float(current)),
    }


def _bucket_steps(step_seconds: dict[str, float] | None) -> dict[str, float]:
    buckets: dict[str, float] = {}
    for name, seconds in dict(step_seconds or {}).items():
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        label = str(name).strip().lower()
        if any(token in label for token in ("stop", "stopping")):
            continue
        bucket = _STEP_BUCKETS.get(label, "startup")
        buckets[bucket] = buckets.get(bucket, 0.0) + value
    return buckets


def _is_resumed(step_seconds: dict[str, float] | None) -> bool:
    return any("joining capture" in str(name).lower() for name in dict(step_seconds or {}))


def _workflow(data: dict[str, Any]) -> Workflow:
    allowed = set(Workflow.__dataclass_fields__)
    return Workflow(**{key: value for key, value in data.items() if key in allowed})


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (float(ordered[mid - 1]) + float(ordered[mid])) / 2


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        return _median(ys), 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom <= 1e-9:
        return y_mean, 0.0
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
    return y_mean - slope * x_mean, slope


def _round_field(key: str, value: float) -> float | int:
    if key == "readout_seconds":
        return round(float(value), 1)
    return int(round(float(value)))


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
