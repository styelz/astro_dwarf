"""Turn raw worker telemetry into HUD-ready values, activity and alerts."""
from __future__ import annotations

import time
from typing import Any

SHOOTING_MODES = {1: "PHOTO", 2: "DSO", 8: "SUN", 9: "MOON", 10: "PLANET"}
STALE_AFTER_S = 60.0
BATTERY_WARN = 20
BATTERY_CRITICAL = 10
STORAGE_LOW_GB = 2


def battery_tone(percent: Any) -> str:
    try:
        value = int(percent)
    except (TypeError, ValueError):
        return "unknown"
    if value <= BATTERY_CRITICAL:
        return "bad"
    if value <= BATTERY_WARN:
        return "warn"
    return "good"


def _temp_text(value: Any) -> str:
    return "—" if value is None else f"{int(value)}°C"


def derive_activity(raw: dict[str, Any]) -> tuple[str, str]:
    """Return (activity, detail) as reported by the device, or ("", "")."""
    if raw.get("power_off"):
        return "poweroff", "POWERING OFF"
    calibration = raw.get("calibration_state")
    if calibration in ("running", "solving"):
        phase = raw.get("calibration_phase") or 0
        detail = f"SOLVE {phase}" if calibration == "solving" or phase else "STARTING"
        return "calibrate", detail
    if raw.get("goto_state") == "running":
        target = raw.get("goto_target") or ""
        return "goto", target.upper() if target else "SLEWING"
    if raw.get("eq_state") == "running":
        return "polar", "EQ SOLVING"
    if raw.get("autofocus_state") == "running":
        return "autofocus", "RUNNING"
    if raw.get("dark_state") == "running":
        progress = raw.get("dark_progress")
        return "dark", f"{int(progress)}%" if progress is not None else "RUNNING"
    if raw.get("capture_active") or raw.get("capture_state") == "running":
        current = raw.get("capture_current")
        total = raw.get("capture_total")
        if current is not None and total:
            detail = f"{int(current)}/{int(total)}"
        elif current is not None:
            detail = f"{int(current)} FRAMES"
        else:
            detail = "STACKING"
        return "imaging", detail
    if raw.get("record_state") == "running":
        seconds = int(raw.get("record_seconds") or 0)
        return "record", f"{seconds // 60:02d}:{seconds % 60:02d}"
    return "", ""


def format_telemetry(raw: dict[str, Any], updated_at: float | None, now: float | None = None) -> dict[str, Any]:
    """Compute the display-ready telemetry dictionary consumed by QML."""
    now = time.time() if now is None else now
    view: dict[str, Any] = dict(raw)
    percent = raw.get("battery_percent")
    view["battery_percent"] = int(percent) if percent is not None else -1
    view["battery_text"] = f"{int(percent)}%" if percent is not None else "—"
    view["battery_tone"] = battery_tone(percent)
    view["charging"] = bool(raw.get("charging"))
    view["charging_text"] = str(raw.get("charging_state") or "").upper()
    cycles = raw.get("battery_cycles")
    soh = raw.get("battery_soh")
    health_parts = []
    if cycles is not None:
        health_parts.append(f"{int(cycles)} CYCLES")
    if soh is not None:
        health_parts.append(f"SOH {int(soh)}%")
    view["battery_health_text"] = " · ".join(health_parts)
    free = raw.get("storage_free_gb")
    total = raw.get("storage_total_gb")
    valid = raw.get("storage_valid")
    if total:
        used = max(0.0, float(total) - float(free or 0))
        view["storage_percent"] = min(1.0, used / float(total))
        view["storage_text"] = f"{int(free or 0)} / {int(total)} GB"
        view["storage_free_text"] = f"{int(free or 0)} GB FREE"
        view["storage_tone"] = "bad" if (free or 0) < STORAGE_LOW_GB else ("warn" if (free or 0) < 8 else "good")
    else:
        view["storage_percent"] = 0.0
        view["storage_text"] = "NO CARD" if valid is False else "—"
        view["storage_free_text"] = ""
        view["storage_tone"] = "bad" if valid is False else "unknown"
    view["storage_valid"] = bool(valid) if valid is not None else total is not None
    view["temperature_text"] = _temp_text(raw.get("temperature_c"))
    view["cmos_tele_text"] = _temp_text(raw.get("cmos_tele_c"))
    view["cmos_wide_text"] = _temp_text(raw.get("cmos_wide_c"))
    focus = raw.get("focus_position")
    view["focus_text"] = str(int(focus)) if focus is not None else "—"
    view["mount_mode"] = raw.get("mount_mode") or ""
    view["mount_text"] = raw.get("mount_mode") or "—"
    view["stream_text"] = raw.get("stream_type") or "—"
    view["lights_on"] = bool(raw.get("lights_on"))
    view["indicator_on"] = bool(raw.get("indicator_on"))
    host = raw.get("host_mode")
    view["host_text"] = "—" if host is None else ("HOST" if host else "SLAVE")
    view["host_mode"] = bool(host) if host is not None else True
    mode = raw.get("shooting_mode")
    view["shooting_mode_text"] = SHOOTING_MODES.get(int(mode), str(mode)) if mode is not None else "—"
    view["exposure_text"] = raw.get("exposure_text") or "—"
    gain = raw.get("gain")
    view["gain_text"] = str(int(gain)) if gain is not None else "—"
    view["tele_resolution"] = raw.get("tele_resolution") or ""
    view["tele_fov"] = raw.get("tele_fov") or ""
    current = raw.get("capture_current")
    total_frames = raw.get("capture_total")
    stacked = raw.get("capture_stacked")
    if current is not None and total_frames:
        view["capture_text"] = f"{int(current)}/{int(total_frames)}"
        view["capture_fraction"] = min(1.0, float(current) / float(total_frames))
    elif current is not None:
        view["capture_text"] = str(int(current))
        view["capture_fraction"] = 0.0
    else:
        view["capture_text"] = ""
        view["capture_fraction"] = 0.0
    view["stacked_text"] = f"{int(stacked)} STACKED" if stacked is not None else ""
    view["capture_active"] = bool(raw.get("capture_active"))
    view["capture_target"] = raw.get("capture_target") or ""
    view["tracking_active"] = raw.get("tracking_state") == "running"
    view["tracking_target"] = raw.get("tracking_target") or raw.get("goto_target") or ""
    view["goto_state"] = raw.get("goto_state") or ""
    view["calibration_state"] = raw.get("calibration_state") or ""
    view["calibration_phase"] = int(raw.get("calibration_phase") or 0)
    activity, detail = derive_activity(raw)
    view["activity"] = activity
    view["activity_detail"] = detail
    age = (now - updated_at) if updated_at else -1.0
    view["age_s"] = int(age) if age >= 0 else -1
    view["stale"] = bool(updated_at) and age > STALE_AFTER_S
    view["has_data"] = bool(raw)
    return view


class AlertEngine:
    """Fires one alert per state transition (never repeats while a state holds)."""

    def evaluate(self, previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []

        def add(level: str, message: str, detail: str = "", toast: bool = True) -> None:
            alerts.append({"level": level, "message": message, "detail": detail, "toast": "1" if toast else ""})

        def changed(key: str) -> bool:
            return key in current and current.get(key) != previous.get(key)

        # Battery thresholds
        if changed("battery_percent"):
            new = int(current["battery_percent"])
            old = previous.get("battery_percent")
            old = int(old) if old is not None else 101
            if new <= BATTERY_CRITICAL < old:
                add("error", f"Battery critical · {new}%", "Shut down or connect power soon")
            elif new <= BATTERY_WARN < old:
                add("warning", f"Battery low · {new}%", "Plan remaining captures accordingly")
        if changed("charging"):
            if current.get("charging"):
                add("info", "Charging", f"Battery at {current.get('battery_percent', '—')}%", toast=False)
            elif previous.get("charging"):
                add("info", "Charger disconnected", "", toast=False)
        # Storage
        if changed("storage_valid") and current.get("storage_valid") is False:
            add("error", "No SD card detected", "Insert or reseat the storage card")
        if changed("storage_free_gb"):
            new = float(current["storage_free_gb"])
            old = previous.get("storage_free_gb")
            if new < STORAGE_LOW_GB and (old is None or float(old) >= STORAGE_LOW_GB):
                add("warning", f"Storage low · {int(new)} GB free", "Captures may stop when the card fills")
        # GOTO
        if changed("goto_state"):
            target = current.get("goto_target") or previous.get("goto_target") or ""
            suffix = f" · {target}" if target else ""
            state = current["goto_state"]
            if state == "running":
                add("info", f"GOTO started{suffix}", "", toast=False)
            elif state in ("stopped", "idle") and previous.get("goto_state") == "running":
                add("success", f"GOTO complete{suffix}", "Target centred; tracking engaged")
        # Calibration
        if changed("calibration_state"):
            state = current["calibration_state"]
            old = previous.get("calibration_state")
            if state in ("running", "solving") and old not in ("running", "solving"):
                add("info", "Calibration started", "", toast=False)
            elif state in ("stopped", "idle") and old in ("running", "solving"):
                phase = current.get("calibration_phase") or previous.get("calibration_phase") or 0
                detail = f"{int(phase)} plate solve{'s' if int(phase) != 1 else ''}" if phase else ""
                add("success", "Calibration complete", detail)
        # EQ / polar
        if changed("eq_state") and current["eq_state"] in ("stopped", "idle") and previous.get("eq_state") == "running":
            add("success", "EQ solving complete", "")
        # Autofocus
        if changed("autofocus_state") and current["autofocus_state"] in ("stopped", "idle") and previous.get("autofocus_state") == "running":
            focus = current.get("focus_position") or previous.get("focus_position")
            add("success", "Autofocus complete", f"Focus position {int(focus)}" if focus is not None else "")
        # Capture
        if changed("capture_active") and not current["capture_active"] and previous.get("capture_active"):
            stacked = current.get("capture_stacked", previous.get("capture_stacked"))
            total = current.get("capture_total", previous.get("capture_total"))
            target = current.get("capture_target") or previous.get("capture_target") or ""
            detail_parts = []
            if stacked is not None and total:
                detail_parts.append(f"{int(stacked)}/{int(total)} frames stacked")
            elif stacked is not None:
                detail_parts.append(f"{int(stacked)} frames stacked")
            if target:
                detail_parts.append(target)
            add("success", "Capture finished", " · ".join(detail_parts))
        if changed("dark_state") and current["dark_state"] in ("stopped", "idle") and previous.get("dark_state") == "running":
            add("success", "Dark frames complete", "")
        # Power / host
        if changed("power_off") and current.get("power_off"):
            add("error", "Telescope is powering off", "The connection will drop")
        if changed("host_mode") and current.get("host_mode") is False and previous.get("host_mode") is True:
            add("warning", "Control taken by another client", "This app is now in slave mode")
        if changed("host_mode") and current.get("host_mode") is True and previous.get("host_mode") is False:
            add("info", "Host control restored", "", toast=False)
        return alerts
