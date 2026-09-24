"""Turn raw worker telemetry into HUD-ready values, activity and alerts."""
from __future__ import annotations

import math
import time
from fractions import Fraction
from typing import Any

SHOOTING_MODES = {1: "PHOTO", 2: "DSO", 8: "SUN", 9: "MOON", 10: "PLANET"}
STALE_AFTER_S = 60.0
_PHOTO_SHOOTING_MODE = 1
_ASTRO_SHOOTING_MODE = 2
BATTERY_WARN = 20
BATTERY_CRITICAL = 10
STORAGE_LOW_GB = 2
TRACKING_NEEDS_CALIBRATION_TOAST = "Tracking needs calibration"
TRACKING_NEEDS_CALIBRATION_DETAIL = (
    "Run CALIBRATE and wait for it to complete, then try TRACK again"
)


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


def _temp_pair(value: Any) -> tuple[str, str]:
    if value is None:
        return "—", ""
    try:
        celsius = int(value)
    except (TypeError, ValueError):
        return "—", ""
    fahrenheit = round(celsius * 9 / 5 + 32)
    return f"{celsius}°C", f"{fahrenheit}°F"


def _assign_temp(view: dict[str, Any], prefix: str, value: Any) -> None:
    celsius, fahrenheit = _temp_pair(value)
    view[f"{prefix}_text"] = celsius if not fahrenheit else f"{celsius} / {fahrenheit}"
    view[f"{prefix}_c_text"] = celsius
    view[f"{prefix}_f_text"] = fahrenheit


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(int(value))
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# DWARF writes the timelapse MP4 at 30 fps. One second of video is 30 frames.
# Manual example: 10 min at a 5 s interval is 120 frames and a 4 s video.
TIMELAPSE_VIDEO_FPS = 30


def timelapse_shoot_seconds(video_seconds: int, interval_seconds: int) -> int:
    """Wall-clock capture time that yields ``video_seconds`` of finished video.

    A 30 s video at 1 frame per second is a 15 min shoot (30 × 30 × 1), not a
    30 s shoot. That short shoot is only 30 frames, which the 30 fps file
    plays in 1 second.
    """
    video = max(0, int(video_seconds))
    interval = int(interval_seconds)
    if video <= 0:
        return 0
    if interval <= 0:
        interval = 1
    return video * TIMELAPSE_VIDEO_FPS * interval


def timelapse_video_seconds(shoot_seconds: int, interval_seconds: int) -> int:
    """Finished-video length for a firmware shoot duration at 30 fps."""
    shoot = max(0, int(shoot_seconds))
    interval = int(interval_seconds)
    if shoot <= 0:
        return 0
    if interval <= 0:
        interval = 1
    return int(round(shoot / (TIMELAPSE_VIDEO_FPS * interval)))


def photo_capture_seconds(value: Any) -> int | None:
    """Parse HUD burst/timelapse interval and duration as raw firmware seconds.

    CONTROL combos send ``1`` or ``30``. The SDK duration-by-name helper treats
    ``30`` as 30 minutes, so a 30-second timelapse never finished until STOP
    and the MP4 stayed unreadable while it was still being written.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        value = value.get("value", value.get("name", value.get("seconds")))
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return int(round(float(value)))
    text = str(value).strip()
    if not text or text == "—":
        return None
    lower = text.lower().replace("secs", "s").replace("sec", "s")
    if lower in {"off", "∞", "inf", "infinite", "unlimited", "infinity"}:
        return 0
    if "min" in lower:
        number = lower.replace("minutes", "").replace("minute", "").replace("mins", "").replace("min", "").strip()
        try:
            return int(round(float(number) * 60.0))
        except (TypeError, ValueError):
            return None
    if lower.endswith("s") and "/" not in lower:
        lower = lower[:-1].strip()
    try:
        seconds = float(lower)
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return int(round(seconds))


def _feature_seconds_text(value: Any) -> str | None:
    seconds = photo_capture_seconds(value)
    if seconds is None:
        return None
    return str(seconds)


def _clock_text(seconds: int) -> str:
    value = max(0, int(seconds))
    hours = value // 3600
    minutes = (value % 3600) // 60
    secs = value % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _running_elapsed_s(raw: dict[str, Any], seconds_key: str, started_key: str, now: float) -> int:
    """Firmware seconds, interpolated from the start stamp so HUD clocks tick."""
    firmware = int(raw.get(seconds_key) or 0)
    started = _as_float(raw.get(started_key)) or 0.0
    local = int(max(0.0, now - started)) if started > 1_000_000_000 else 0
    return max(firmware, local)


def _timelapse_total_s(raw: dict[str, Any]) -> int:
    """Capture length for the clock. ``timelapse_duration`` is finished-video seconds."""
    video = photo_capture_seconds(raw.get("timelapse_duration")) or 0
    if video > 0:
        interval = photo_capture_seconds(raw.get("timelapse_interval")) or 1
        return timelapse_shoot_seconds(video, interval)
    shoot = int(raw.get("timelapse_shoot_s") or 0)
    if shoot > 0:
        return shoot
    return int(raw.get("timelapse_total_s") or 0)


def _camera_params_entry(cameras: Any, index: int) -> dict[str, Any]:
    if isinstance(cameras, dict):
        for key in (index, str(index)):
            value = cameras.get(key)
            if isinstance(value, dict):
                return value
        return {}
    if isinstance(cameras, list) and 0 <= index < len(cameras):
        value = cameras[index]
        return value if isinstance(value, dict) else {}
    return {}


def _exposure_text_from_params(exposure: dict[str, Any], model_id: str) -> str | None:
    name = exposure.get("name")
    if name not in (None, "", "None"):
        return str(name)
    value = exposure.get("value")
    if value is None:
        return None
    try:
        from .device_telemetry import _exposure_name

        mapped = _exposure_name(value, model_id)
        if mapped not in (None, "", "None"):
            return str(mapped)
    except Exception:
        pass
    return str(value)


def apply_mode_exposure_fields(state: dict[str, Any] | None) -> dict[str, Any]:
    """Copy photo vs DSO exposure/gain into the HUD keys for the live mode.

    Firmware keeps independent PHOTO and ASTRO tables. Mapping both onto
    ``exposure_text`` made a 1/30 photo default overwrite a saved 15s DSO
    exposure after a camera switch or app restart.
    """
    snap = state or {}
    try:
        mode = int(snap["shooting_mode"]) if snap.get("shooting_mode") is not None else 0
    except (TypeError, ValueError):
        mode = 0
    if mode == _PHOTO_SHOOTING_MODE:
        slot = "photo"
    elif mode == _ASTRO_SHOOTING_MODE:
        slot = "astro"
    else:
        return {}
    out: dict[str, Any] = {}
    for prefix in ("", "wide_"):
        exp = snap.get(f"{slot}_{prefix}exposure_text")
        if exp not in (None, "", "—"):
            out[f"{prefix}exposure_text"] = exp
        gain = snap.get(f"{slot}_{prefix}gain")
        if gain not in (None, "", "—"):
            out[f"{prefix}gain"] = gain
    return out


_AUTO_PARAM_BOOL_KEYS = ("isAuto", "is_auto", "autoParams", "autoParameter", "autoParameters")
# Same convention as exposure currentMode: 0 is auto, 1 is manual.
_AUTO_PARAM_MODE_KEYS = ("autoMode", "curAutoMode", "paramsMode", "curParamsMode", "parameterMode")


def _explicit_auto_param(entry: dict[str, Any]) -> bool | None:
    for key in _AUTO_PARAM_BOOL_KEYS:
        if key in entry and entry[key] is not None:
            return _as_bool(entry[key])
    for key in _AUTO_PARAM_MODE_KEYS:
        if key not in entry or entry[key] is None:
            continue
        mode = _as_int(entry[key])
        if mode is not None:
            return mode == 0
    return None


def _exposure_gain_auto(entry: dict[str, Any]) -> bool | None:
    """True when both shutter and gain are in firmware auto mode."""
    exposure = entry.get("exposure") if isinstance(entry.get("exposure"), dict) else {}
    gain = entry.get("gain") if isinstance(entry.get("gain"), dict) else {}
    special = entry.get("specialParams") if isinstance(entry.get("specialParams"), dict) else {}
    exp = special.get("exp") if isinstance(special.get("exp"), dict) else {}
    gn = special.get("gain") if isinstance(special.get("gain"), dict) else {}
    exp_mode = _as_int(exposure.get("mode", exposure.get("currentMode")))
    if exp_mode is None:
        exp_mode = _as_int(exp.get("currentMode", exp.get("mode")))
    gain_mode = _as_int(gain.get("mode", gain.get("currentMode")))
    if gain_mode is None:
        gain_mode = _as_int(gn.get("currentMode", gn.get("mode")))
    if exp_mode is None or gain_mode is None:
        return None
    return exp_mode == 0 and gain_mode == 0


def _camera_label(entry: dict[str, Any], fallback: Any = None) -> str | None:
    raw = entry.get("cameraId", entry.get("camera_id", fallback))
    if raw is None:
        return None
    if str(raw) == "1":
        return "wide"
    if str(raw) == "0":
        return "tele"
    return None


def explicit_auto_parameter_state(result: Any) -> dict[str, bool]:
    """Cameras whose catalog entry has an explicit Auto Parameters flag.

    Exposure ``currentMode`` 1 is the manual table. It is also what the
    catalog still shows immediately after Auto Parameters is turned on, so
    that mode must not be reported as off.
    """
    if not isinstance(result, dict):
        return {}
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    if not isinstance(data, dict):
        return {}
    found: dict[str, bool] = {}

    def consider(entry: Any, fallback: Any = None) -> None:
        if not isinstance(entry, dict):
            return
        name = _camera_label(entry, fallback)
        if name is None or name in found:
            return
        flag = _explicit_auto_param(entry)
        if flag is not None:
            found[name] = flag

    raw_cameras = data.get("cameraParams")
    if isinstance(raw_cameras, list):
        for entry in raw_cameras:
            consider(entry)
    cleaned = data.get("cameras")
    if isinstance(cleaned, dict):
        for key, entry in cleaned.items():
            consider(entry, key)
    elif isinstance(cleaned, list):
        for index, entry in enumerate(cleaned):
            consider(entry, index)
    for entry in data.get("shootingTechSettings") or []:
        consider(entry)
    return found


def auto_parameter_cameras(result: Any) -> list[str]:
    """Tele and wide cameras with the mobile app's Auto Parameters switch on.

    That switch is ``ReqSetAutoParam``. While it is on, a manual stack count
    does not reach the camera. The HTTP catalog reports it as ``isAuto``, or
    as exposure and gain ``currentMode`` 0.
    """
    if not isinstance(result, dict):
        return []
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    if not isinstance(data, dict):
        return []
    found: list[str] = []

    def consider(entry: Any, fallback: Any = None) -> None:
        if not isinstance(entry, dict):
            return
        name = _camera_label(entry, fallback)
        if name is None or name in found:
            return
        flag = _explicit_auto_param(entry)
        if flag is None:
            flag = _exposure_gain_auto(entry)
        if flag:
            found.append(name)

    raw_cameras = data.get("cameraParams")
    if isinstance(raw_cameras, list):
        for entry in raw_cameras:
            consider(entry)
    cleaned = data.get("cameras")
    if isinstance(cleaned, dict):
        for key, entry in cleaned.items():
            consider(entry, key)
    elif isinstance(cleaned, list):
        for index, entry in enumerate(cleaned):
            consider(entry, index)
    for entry in data.get("shootingTechSettings") or []:
        consider(entry)
    return found


def camera_params_to_telemetry(result: Any, model_id: str = "3") -> dict[str, Any]:
    """Map HTTP camera-param JSON onto the telemetry keys QML already reads."""
    if not isinstance(result, dict):
        return {}
    cameras = result.get("cameras") or {}
    changes: dict[str, Any] = {}
    mode_id = _as_int(result.get("mode_id"))
    slot = "photo" if mode_id == _PHOTO_SHOOTING_MODE else "astro"

    def collect(values: Any, prefix: str = "") -> None:
        if not isinstance(values, dict):
            return
        exposure = values.get("exposure")
        if isinstance(exposure, dict):
            text = _exposure_text_from_params(exposure, model_id)
            if text:
                changes[f"{slot}_{prefix}exposure_text"] = text
                if slot == "astro":
                    changes[f"{prefix}exposure_text"] = text
        elif exposure not in (None, ""):
            text = str(exposure)
            changes[f"{slot}_{prefix}exposure_text"] = text
            if slot == "astro":
                changes[f"{prefix}exposure_text"] = text
        gain = values.get("gain")
        if isinstance(gain, dict):
            gain_value = _as_int(gain.get("value"))
        else:
            gain_value = _as_int(gain)
        if gain_value is not None:
            changes[f"{slot}_{prefix}gain"] = gain_value
            if slot == "astro":
                changes[f"{prefix}gain"] = gain_value
        white_balance = values.get("wb") if isinstance(values.get("wb"), dict) else {}
        wb_value = _as_int(white_balance.get("value"))
        if wb_value is not None:
            changes[f"{prefix}wb_value"] = wb_value
        wb_scene = _as_int(white_balance.get("scene"))
        if wb_scene is not None:
            changes[f"{prefix}wb_scene"] = wb_scene
        for name in ("brightness", "contrast", "saturation", "hue", "sharpness"):
            number = _as_int(values.get(name))
            if number is not None:
                changes[f"{prefix}{name}"] = number
        stack_count = _as_int(values.get("stackCount", values.get("stack_count")))
        if stack_count is not None:
            changes[f"{prefix}stack_count"] = stack_count
        ir = values.get("filterType", values.get("filter_type", values.get("filter")))
        if prefix == "" and ir not in (None, ""):
            from .domain import normalize_ir_filter

            name = normalize_ir_filter(ir)
            if name:
                changes["ir_filter"] = name
        burst = values.get("burst") if isinstance(values.get("burst"), dict) else {}
        burst_count = burst.get("count", values.get("burst_count"))
        if isinstance(burst_count, dict):
            burst_count = burst_count.get("value", burst_count.get("name"))
        burst_count = _as_int(burst_count)
        if burst_count is not None:
            changes[f"{prefix}burst_count"] = burst_count
        burst_interval = _feature_seconds_text(burst.get("interval", values.get("burst_interval")))
        if burst_interval is not None:
            changes[f"{prefix}burst_interval"] = burst_interval
        lapse = values.get("timelapse")
        if not isinstance(lapse, dict):
            lapse = values.get("timeLapse") if isinstance(values.get("timeLapse"), dict) else {}
        if not lapse:
            lapse = values.get("time_lapse") if isinstance(values.get("time_lapse"), dict) else {}
        lapse_interval = _feature_seconds_text(lapse.get("interval", values.get("timelapse_interval")))
        if lapse_interval is not None:
            changes[f"{prefix}timelapse_interval"] = lapse_interval
        # Firmware duration is shoot seconds (120 = 2 min). The HUD duration
        # is the finished video, so 900 s at a 1 s interval comes back as 30.
        lapse_shoot = photo_capture_seconds(lapse.get("duration", values.get("timelapse_duration")))
        if lapse_shoot is not None:
            interval = photo_capture_seconds(lapse_interval) or 1
            changes[f"{prefix}timelapse_shoot_s"] = int(lapse_shoot)
            changes[f"{prefix}timelapse_duration"] = str(timelapse_video_seconds(lapse_shoot, interval))

    collect(_camera_params_entry(cameras, 0))
    collect(_camera_params_entry(cameras, 1), "wide_")
    shooting = result.get("shooting_mode")
    if isinstance(shooting, dict):
        auto_cal = shooting.get("autoCalibration", shooting.get("auto_calibration"))
        parsed = _as_bool(auto_cal)
        if parsed is not None:
            changes["auto_calibration"] = parsed
        stack_format = _as_int(
            shooting.get("stackFormat", shooting.get("stack_format", shooting.get("format")))
        )
        if stack_format is not None:
            changes["stack_format"] = stack_format
    techs = result.get("tech_settings") or {}
    if isinstance(techs, dict):
        # shootingTechSettings is per camera: 0 tele, 1 wide. stackCount there
        # is the DSO subframe total. A camera "count" field is not that value.
        for camera_id, prefix in ((0, ""), (1, "wide_")):
            entry = techs.get(camera_id)
            if not isinstance(entry, dict):
                entry = techs.get(str(camera_id))
            if not isinstance(entry, dict):
                continue
            count = _as_int(entry.get("stackCount", entry.get("stack_count")))
            if count is not None:
                changes[f"{prefix}stack_count"] = count
    catalog = result.get("data") if isinstance(result.get("data"), dict) else result
    if isinstance(catalog, dict) and (
        catalog.get("cameraParams") or catalog.get("cameras") or catalog.get("shootingTechSettings")
    ):
        for camera, flag in explicit_auto_parameter_state(result).items():
            changes[f"auto_parameters_{camera}"] = flag
        for camera in auto_parameter_cameras(result):
            changes.setdefault(f"auto_parameters_{camera}", True)
    return changes


def exposure_seconds_from_text(value: Any) -> float | None:
    """Parse firmware exposure names ('15', '1/60', '15s') into seconds."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _as_float(value)
    text = str(value).strip()
    if not text or text == "—":
        return None
    if text.lower().endswith("s") and "/" not in text:
        text = text[:-1].strip()
    try:
        seconds = float(Fraction(text)) if "/" in text else float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return _as_float(seconds)


def _configured_exposure_seconds(raw: dict[str, Any]) -> float:
    camera = str(raw.get("capture_camera") or "")
    texts = (
        (raw.get("wide_exposure_text"), raw.get("exposure_text"))
        if camera == "wide"
        else (raw.get("exposure_text"), raw.get("wide_exposure_text"))
    )
    for text in texts:
        seconds = exposure_seconds_from_text(text)
        if seconds:
            return seconds
    return 0.0


def _exposure_progress_seconds(raw: dict[str, Any]) -> tuple[float, float]:
    """Firmware long-exp progress, falling back to the configured exposure."""
    configured = _configured_exposure_seconds(raw)
    elapsed = _as_float(raw.get("exposure_elapsed_s")) or 0.0
    total = _as_float(raw.get("exposure_total_s")) or 0.0
    # Some firmware builds report milliseconds for a multi-second exposure.
    if configured >= 1 and total > configured * 8:
        elapsed /= 1000.0
        total /= 1000.0
    if total <= 0:
        total = configured
    if total > 0:
        elapsed = min(elapsed, total)
    return elapsed, total


def _capture_frame_count(raw: dict[str, Any]) -> int | None:
    """Stacked frames are the HUD counter; taken is only a fallback.

    Firmware ``current_count`` increments when a subframe is captured, often
    as the next exposure starts. ``stacked_count`` is frames actually in the
    stack. Using ``max()`` made STACKING N/M run a frame ahead of the preview.
    """
    stacked = _as_int(raw.get("capture_stacked"))
    if stacked is not None:
        return stacked
    return _as_int(raw.get("capture_current"))


def stacked_capture_count(raw: dict[str, Any]) -> int:
    """Non-negative stacked frames, falling back to taken only if stacked is missing."""
    value = _capture_frame_count(raw)
    return max(0, int(value or 0))


def tracking_needs_calibration(result: Any) -> bool:
    """True when a TRACK/GOTO failure is the uncalibrated-mount reject."""
    text = str(result or "").lower()
    return (
        "need_calibration" in text
        or "needs calibration" in text
        or "-11511" in text
        or "run calibrate" in text
    )


def derive_activity(raw: dict[str, Any], now: float | None = None) -> tuple[str, str]:
    """Return (activity, detail) as reported by the device, or ("", "")."""
    now = time.time() if now is None else now
    if raw.get("power_off"):
        return "poweroff", "POWERING OFF"
    calibration = raw.get("calibration_state")
    if calibration in ("running", "solving"):
        phase = raw.get("calibration_phase") or 0
        detail = f"SOLVE {phase}" if calibration == "solving" or phase else "STARTING"
        return "calibrate", detail
    if raw.get("goto_state") in ("running", "solving", "stopping"):
        target = raw.get("goto_target") or ""
        if raw.get("goto_state") == "solving":
            detail = "PLATE SOLVING"
        elif raw.get("goto_state") == "stopping":
            detail = "STOPPING"
        else:
            detail = target.upper() if target else "SLEWING"
        return "goto", detail
    if raw.get("eq_state") == "running":
        return "polar", "EQ SOLVING"
    if raw.get("autofocus_state") in ("running", "stopping"):
        return "autofocus", "STOPPING" if raw.get("autofocus_state") == "stopping" else "RUNNING"
    if raw.get("dark_state") == "running":
        progress = raw.get("dark_progress")
        return "dark", f"{int(progress)}%" if progress is not None else "RUNNING"
    if raw.get("burst_state") == "running":
        completed = _as_int(raw.get("burst_completed"))
        total = _as_int(raw.get("burst_total")) or _as_int(raw.get("burst_count"))
        if completed is not None and total:
            return "burst", f"{completed}/{total}"
        if total:
            return "burst", f"{total} SHOTS"
        return "burst", "RUNNING"
    if raw.get("timelapse_state") == "running":
        elapsed = _running_elapsed_s(raw, "timelapse_elapsed_s", "timelapse_started_at", now)
        total = _timelapse_total_s(raw)
        video = photo_capture_seconds(raw.get("timelapse_duration")) or 0
        out_s = int(raw.get("timelapse_out_s") or 0)
        if total:
            detail = f"{_clock_text(elapsed)} / {_clock_text(total)}"
        else:
            detail = _clock_text(elapsed)
        # out_time is how much of the 30 fps file has been assembled.
        if video > 0:
            detail = f"{detail} · OUT {_clock_text(out_s)} / {_clock_text(video)}"
        elif out_s > 0 and out_s + 2 < elapsed:
            detail = f"{detail} · OUT {_clock_text(out_s)}"
        return "timelapse", detail
    if raw.get("record_state") == "running":
        return "record", _clock_text(_running_elapsed_s(raw, "record_seconds", "record_started_at", now))
    if raw.get("capture_active") or raw.get("capture_state") == "running":
        current = _capture_frame_count(raw)
        total = raw.get("capture_total")
        if current is not None and total:
            detail = f"{int(current)}/{int(total)}"
        elif current is not None:
            detail = f"{int(current)} FRAMES"
        else:
            detail = "STACKING"
        return "imaging", detail
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
    _assign_temp(view, "temperature", raw.get("temperature_c"))
    _assign_temp(view, "cmos_tele", raw.get("cmos_tele_c"))
    _assign_temp(view, "cmos_wide", raw.get("cmos_wide_c"))
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
    tech = _as_int(raw.get("shooting_tech"))
    view["shooting_tech"] = tech if tech else 0
    view["photo_primed"] = bool(raw.get("photo_primed")) and _as_int(mode) == 1 and tech in {None, 1}
    view["exposure_text"] = raw.get("exposure_text") or "—"
    gain = raw.get("gain")
    view["gain_text"] = str(int(gain)) if gain is not None else "—"
    view["tele_resolution"] = raw.get("tele_resolution") or ""
    view["tele_fov"] = raw.get("tele_fov") or ""
    view["wide_fov"] = raw.get("wide_fov") or ""
    progress = _capture_frame_count(raw)
    total_frames = raw.get("capture_total")
    stacked = raw.get("capture_stacked")
    taken = raw.get("capture_current")
    capturing = bool(raw.get("capture_active") or raw.get("capture_state") == "running")
    if capturing and progress is not None and total_frames:
        view["capture_text"] = f"{int(progress)}/{int(total_frames)}"
        view["capture_fraction"] = min(1.0, float(progress) / float(total_frames))
    elif capturing and progress is not None:
        view["capture_text"] = str(int(progress))
        view["capture_fraction"] = 0.0
    else:
        view["capture_text"] = ""
        view["capture_fraction"] = 0.0
    view["stacked_text"] = f"{int(stacked)} STACKED" if capturing and stacked is not None else ""
    try:
        view["capture_stacked"] = int(stacked or 0)
    except (TypeError, ValueError):
        view["capture_stacked"] = 0
    try:
        view["capture_current"] = int(taken or 0)
    except (TypeError, ValueError):
        view["capture_current"] = 0
    try:
        view["capture_total"] = int(total_frames or 0)
    except (TypeError, ValueError):
        view["capture_total"] = 0
    view["capture_active"] = capturing
    elapsed_s, exposure_s = _exposure_progress_seconds(raw) if capturing else (0.0, _configured_exposure_seconds(raw))
    view["exposure_elapsed_s"] = round(elapsed_s, 2)
    view["exposure_total_s"] = round(exposure_s, 3)
    view["exposure_progress"] = min(1.0, elapsed_s / exposure_s) if capturing and exposure_s > 0 else 0.0
    # The shutter opens on firmware 0/0, then each time current_count pulls
    # ahead (1/0, 2/1, …). stacked_count catches up mid-exposure and does
    # not start a frame. Synthetic zeros after START_CAPTURE are not a
    # progress packet. Non-zero counts (join) are live. Last N/N holds.
    seen = bool(raw.get("capture_progress_seen")) or view["capture_current"] > 0 or view["capture_stacked"] > 0
    last_done = view["capture_total"] > 0 and view["capture_stacked"] >= view["capture_total"]
    view["capture_progress_seen"] = bool(capturing and seen)
    view["exposure_running"] = bool(capturing and seen and not last_done)
    view["capture_target"] = raw.get("capture_target") or ""
    view["tracking_active"] = raw.get("tracking_state") == "running"
    view["tracking_target"] = raw.get("tracking_target") or raw.get("goto_target") or ""
    view["goto_state"] = raw.get("goto_state") or ""
    view["calibration_state"] = raw.get("calibration_state") or ""
    view["calibration_phase"] = int(raw.get("calibration_phase") or 0)
    azi = raw.get("eq_azi_err")
    alt = raw.get("eq_alt_err")
    try:
        azi_value = float(azi) if azi is not None else None
    except (TypeError, ValueError):
        azi_value = None
    try:
        alt_value = float(alt) if alt is not None else None
    except (TypeError, ValueError):
        alt_value = None
    view["eq_azi_err"] = azi_value if azi_value is not None else 0
    view["eq_alt_err"] = alt_value if alt_value is not None else 0
    view["eq_has_result"] = azi_value is not None and alt_value is not None
    if view["eq_has_result"]:
        azi_glyph = "↻" if azi_value > 0 else ("↺" if azi_value < 0 else "·")
        alt_glyph = "↑" if alt_value > 0 else ("↓" if alt_value < 0 else "·")
        azi_dir = "CW" if azi_value > 0 else ("CCW" if azi_value < 0 else "OK")
        alt_dir = "UP" if alt_value > 0 else ("DOWN" if alt_value < 0 else "OK")
        view["eq_azi_text"] = f"{azi_glyph} {abs(azi_value):.2f}° AZ {azi_dir}"
        view["eq_alt_text"] = f"{alt_glyph} {abs(alt_value):.2f}° ALT {alt_dir}"
    else:
        view["eq_azi_text"] = ""
        view["eq_alt_text"] = ""
    view["timelapse_shoot_s"] = _timelapse_total_s(raw)
    activity, detail = derive_activity(raw, now)
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

        # Battery thresholds. Skip the low-battery toast on the first sample —
        # a coarse 20% notify often arrives before the real 22% BatteryInfo.
        if changed("battery_percent"):
            new = int(current["battery_percent"])
            old = previous.get("battery_percent")
            old = int(old) if old is not None else None
            if old is None:
                if new <= BATTERY_CRITICAL:
                    add("error", f"Battery critical · {new}%", "Shut down or connect power soon")
            elif new <= BATTERY_CRITICAL < old:
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
            previous_state = previous.get("goto_state")
            if state in ("running", "solving") and previous_state not in ("running", "solving", "stopping"):
                add("info", f"GOTO started{suffix}", "", toast=False)
            elif state == "solving" and previous_state == "running":
                add("info", f"GOTO plate-solving{suffix}", "", toast=False)
            elif (
                state in ("stopped", "idle")
                and previous_state in ("running", "solving", "stopping")
                and not current.get("goto_error")
                and not current.get("goto_released")
            ):
                tracking = current.get("tracking_state") == "running"
                detail = "Target centred; tracking engaged" if tracking else "Target centred"
                add("success", f"GOTO complete{suffix}", detail)
        if changed("goto_error") and current.get("goto_error") == "need_calibration":
            add("warning", TRACKING_NEEDS_CALIBRATION_TOAST, TRACKING_NEEDS_CALIBRATION_DETAIL)
        elif changed("goto_error") and current.get("goto_error"):
            add("error", "GOTO failed", "The telescope rejected the slew")
        # Calibration. Firmware notifies idle both when the solve finishes and
        # when it fails (CODE_ASTRO_CALIBRATION_FAILED). The reply is stored as
        # calibration_error; idle alone is not success.
        if changed("calibration_state") or (
            changed("calibration_error") and current.get("calibration_error")
        ):
            state = current.get("calibration_state")
            old = previous.get("calibration_state")
            failed = bool(current.get("calibration_error"))
            if changed("calibration_state") and state in ("running", "solving") and old not in ("running", "solving"):
                add("info", "Calibration started", "", toast=False)
            ended = (
                changed("calibration_state")
                and state in ("stopped", "idle")
                and old in ("running", "solving")
            )
            if ended and not failed:
                phase = current.get("calibration_phase") or previous.get("calibration_phase") or 0
                try:
                    phase_n = int(phase)
                except (TypeError, ValueError):
                    phase_n = 0
                detail = f"{phase_n} plate solve{'s' if phase_n != 1 else ''}" if phase_n else ""
                add("success", "Calibration complete", detail)
            elif failed and not previous.get("calibration_error"):
                add("error", "Calibration failed", "The telescope could not plate-solve")
        # EQ / polar
        if changed("eq_state") and current["eq_state"] in ("stopped", "idle") and previous.get("eq_state") == "running":
            azi = current.get("eq_azi_err", previous.get("eq_azi_err"))
            alt = current.get("eq_alt_err", previous.get("eq_alt_err"))
            detail = ""
            if azi is not None and alt is not None:
                detail = f"Az {abs(float(azi)):.2f}° · Alt {abs(float(alt)):.2f}°"
            add("success", "EQ solving complete", detail)
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
            if stacked:
                add("success", "Capture finished", " · ".join(detail_parts))
            else:
                add("info", "Capture ended", " · ".join(detail_parts) or "No frames stacked", toast=False)
        if changed("dark_state") and current["dark_state"] in ("stopped", "idle") and previous.get("dark_state") == "running":
            add("success", "Dark frames complete", "")
        if changed("burst_state") and current["burst_state"] in ("stopped", "idle") and previous.get("burst_state") == "running":
            count = current.get("burst_count", previous.get("burst_count"))
            add("success", "Burst complete", f"{int(count)} shots" if count else "")
        if changed("timelapse_state") and current["timelapse_state"] in ("stopped", "idle") and previous.get("timelapse_state") == "running":
            add("success", "Timelapse complete", "")
        if changed("record_state") and current["record_state"] in ("stopped", "idle") and previous.get("record_state") == "running":
            add("success", "Recording complete", "")
        # Power / host
        if changed("power_off") and current.get("power_off"):
            add("error", "Telescope is powering off", "The connection will drop")
        if changed("host_mode") and current.get("host_mode") is False and previous.get("host_mode") is True:
            add("warning", "Control taken by another client", "This app is now in slave mode")
        if changed("host_mode") and current.get("host_mode") is True and previous.get("host_mode") is False:
            add("info", "Host control restored", "", toast=False)
        return alerts
