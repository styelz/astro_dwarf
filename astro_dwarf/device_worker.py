"""Isolated telescope SDK worker.

One process is launched per physical telescope. JSON messages use stdout;
all SDK output and tracebacks use stderr so the Qt log panel can display them.
"""
from __future__ import annotations

import contextlib
import asyncio
import heapq
import html
import itertools
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import queue
from pathlib import Path
from typing import Any

from .device_telemetry import CODE_STEP_MOTOR_NEED_RESET, TelemetryTap, install_sdk_logging
from .domain import (
    album_http_path,
    album_http_url,
    album_path_matches_model,
    device_name_model,
    firmware_binning,
    firmware_exposure_name,
)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_write_lock = threading.Lock()
_api = None
_tap: TelemetryTap | None = None
_device: dict[str, Any] = {}
_stop = threading.Event()
# (priority, sequence, message): urgent commands (stop/disconnect) jump the queue.
_commands: queue.PriorityQueue[tuple[int, int, dict[str, Any]]] = queue.PriorityQueue()
_command_sequence = itertools.count()
_PRIORITY_URGENT = 0
_PRIORITY_NORMAL = 1
_connected = threading.Event()
_session_active = threading.Event()
_session_phase: str | None = None
_stop_phase: str | None = None
_in_flight: str | None = None
_interrupt_pending = False
_INTERRUPT_MARKER = "astro-dwarf-interrupt"
_QUIET_OPERATIONS = {"device_state", "stack_status"}
_STATE_REFRESH_SECONDS = 30.0
_STATUS_POLL_SECONDS = 2.0
_MODEL_IDS = {"Dwarf II": "2", "Dwarf 3": "3", "Dwarf Mini": "5"}
# Set once the steppers answer CODE_STEP_MOTOR_NEED_RESET: absolute position
# reads keep failing until the mount is homed, so stop probing this session.
_motors_unhomed = False
# Dual Lenses Locating (cmd 14009) always works in wide-camera 1920x1080 pixels.
_LINKAGE_W = 1920
_LINKAGE_H = 1080


def emit(payload: dict[str, Any]) -> None:
    with _write_lock:
        sys.__stdout__.write(json.dumps(payload, default=str) + "\n")
        sys.__stdout__.flush()


def log(message: str, level: str = "info") -> None:
    emit({"event": "log", "level": level, "message": message})


def report_status(kind: str, step: str) -> None:
    emit({"event": "status", "kind": kind, "step": step})


def _client_status() -> Any:
    try:
        from dwarf_python_api.lib import websockets_utils

        if getattr(websockets_utils, "client_instance", None) is None:
            return None
        return websockets_utils.get_client_status()
    except Exception:
        return None


def _queued_internal(command: str) -> bool:
    with _commands.mutex:
        return any(
            item.get("internal") and item.get("command") == command
            for _priority, _sequence, item in _commands.queue
        )


def _put_command(message: dict[str, Any], priority: int = _PRIORITY_NORMAL) -> None:
    _commands.put((priority, next(_command_sequence), message))


def request_state_refresh() -> None:
    """Queue a full device-state read behind the current SDK command."""
    if _connected.is_set() and not _queued_internal("device_state"):
        _put_command({"command": "device_state", "internal": True})


def _sdk_socket() -> tuple[Any, Any]:
    """Return the SDK's live websocket client and its event loop (or Nones)."""
    try:
        from dwarf_python_api.lib import websockets_utils

        client = getattr(websockets_utils, "client_instance", None)
        loop = getattr(websockets_utils, "event_loop", None)
        if client is None or loop is None or loop.is_closed():
            return None, None
        return client, loop
    except Exception:
        return None, None


def _interrupt_sdk_wait(reason: str) -> bool:
    """Wake the SDK call blocked on the result queue so it returns False.

    The SDK waits on ``client_instance.result_queue`` for the device reply;
    pushing a warning result makes ``send_socket_message`` return immediately.
    """
    global _interrupt_pending
    client, loop = _sdk_socket()
    if client is None:
        return False
    try:
        from dwarf_python_api.lib import websockets_utils

        payload = {
            "result": websockets_utils.Dwarf_Result.WARNING,
            "message": _INTERRUPT_MARKER,
            "code": websockets_utils.ERROR_INTERRUPTED,
            "reason": reason,
        }
        loop.call_soon_threadsafe(client.result_queue.put_nowait, payload)
        _interrupt_pending = True
        return True
    except Exception:
        return False


def _drain_result_queue() -> None:
    """Drop leftover SDK results so a prior fire-and-forget command cannot complete the next wait."""
    global _interrupt_pending
    _interrupt_pending = False
    client, loop = _sdk_socket()
    if client is None:
        return

    async def drain() -> None:
        while True:
            try:
                client.result_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    try:
        asyncio.run_coroutine_threadsafe(drain(), loop).result(timeout=2)
    except Exception:
        pass


def request_stop(reason: str = "Session stopped") -> None:
    """Abort the running session from the reader thread without touching the SDK.

    Sets the stop flag (checked between steps) and wakes any SDK call that is
    waiting for a device reply. The actual stop commands run afterwards on the
    command thread so they never race the interrupted call.
    """
    global _stop_phase
    _stop_phase = _session_phase
    _stop.set()
    if _session_active.is_set() or _in_flight is not None:
        report_status("stop", _stop_wait_label(_session_phase or _in_flight))
    else:
        report_status("stop", "Sending stop commands")
    if _in_flight is not None:
        _interrupt_sdk_wait(reason)


def _telemetry_loop() -> None:
    """Flush buffered telemetry, mirror the SDK cache, and refresh device state."""
    last_status = 0.0
    last_refresh = time.monotonic()
    while True:
        time.sleep(0.25)
        tap = _tap
        if tap is None:
            continue
        try:
            tap.flush()
        except Exception:
            pass
        if not _connected.is_set():
            last_refresh = time.monotonic()
            continue
        if tap.snapshot().get("power_off"):
            _connected.clear()
            continue
        now = time.monotonic()
        if now - last_status >= _STATUS_POLL_SECONDS:
            last_status = now
            status = _client_status()
            if status is not None:
                tap.poll_client_status(status)
        # Command-triggered refreshes stamp state_snapshot_at too, so they push the periodic one out.
        snapshot_at = tap.snapshot().get("state_snapshot_at")
        if isinstance(snapshot_at, (int, float)):
            last_refresh = max(last_refresh, now - max(0.0, time.time() - float(snapshot_at)))
        if now - last_refresh >= _STATE_REFRESH_SECONDS:
            last_refresh = now
            request_state_refresh()


def send_without_response(message: Any, command: int, module_id: int) -> bool:
    """Send a V3 command without waiting for the SDK's blocking reply."""
    socket_globals = _api.connect_socket.__globals__
    client = socket_globals.get("client_instance")
    if not client:
        return False
    future = asyncio.run_coroutine_threadsafe(
        socket_globals["send_socket"](message, command, 0, module_id),
        client.task.get_loop(),
    )
    future.result(timeout=5)
    return True


FUNCTIONS = {
    "disconnect": "perform_disconnect",
    "reboot": "perform_reboot",
    "power_down": "perform_powerdown",
    "lights_on": "perform_powerOpenRGB",
    "lights_off": "perform_powerCloseRGB",
    "indicator_on": "perform_powerIndOn",
    "indicator_off": "perform_powerIndOff",
    "time": "perform_time",
    "timezone": "perform_timezone",
    "location": "perform_set_location",
    "host_master": "set_HostMaster",
    "host_release": "unset_HostMaster",
    "device_state": "perform_get_device_state_info",
    "go_live": "perform_GoLive",
    "photo_mode": "perform_enter_photo_mode",
    "astro_mode": "perform_enter_astro_mode",
    "shooting_mode": "perform_enter_shooting_mode",
    "open_camera": "perform_open_camera",
    "open_wide_camera": "perform_open_widecamera",
    "calibrate": "perform_calibration",
    "stop_calibrate": "perform_stop_calibration",
    "autofocus": "perform_start_autofocus",
    "stop_autofocus": "perform_stop_autofocus",
    "polar": "start_polar_align",
    "stop_polar": "stop_polar_align",
    "goto": "perform_goto",
    "goto_solar": "perform_goto_stellar",
    "stop_goto": "perform_stop_goto",
    "joystick": "perform_motor_joystick_v3",
    "stop_motors": "perform_motor_joystick_stop_v3",
    "set_exposure": "perform_set_astro_exposure_by_name_v3",
    "set_gain": "perform_set_astro_gain_v3",
    "set_ir": "perform_set_ir_filter_v3",
    "set_count": "perform_set_astro_stack_count_v3",
    "set_mosaic_count": "perform_set_astro_mosaic_count_v3",
    "set_binning": "perform_set_astro_stack_binning_v3",
    "astro": "perform_takeAstroPhoto",
    "wait_astro": "perform_waitEndAstroPhoto",
    "wait_astro_resume": "perform_waitRetryEndAstroPhoto",
    "stop_astro": "perform_stopAstroPhoto",
    "wide_astro": "perform_takeAstroWidePhoto",
    "wait_wide": "perform_waitEndAstroWidePhoto",
    "wait_wide_resume": "perform_waitRetryEndAstroWidePhoto",
    "stop_wide": "perform_stopAstroWidePhoto",
    "mosaic": "perform_start_mosaic_v3",
    "stack_status": "perform_read_astro_stacking_status_v3",
    "burst_start": "perform_start_burst_v3",
    "burst_stop": "perform_stop_burst_v3",
    "record_start": "perform_start_record_v3",
    "record_stop": "perform_stop_record_v3",
    "timelapse_start": "perform_start_timelapse_v3",
    "timelapse_stop": "perform_stop_timelapse_v3",
    "photo": "perform_takePhoto",
    "wide_photo": "perform_takeWidePhoto",
    "photo_autofocus": "perform_auto_focus_v3",
    "set_wb": "perform_set_wb_v3",
    "set_wb_preset": "perform_set_wb_preset_by_name_v3",
    "set_brightness": "perform_set_brightness_v3",
    "set_contrast": "perform_set_contrast_v3",
    "set_saturation": "perform_set_saturation_v3",
    "set_hue": "perform_set_hue_v3",
    "set_sharpness": "perform_set_sharpness_v3",
    "set_burst_count": "perform_set_burst_count_v3",
    "set_burst_interval": "perform_set_burst_interval_by_name_v3",
    "set_timelapse_interval": "perform_set_timelapse_interval_by_name_v3",
    "set_timelapse_duration": "perform_set_timelapse_duration_by_name_v3",
    "set_stack_format": "perform_set_astro_stack_format_v3",
    "set_auto_calibration": "perform_set_astro_auto_calibration_v3",
    "read_camera": "perform_read_camera_params_http_v3",
}

# Firmware DSO stacking mode. Sun/Moon/Planet use 8/9/10 instead.
_ASTRO_SHOOTING_MODE = 2
_ASTRO_SHOOTING_TECH = 2


def configure(device: dict[str, Any]) -> bool:
    global _api, _device
    _device = device
    folder = Path(tempfile.mkdtemp(prefix=f"astro-dwarf-{device['id'][:8]}-"))
    actual_id = {"Dwarf II": 2, "Dwarf 3": 3, "Dwarf Mini": 5}.get(device.get("model"), 3)
    (folder / "config.py").write_text(
        "\n".join(
            [
                f'DWARF_IP = "{device.get("ip_address", "")}"',
                f'DWARF_ID = "{actual_id - 1}"',
                'DWARF_UI = "True"',
                'CLIENT_ID = "0000DAF2-0000-1000-8000-00805F9B34FB"',
                'TIMEOUT_CMD = "0"',
                'LOG_FILE = "False"',
                "DEBUG = False",
                "TRACE = True",
            ]
        ),
        encoding="utf-8",
    )
    (folder / "config.ini").write_text(
        "\n".join(
            [
                "[CONFIG]",
                f"LATITUDE = {device.get('latitude', 0)}",
                f"LONGITUDE = {device.get('longitude', 0)}",
                f"TIMEZONE = {device.get('timezone_name', 'UTC')}",
                f"BLE_STA_SSID = {device.get('wifi_ssid', '')}",
                f"BLE_STA_PWD = {device.get('wifi_password', '')}",
                f"BLE_PSD = {device.get('ble_password') or 'DWARF_12345678'}",
            ]
        ),
        encoding="utf-8",
    )
    os.chdir(folder)
    with contextlib.redirect_stdout(sys.stderr):
        from dwarf_python_api.lib import dwarf_utils, websockets_utils

        _api = dwarf_utils
    install_sdk_logging(emit)
    global _tap
    _tap = TelemetryTap(emit, _MODEL_IDS.get(str(device.get("model")), "3"))
    if not _tap.install(websockets_utils):
        log("Telemetry tap unavailable; only SDK cache values will be shown", "warning")
    threading.Thread(target=_telemetry_loop, name="telemetry", daemon=True).start()
    log(f"Worker ready for {device.get('name')} at {device.get('ip_address')}")
    return True


def _timezone_values() -> list[str]:
    name = str(_device.get("timezone_name") or "UTC").strip() or "UTC"
    values = [name]
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        offset = datetime.now(ZoneInfo(name)).utcoffset()
        if offset is not None:
            total = int(offset.total_seconds() // 60)
            sign = "+" if total >= 0 else "-"
            hours, minutes = divmod(abs(total), 60)
            for prefix in ("GMT", "UTC"):
                stamp = f"{prefix}{sign}{hours:02d}:{minutes:02d}"
                if stamp not in values:
                    values.append(stamp)
    except Exception:
        pass
    return values


def _set_timezone() -> Any:
    """CMD_SYSTEM_SET_TIME_ZONE (13001). Try IANA name, then GMT/UTC offsets."""
    from dwarf_python_api.proto import system_pb2

    last: Any = False
    for value in _timezone_values():
        message = system_pb2.ReqSetTimezone()
        message.timezone = value
        log(f"Timezone is : {value}", "notice")
        last = _send_request("timezone", message, 13001, 4, "Set Timezone")
        if last == 0:
            return True
        if last is False:
            return False
        log(f"Timezone {value} rejected ({last}), trying next format", "debug")
    log(
        "Firmware rejected timezone strings; clock offset was already applied by SET_TIME",
        "debug",
    )
    return False


def _site_coordinates() -> tuple[float, float]:
    try:
        latitude = float(_device.get("latitude") or 0)
        longitude = float(_device.get("longitude") or 0)
    except (TypeError, ValueError):
        return 0.0, 0.0
    return latitude, longitude


def _set_location() -> Any:
    """CMD_SYSTEM_SET_LOCATION (13010) using the worker's device coordinates.

    The SDK wrapper reads config.ini from the process cwd. Sending the proto
    from ``_device`` keeps a cwd/config miss from silently writing 0,0.
    """
    from dwarf_python_api.proto import system_pb2

    latitude, longitude = _site_coordinates()
    if abs(latitude) < 1e-9 and abs(longitude) < 1e-9:
        log(
            "Telescope location is lat=0, long=0 — set your site coordinates or polar alignment and tracking will be wrong",
            "warning",
        )
        return False
    message = system_pb2.ReqSetLocation()
    message.latitude = latitude
    message.longitude = longitude
    message.altitude = 0
    log(f"Location is : lat={latitude}, long={longitude}", "notice")
    return _send_request("location", message, 13010, 4, "Set Location")


def _motor_position(motor_id: int) -> float | None:
    """Read one axis via CMD 14011. Position is degrees.

    Returns None straight away when the firmware replies with an error (most
    often NEED_RESET on a mount that has not been homed) instead of waiting
    for the timeout, and remembers NEED_RESET so later taps skip the probe.
    """
    global _motors_unhomed
    from dwarf_python_api.proto import motor_control_pb2

    if _tap is None or _motors_unhomed:
        return None
    before = time.monotonic()
    message = motor_control_pb2.ReqMotorGetPosition()
    message.id = int(motor_id)
    send_without_response(message, 14011, 6)
    deadline = time.monotonic() + 1.5
    key = f"motor_pos_{int(motor_id)}"
    stamp_key = f"{key}_at"
    while time.monotonic() < deadline:
        snap = _tap.snapshot()
        stamped = snap.get(stamp_key)
        if isinstance(stamped, (int, float)) and float(stamped) >= before - 0.05:
            try:
                return float(snap[key])
            except (KeyError, TypeError, ValueError):
                return None
        last_at = snap.get("motor_pos_last_at")
        if isinstance(last_at, (int, float)) and float(last_at) >= before - 0.05:
            try:
                code = int(snap.get("motor_pos_last_code") or 0)
            except (TypeError, ValueError):
                code = 0
            if code != 0:
                if code == CODE_STEP_MOTOR_NEED_RESET:
                    _motors_unhomed = True
                return None
        time.sleep(0.04)
    return None


def _motor_run_to(motor_id: int, position: float) -> bool:
    from dwarf_python_api.proto import motor_control_pb2

    message = motor_control_pb2.ReqMotorRunTo()
    message.id = int(motor_id)
    message.end_position = float(position)
    message.speed = 10
    message.speed_ramping = 100
    message.resolution_level = 3
    return send_without_response(message, 14001, 6)


def _wide_linkage_pixels(nx: float, ny: float) -> tuple[int, int]:
    """Map a 0-1 wide-view tap onto firmware DualCameraLinkage pixels.

    Cmd 14009 already slews that wide-frame pixel onto the tele camera.
    Do not add the PictureMatching box: live taps showed that shift pulling
    a left-side click (raw 553) to near-centre (838).
    """
    x = nx * (_LINKAGE_W - 1)
    y = ny * (_LINKAGE_H - 1)
    return (
        int(round(max(0.0, min(float(_LINKAGE_W - 1), x)))),
        int(round(max(0.0, min(float(_LINKAGE_H - 1), y)))),
    )


def _send_dual_camera_linkage(x: int, y: int) -> bool:
    """Dual Lenses Locating (official app double-tap). CMD 14009, MODULE_MOTOR."""
    from dwarf_python_api.proto import motor_control_pb2

    message = motor_control_pb2.ReqDualCameraLinkage()
    message.x = int(x)
    message.y = int(y)
    return send_without_response(message, 14009, 6)


def _center_wide_view(nx: float, ny: float, fov_h: float, fov_v: float) -> dict[str, Any]:
    """Slew so a 0-1 wide-frame tap lands on the wide-view crosshair.

    Dual Lenses Locating is the official double-tap and works unhomed. RunTo
    by FOV is only a fallback if that command fails.
    """
    nx = max(0.0, min(1.0, float(nx)))
    ny = max(0.0, min(1.0, float(ny)))
    x, y = _wide_linkage_pixels(nx, ny)
    detail = {
        "path": "14009",
        "x": x,
        "y": y,
        "nx": nx,
        "ny": ny,
        "ok": False,
    }
    log(
        f"Center tap ({nx:.3f}, {ny:.3f}) → Dual Lenses Locating ({x}, {y}) of {_LINKAGE_W}×{_LINKAGE_H}",
        "info",
    )
    if _send_dual_camera_linkage(x, y):
        detail["ok"] = True
        return detail
    yaw_delta = (nx - 0.5) * float(fov_h)
    pitch_delta = (0.5 - ny) * float(fov_v)
    az = _motor_position(1)
    alt = _motor_position(2) if az is not None else None
    if az is None or alt is None:
        log("Dual Lenses Locating failed and mount position is unavailable", "error")
        return detail
    log(
        f"Center fallback RunTo yaw {yaw_delta:+.2f}° pitch {pitch_delta:+.2f}° "
        f"from ({az:.2f}, {alt:.2f})",
        "info",
    )
    moved = True
    if abs(yaw_delta) >= 0.05:
        moved = _motor_run_to(1, az + yaw_delta) and moved
    if abs(pitch_delta) >= 0.05:
        moved = _motor_run_to(2, alt + pitch_delta) and moved
    detail["path"] = "runto"
    detail["ok"] = bool(moved)
    return detail


_FOCUS_FAR = 0
_FOCUS_NEAR = 1
_FOCUS_STEP_CLOSE = 8


def _focus_position() -> int | None:
    snap = _tap.snapshot() if _tap else {}
    value = snap.get("focus_position")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _set_focus_position(target: int) -> bool:
    """Move the focus motor to an absolute step count reported by telemetry."""
    from dwarf_python_api.proto import focus_pb2

    target = int(target)
    current = _focus_position()
    if current is None:
        raise RuntimeError("Focus position is unknown. Wait for telemetry, then try again.")
    if abs(current - target) <= 1:
        return True

    def direction_for(position: int) -> int:
        return _FOCUS_NEAR if target < position else _FOCUS_FAR

    def passed(position: int, direction: int) -> bool:
        return position <= target if direction == _FOCUS_NEAR else position >= target

    deadline = time.monotonic() + 45.0
    while abs(current - target) > 1:
        if _stop.is_set():
            raise InterruptedError("Focus move stopped")
        if time.monotonic() >= deadline:
            raise RuntimeError("Focus move timed out")
        direction = direction_for(current)
        if abs(current - target) > _FOCUS_STEP_CLOSE:
            message = focus_pb2.ReqManualContinuFocus()
            message.direction = direction
            if send_without_response(message, 15002, 8) is False:
                return False
            burst_from = current
            burst_started = time.monotonic()
            try:
                while time.monotonic() < deadline:
                    if _stop.is_set():
                        raise InterruptedError("Focus move stopped")
                    time.sleep(0.05)
                    position = _focus_position()
                    if position is None:
                        continue
                    current = position
                    if passed(current, direction) or abs(current - target) <= _FOCUS_STEP_CLOSE:
                        break
                    if current == burst_from and time.monotonic() - burst_started > 2.5:
                        raise RuntimeError("Focus motor did not move")
                else:
                    raise RuntimeError("Focus move timed out")
            finally:
                send_without_response(focus_pb2.ReqStopManualContinuFocus(), 15003, 8)
            updated = _focus_position()
            current = current if updated is None else updated
            continue
        message = focus_pb2.ReqManualSingleStepFocus()
        message.direction = direction
        if send_without_response(message, 15001, 8) is False:
            return False
        time.sleep(0.08)
        position = _focus_position()
        if position is None:
            continue
        if position == current:
            time.sleep(0.12)
            position = _focus_position()
            if position is None or position == current:
                if abs(current - target) <= _FOCUS_STEP_CLOSE:
                    return True
                raise RuntimeError("Focus motor did not move")
        current = position
        if passed(current, direction):
            break
    return True


def sdk_call(operation: str, *args: Any) -> Any:
    global _motors_unhomed
    if _api is None:
        raise RuntimeError("Telescope worker is not configured")
    if operation == "astro_mode":
        return _ensure_astro_mode()
    if operation == "timezone":
        return _set_timezone()
    if operation == "location":
        return _set_location()
    if operation in ("calibrate", "polar", "goto", "goto_solar"):
        # These home the steppers, so let the next centre tap probe positions again.
        _motors_unhomed = False
    if operation in ("joystick", "stop_motors"):
        from dwarf_python_api.proto import motor_control_pb2

        if operation == "joystick":
            message = motor_control_pb2.ReqMotorServiceJoystick()
            message.vector_angle = float(args[0])
            message.vector_length = float(args[1])
            return send_without_response(message, 14006, 6)
        return send_without_response(motor_control_pb2.ReqMotorServiceJoystickStop(), 14008, 6)
    if operation == "center_tap":
        nx = float(args[0]) if args else 0.5
        ny = float(args[1]) if len(args) > 1 else 0.5
        fov_h = float(args[2]) if len(args) > 2 else 0.0
        fov_v = float(args[3]) if len(args) > 3 else 0.0
        if fov_h <= 0 or fov_v <= 0:
            snap = _tap.snapshot() if _tap else {}
            try:
                fov_h = float(snap.get("wide_fov_h") or 0)
                fov_v = float(snap.get("wide_fov_v") or 0)
            except (TypeError, ValueError):
                fov_h = fov_v = 0.0
        if fov_h <= 0 or fov_v <= 0:
            fov_h, fov_v = 45.06, 25.93
        return _center_wide_view(nx, ny, fov_h, fov_v)
    if operation == "manual_focus":
        from dwarf_python_api.proto import focus_pb2

        message = focus_pb2.ReqManualSingleStepFocus()
        message.direction = int(args[0])
        return send_without_response(message, 15001, 8)
    if operation == "set_focus":
        return _set_focus_position(int(args[0]))
    if operation == "normal_autofocus":
        # Live/photo AF (15000). Contrast-detects a bright scene; on a night
        # sky it racks toward infinity or fails. Keep for photo mode only.
        from dwarf_python_api.proto import focus_pb2

        return send_without_response(focus_pb2.ReqNormalAutoFocus(), 15000, 8)
    capture_messages = {
        "burst_start": ("ReqBurstPhoto", 10003),
        "burst_stop": ("ReqStopBurstPhoto", 10004),
        "record_start": ("ReqStartRecord", 10005),
        "record_stop": ("ReqStopRecord", 10006),
        "timelapse_start": ("ReqStartTimeLapse", 10033),
        "timelapse_stop": ("ReqStopTimeLapse", 10034),
    }
    if operation in capture_messages:
        from dwarf_python_api.proto import camera_pb2

        message_name, command = capture_messages[operation]
        return send_without_response(getattr(camera_pb2, message_name)(), command, 1)
    if _device.get("model") in ("Dwarf 3", "Dwarf Mini"):
        if operation in ("calibrate", "stop_calibrate", "polar", "stop_polar", "goto", "goto_solar"):
            from dwarf_python_api.proto import astro_pb2

            if operation == "goto":
                message = astro_pb2.ReqGotoDSO()
                message.ra = float(args[0])
                message.dec = float(args[1])
                message.target_name = str(args[2] if len(args) > 2 else "")
                # Match astro_dwarf_session / perform_goto: goto_only=False so
                # the firmware starts sidereal tracking after the slew/solve.
                message.goto_only = bool(args[3]) if len(args) > 3 else False
                if len(args) > 4 and args[4] is not None:
                    message.rotation = int(args[4])
                return send_without_response(message, 11002, 3)
            if operation == "goto_solar":
                message = astro_pb2.ReqGotoSolarSystem()
                message.index = int(args[0])
                message.lon = float(_device.get("longitude", 0))
                message.lat = float(_device.get("latitude", 0))
                message.target_name = str(args[1] if len(args) > 1 else "")
                if len(args) > 2:
                    message.force_start = bool(args[2])
                return send_without_response(message, 11003, 3)
            astro_messages = {
                "calibrate": ("ReqStartCalibration", 11000),
                "stop_calibrate": ("ReqStopCalibration", 11001),
                "polar": ("ReqStartEqSolving", 11018),
                "stop_polar": ("ReqStopEqSolving", 11019),
            }
            message_name, command = astro_messages[operation]
            message = getattr(astro_pb2, message_name)()
            if operation == "polar":
                message.lon = float(_device.get("longitude", 0))
                message.lat = float(_device.get("latitude", 0))
            return send_without_response(message, command, 3)
        if operation in ("autofocus", "stop_autofocus"):
            from dwarf_python_api.proto import focus_pb2

            if operation == "autofocus":
                message = focus_pb2.ReqAstroAutoFocus()
                message.mode = int(args[0]) if args else 0
                return send_without_response(message, 15004, 8)
            return send_without_response(focus_pb2.ReqStopAstroAutoFocus(), 15005, 8)
    function_name = FUNCTIONS.get(operation)
    function = getattr(_api, function_name, None) if function_name else None
    if function is None:
        raise NotImplementedError(f"Installed SDK does not provide '{operation}'")
    return _invoke_sdk(operation, function, *args)


def _invoke_sdk(operation: str, function: Any, *args: Any, label: str | None = None) -> Any:
    """Run one blocking SDK call with the shared stop/interrupt bookkeeping."""
    label = label or operation.replace("_", " ").title()
    # Periodic state refreshes are plumbing; keep them out of the main log.
    call_level = "debug" if operation in _QUIET_OPERATIONS else "sdk"
    global _in_flight
    _drain_result_queue()
    _in_flight = operation
    try:
        # Publish _in_flight before reading _stop; request_stop() does the
        # reverse, so a stop can never slip between the check and the call.
        if _session_active.is_set() and _stop.is_set():
            raise InterruptedError("Session stopped")
        log(f"{label}…", call_level)
        with contextlib.redirect_stdout(sys.stderr):
            result = function(*args)
    finally:
        _in_flight = None
    log(f"{label}: {result}", call_level)
    return result


def _send_request(operation: str, message: Any, command: int, module_id: int, label: str) -> Any:
    """Send a protobuf request through the SDK socket and return the raw reply code.

    Unlike the ``perform_*`` wrappers (which collapse every failure to ``False``),
    ``connect_socket`` hands back the device's error code, e.g. -11503 when no
    matching dark frames exist.
    """
    if _api is None:
        raise RuntimeError("Telescope worker is not configured")
    return _invoke_sdk(operation, _api.connect_socket, message, command, 0, module_id, label=label)


def serializable_state(value: Any) -> Any:
    """Convert SDK/protobuf state into JSON-safe values without inventing fields."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): serializable_state(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable_state(item) for item in value]
    try:
        from google.protobuf.json_format import MessageToDict
        from google.protobuf.message import Message

        if isinstance(value, Message):
            return MessageToDict(value, preserving_proto_field_name=True)
    except ImportError:
        pass
    if hasattr(value, "__dict__"):
        data = {
            str(key): serializable_state(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
        if data:
            return data
    return {"value": str(value)}


_BLE_NAME_PREFIXES = {
    "Dwarf II": ("DWARF2", "DWARFII"),
    "Dwarf 3": ("DWARF3",),
    "Dwarf Mini": ("DWARF_MINI", "DWARFMINI"),
}


def _patch_bleak_for_dwarf_sdk() -> None:
    """dwarf_ble_connect still uses Bleak 0.x methods removed in Bleak 3."""
    import functools

    from bleak import BleakClient

    if not hasattr(BleakClient, "set_disconnected_callback"):
        def set_disconnected_callback(self, callback=None, **_kwargs):
            backend = getattr(self, "_backend", None)
            if backend is None:
                return
            backend._disconnected_callback = (
                None if callback is None else functools.partial(callback, self)
            )

        BleakClient.set_disconnected_callback = set_disconnected_callback

    if not hasattr(BleakClient, "get_services"):
        async def get_services(self, **_kwargs):
            return self.services

        BleakClient.get_services = get_services


def _run_async(factory):
    result: dict[str, Any] = {}

    def target() -> None:
        try:
            from bleak.backends.winrt.util import allow_sta

            allow_sta()
        except Exception:
            pass
        try:
            _patch_bleak_for_dwarf_sdk()
        except Exception:
            pass
        try:
            result["value"] = asyncio.run(factory())
        except RuntimeError as exc:
            if "Event loop is closed" not in str(exc):
                result["error"] = exc
                return
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result["value"] = loop.run_until_complete(factory())
            except Exception as retry_exc:
                result["error"] = retry_exc
            finally:
                loop.close()
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=target, name="dwarf-ble", daemon=True)
    thread.start()
    thread.join(timeout=90)
    if thread.is_alive():
        raise TimeoutError("Bluetooth operation timed out")
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _write_config_ip(ip: str, dwarf_id: Any = None) -> None:
    path = Path("config.py")
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = []
    for line in lines:
        if line.startswith("DWARF_IP "):
            updated.append(f'DWARF_IP = "{ip}"')
        elif dwarf_id is not None and line.startswith("DWARF_ID "):
            updated.append(f'DWARF_ID = "{dwarf_id}"')
        else:
            updated.append(line)
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    _device["ip_address"] = ip


def _ble_name_key(name: str) -> str:
    return (name or "").replace(" ", "").replace("-", "_").upper()


def _pick_ble_device(devices: list[Any], model: str) -> Any:
    prefixes = _BLE_NAME_PREFIXES.get(model, ())
    matches = [
        device
        for device in devices
        if any(_ble_name_key(device.name).startswith(prefix) for prefix in prefixes)
    ]
    chosen = (matches or devices)[0]
    if len(matches or devices) > 1:
        log(f"Several Dwarf Bluetooth devices found; using {chosen.name}")
    return chosen


def _is_dwarf_hotspot(ssid: str) -> bool:
    name = (ssid or "").replace(" ", "").replace("-", "_").upper()
    return name.startswith(("DWARF3", "DWARF_MINI", "DWARFMINI", "DWARF2", "DWARFII", "DWARF_"))


def _station_credentials(ssid: str, password: str) -> tuple[str, str]:
    if not ssid or not password or _is_dwarf_hotspot(ssid):
        return "", ""
    return ssid, password


def _run_netsh(*args: str) -> str:
    completed = subprocess.run(
        ["netsh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )
    return f"{completed.stdout or ''}{completed.stderr or ''}"


def _visible_wifi_ssids() -> list[str]:
    names: list[str] = []
    for line in _run_netsh("wlan", "show", "networks").splitlines():
        stripped = line.strip()
        if stripped.startswith("SSID") and ":" in stripped:
            name = stripped.split(":", 1)[1].strip()
            if name:
                names.append(name)
    return names


def _hotspot_password() -> str:
    return str(_device.get("wifi_password") or _device.get("ble_password") or "DWARF_12345678")


def _host_reachable(host: str, port: int = 8092, timeout: float = 1.5) -> bool:
    try:
        socket.create_connection((host, port), timeout).close()
        return True
    except OSError:
        return False


def _choose_hotspot_ssid(preferred: str) -> str:
    visible = _visible_wifi_ssids()
    candidates: list[str] = []
    for name in (preferred, str(_device.get("_ble_ssid") or ""), str(_device.get("wifi_ssid") or "")):
        if name and name not in candidates:
            candidates.append(name)
    for name in visible:
        if _is_dwarf_hotspot(name) and name not in candidates:
            candidates.append(name)
    for name in candidates:
        if name in visible:
            return name
    raise RuntimeError(
        "No Dwarf hotspot is visible on this computer's Wi-Fi. "
        "Power the telescope on and keep it close."
    )


def _join_dwarf_hotspot(preferred_ssid: str, control_ip: str) -> None:
    if _host_reachable(control_ip):
        return
    if sys.platform != "win32":
        raise RuntimeError("Automatic hotspot join is only available on Windows.")
    ssid = _choose_hotspot_ssid(preferred_ssid)
    password = _hotspot_password()
    log(f"Joining telescope hotspot {ssid}…")
    profile = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{html.escape(ssid)}</name>
    <SSIDConfig>
        <SSID>
            <name>{html.escape(ssid)}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{html.escape(password)}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "dwarf-hotspot.xml"
        path.write_text(profile, encoding="utf-8")
        added = _run_netsh("wlan", "add", "profile", f"filename={path}", "user=current")
        if "error" in added.lower() and "added" not in added.lower() and "updated" not in added.lower():
            raise RuntimeError(f"Could not save the hotspot profile: {added.strip() or 'netsh failed'}")
        connected = _run_netsh("wlan", "connect", f"name={ssid}", f"ssid={ssid}")
        if "error" in connected.lower() and "success" not in connected.lower():
            raise RuntimeError(f"Could not join {ssid}: {connected.strip() or 'netsh failed'}")
    for _ in range(20):
        if _host_reachable(control_ip):
            log(f"Reached the telescope at {control_ip}")
            return
        time.sleep(1)
    raise RuntimeError(
        f"This computer joined {ssid}, but {control_ip} is still unreachable."
    )


def _ensure_hotspot_link(ip: str) -> None:
    if ip != "192.168.88.1" and not _is_dwarf_hotspot(str(_device.get("_ble_ssid") or "")):
        return
    _join_dwarf_hotspot(str(_device.get("_ble_ssid") or ""), ip or "192.168.88.1")


def _set_wifi_ap_message(ble_password: str) -> bytes:
    import dwarf_python_api.proto.ble_pb2 as ble
    from dwarf_ble_connect.lib.dwarf_protocol_ble import create_packet_ble

    message = ble.ReqAp()
    message.cmd = 2
    message.wifi_type = 0
    message.auto_start = 1
    message.country_list = 0
    message.ble_psd = ble_password
    return create_packet_ble(2, message)


async def _ble_wifi_session(
    dwarf: Any,
    ble_password: str,
    sta_ssid: str,
    sta_password: str,
    preferred: str = "auto",
) -> dict[str, Any]:
    from bleak import BleakClient
    from dwarf_ble_connect.lib.dwarf_lib_ble import DWARF_CHARACTERISTIC_UUID
    from dwarf_ble_connect.lib.dwarf_protocol_ble import (
        analyze_packet_ble,
        get_wifi_config_message,
        set_wifi_STA_message,
    )

    replies: dict[int, dict[str, Any]] = {}
    wanted = {"cmd": 1}
    ready = asyncio.Event()

    def on_notify(_sender, data) -> None:
        parsed = analyze_packet_ble(data)
        if not parsed or parsed.get("cmd") != wanted["cmd"]:
            return
        replies[int(parsed["cmd"])] = parsed
        ready.set()

    async def write_and_wait(payload: bytes, cmd: int, timeout: float) -> dict[str, Any]:
        wanted["cmd"] = cmd
        ready.clear()
        await client.write_gatt_char(DWARF_CHARACTERISTIC_UUID, payload)
        await asyncio.wait_for(ready.wait(), timeout)
        return replies.get(cmd) or {}

    client = BleakClient(dwarf.address, timeout=15)
    await client.connect()
    try:
        await client.start_notify(DWARF_CHARACTERISTIC_UUID, on_notify)
        config = await write_and_wait(get_wifi_config_message(ble_password), 1, 8)
        code = config.get("code")
        if code not in (0, None):
            if code == -1:
                raise RuntimeError(
                    "Bluetooth password rejected. Set it under Settings (factory default is DWARF_12345678)."
                )
            raise RuntimeError(f"Bluetooth config error: {code}")

        current_ip = str(config.get("ip") or "").strip()
        current_ssid = str(config.get("ssid") or "").strip()
        wifi_mode = config.get("wifi_mode")
        mode_name = {1: "AP", 2: "STA"}.get(wifi_mode, f"mode {wifi_mode}")
        log(f"Telescope Wi-Fi is {mode_name}" + (f" ({current_ssid} at {current_ip})" if current_ip else ""))

        async def start_hotspot() -> dict[str, Any]:
            log("Starting telescope hotspot…")
            try:
                ap = await write_and_wait(_set_wifi_ap_message(ble_password), 2, 15)
            except TimeoutError:
                ap = {}
            if ap.get("code") not in (0, None):
                raise RuntimeError(f"Could not start telescope hotspot: {ap.get('code')}")
            return {
                "ip_address": "192.168.88.1",
                "ssid": str(ap.get("ssid") or current_ssid),
                "wifi_mode": 1,
            }

        if preferred == "ap":
            if wifi_mode == 1:
                return {"ip_address": current_ip or "192.168.88.1", "ssid": current_ssid, "wifi_mode": 1}
            return await start_hotspot()

        if preferred == "sta":
            if not sta_ssid:
                raise RuntimeError(
                    "Station mode needs the router's Wi-Fi name and password. "
                    "Do not enter the Dwarf hotspot name."
                )
            log(f"Asking the telescope to join {sta_ssid}…")
            try:
                sta = await write_and_wait(
                    set_wifi_STA_message(1, ble_password, sta_ssid, sta_password),
                    3,
                    20,
                )
            except TimeoutError:
                sta = {}
            if sta.get("code") == 0 and sta.get("ip"):
                return {"ip_address": str(sta["ip"]), "ssid": str(sta.get("ssid") or sta_ssid), "wifi_mode": 2}
            raise RuntimeError(str(sta.get("error") or f"The telescope could not join {sta_ssid}"))

        if current_ip:
            return {"ip_address": current_ip, "ssid": current_ssid, "wifi_mode": wifi_mode}
        return await start_hotspot()
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


def _mark_disconnected() -> None:
    global _motors_unhomed
    _connected.clear()
    # A reconnect may follow a calibration/home; probe the encoders again.
    _motors_unhomed = False
    if _tap is not None:
        _tap.reset()


def _safe_disconnect() -> None:
    _mark_disconnected()
    try:
        sdk_call("disconnect")
    except Exception:
        pass


def _handshake() -> dict[str, Any] | None:
    try:
        if sdk_call("host_master") is False:
            log("MASTER LOCK: no response (expected on V3). Continuing.", "warning")
    except NotImplementedError as exc:
        log(str(exc), "warning")
    except Exception as exc:
        log(f"MASTER LOCK skipped: {exc}", "warning")
    if sdk_call("time") is False:
        return None
    for operation in ("timezone", "location", "device_state"):
        try:
            sdk_call(operation)
        except NotImplementedError as exc:
            log(str(exc), "warning")
        except Exception as exc:
            log(f"{operation} skipped: {exc}", "warning")
    _connected.set()
    # Sessions connect on their own; tell the UI so STOP/DISCONNECT stay usable.
    emit({"event": "connected", "ip_address": str(_device.get("ip_address") or "")})
    if _tap is None:
        return {}
    status = _client_status()
    if status is not None:
        _tap.poll_client_status(status)
    _tap.flush()
    return _tap.snapshot()


def provision_bluetooth() -> str:
    try:
        from dwarf_ble_connect.lib.dwarf_lib_ble import discover_dwarf_devices
    except ImportError as exc:
        raise RuntimeError("Bluetooth support is not available in this install") from exc

    ssid = str(_device.get("wifi_ssid") or "")
    password = str(_device.get("wifi_password") or "")
    ble_password = str(_device.get("ble_password") or "DWARF_12345678")
    preferred = str(_device.get("wifi_mode") or "auto").lower()
    if preferred == "sta":
        sta_ssid, sta_password = _station_credentials(ssid, password)
        if not sta_ssid:
            raise RuntimeError(
                "Station mode needs the router's Wi-Fi name and password. "
                "Do not enter the Dwarf hotspot name."
            )
        log(f"Scanning Bluetooth to put the telescope on {sta_ssid}…")
    else:
        sta_ssid, sta_password = "", ""
        if preferred == "ap":
            log("Scanning Bluetooth to use the telescope hotspot…")
        else:
            log("Scanning Bluetooth to read the telescope Wi-Fi…")

    with contextlib.redirect_stdout(sys.stderr):
        found = _run_async(discover_dwarf_devices)
    devices = (found or {}).get("dwarf_devices") or []
    if found and found.get("error"):
        raise RuntimeError(f"Bluetooth scan failed: {found['error']}")
    if not devices:
        raise RuntimeError("No Dwarf found over Bluetooth. Power it on and keep it near this computer.")

    names = ", ".join(device.name or device.address for device in devices)
    log(f"Bluetooth found: {names}")
    dwarf = _pick_ble_device(devices, str(_device.get("model") or ""))
    log(f"Connecting to {dwarf.name} over Bluetooth…")

    with contextlib.redirect_stdout(sys.stderr):
        state = _run_async(lambda: _ble_wifi_session(dwarf, ble_password, sta_ssid, sta_password, preferred))
    if not state or not state.get("ip_address"):
        raise RuntimeError("Bluetooth connected but did not return an IP address")

    ip = str(state["ip_address"])
    _device["_ble_ssid"] = str(state.get("ssid") or "")
    _write_config_ip(ip, state.get("device_dwarf_id"))
    log(f"Bluetooth assigned IP {ip}")
    return ip


def connect() -> bool | dict[str, Any]:
    ip = str(_device.get("ip_address") or "").strip()
    ble_enabled = bool(_device.get("ble_enabled"))
    if ip:
        log(f"Connecting to {ip}…")
        if ip == "192.168.88.1" and not _host_reachable(ip):
            _ensure_hotspot_link(ip)
        telemetry = _handshake()
        if telemetry is not None:
            return {"ip_address": ip, "telemetry": telemetry}
        log("IP connection failed" + (", trying Bluetooth…" if ble_enabled else ""), "warning")
        _safe_disconnect()
    elif not ble_enabled:
        raise RuntimeError("Set a telescope IP, or enable Bluetooth and try again")

    if not ble_enabled:
        return False

    discovered = provision_bluetooth()
    _ensure_hotspot_link(discovered)
    for attempt in range(1, 6):
        telemetry = _handshake()
        if telemetry is not None:
            return {"ip_address": discovered, "telemetry": telemetry}
        log(f"Waiting for the telescope at {discovered} ({attempt}/5)…")
        time.sleep(3)
        _safe_disconnect()
    hotspot = str(_device.get("_ble_ssid") or "")
    mode = str(_device.get("wifi_mode") or "auto").lower()
    if discovered == "192.168.88.1" or _is_dwarf_hotspot(hotspot) or mode == "ap":
        name = hotspot or "the Dwarf hotspot"
        raise RuntimeError(
            f"The telescope hotspot {name} is on at {discovered}, but this computer still cannot reach it."
        )
    if mode == "sta":
        raise RuntimeError(
            f"The telescope joined Wi-Fi at {discovered}, but this computer cannot reach it. "
            "Connect this computer to the same router network."
        )
    raise RuntimeError(
        f"Bluetooth found {discovered}, but this computer cannot reach the telescope over Wi-Fi."
    )


def _error_name(code: int) -> str:
    try:
        from dwarf_python_api.lib.websockets_utils import getErrorCodeValueName

        name = str(getErrorCodeValueName(code) or "").strip()
        if name and name != str(code):
            return f"{name} ({code})"
    except Exception:
        pass
    return f"code {code}"


# Fire-and-forget V3 commands: (reply command id, telemetry state key, done-on-reply, timeout s)
_V3_OPERATION_WAITS: dict[str, tuple[int, str | None, bool, float]] = {
    "autofocus": (15004, None, True, 180.0),
    "calibrate": (11000, "calibration_state", False, 600.0),
    "polar": (11018, "eq_state", True, 600.0),
    "goto": (11002, "goto_state", False, 300.0),
    "goto_solar": (11003, "goto_state", False, 300.0),
}
_NON_FATAL_REPLIES = {
    11000: {-11500},  # plate solving retry during calibration
    11002: {-11500},
    11003: {-11500},
}
_BUSY_ASTRO = {"running", "solving", "stopping"}


def _await_operation(name: str, operation: str, since: float) -> None:
    """Block until a fire-and-forget V3 operation finishes, fails or times out.

    Dwarf 3 / Mini start calibration, autofocus, polar alignment and GOTO
    without waiting for the slew/solve to finish. The session watches
    telemetry: calibration/EQ/autofocus send a reply when they end, GOTO
    is acknowledged up front, and state notifications report
    running → solving → idle/stopped. GOTO then has to hand off to
    tracking (same as astro_dwarf_session) before capture can start.
    """
    if _tap is None:
        return
    reply_cmd, state_key, done_on_reply, timeout = _V3_OPERATION_WAITS[operation]
    goto = operation in ("goto", "goto_solar")
    seen_running = False
    snapshot = _tap.snapshot()
    state = snapshot.get(state_key) if state_key else None
    if state in _BUSY_ASTRO:
        seen_running = True
    elif goto and snapshot.get("tracking_state") == "running" and (time.monotonic() - since) > 5:
        # GOTO already handed off to tracking before we started waiting.
        return
    log(f"{name} started; waiting for the telescope to finish…")
    logged_tracking_wait = False
    while True:
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        snapshot = _tap.snapshot()
        code = _tap.response_after(reply_cmd, since)
        if code is not None and code != 0 and code not in _NON_FATAL_REPLIES.get(reply_cmd, set()):
            raise RuntimeError(f"{name} failed: {_error_name(code)}")
        if code == 0 and done_on_reply:
            return
        state = snapshot.get(state_key) if state_key else None
        if state in _BUSY_ASTRO:
            seen_running = True
        tracking = snapshot.get("tracking_state") == "running"
        if goto and tracking:
            return
        if goto and seen_running and state in ("idle", "stopped") and not logged_tracking_wait:
            log("GOTO finished; waiting for tracking to start…")
            logged_tracking_wait = True
        if seen_running and state in ("idle", "stopped") and not goto:
            return
        elapsed = time.monotonic() - since
        if elapsed > timeout:
            if goto and not tracking:
                raise RuntimeError(
                    f"{name} finished but tracking did not start. "
                    "Set the telescope to your observing site, then retry."
                )
            raise RuntimeError(f"{name} timed out after {int(timeout)} s")
        if state_key and not seen_running and elapsed > 30:
            raise RuntimeError(f"{name} did not start")
        time.sleep(0.5)


def _wait_for_capture_slot(progress: Any = None) -> None:
    """Do not start stacking while GOTO or calibration still owns the astro engine.

    Tracking taking over means the GOTO has finished, even if a stale GOTO
    state lingers in telemetry. When the wait runs out we still try to
    capture: the firmware is the authority and ``_start_capture`` retries on
    a real busy reply.
    """
    if _tap is None:
        return
    deadline = time.monotonic() + 60.0
    logged = False
    while time.monotonic() < deadline:
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        snapshot = _tap.snapshot()
        if snapshot.get("tracking_state") == "running":
            return
        if snapshot.get("goto_state") not in _BUSY_ASTRO and snapshot.get("calibration_state") not in _BUSY_ASTRO:
            return
        if not logged:
            log("Waiting for the telescope to finish slewing before capture…")
            if progress:
                progress("Waiting for slew to finish")
            logged = True
        time.sleep(0.5)
    log("Telemetry still reports the telescope busy; asking it to start capture anyway", "warning")


# Capture starts: worker operation -> request command id (all on the astro module)
_MODULE_ASTRO = 3
_CAPTURE_STARTS: dict[str, int] = {"astro": 11005, "wide_astro": 11016, "mosaic": 11031}
CMD_ASTRO_CONTINUE_SHOOTING = 11050
CODE_ASTRO_FUNCTION_BUSY = -11501
CODE_ASTRO_DARK_NOT_FOUND = -11503
CODE_ASTRO_GOTO_RUNNING = -11508
CODE_ASTRO_DARK_TEMP_MISMATCH = -11530
# The astro engine is still winding down GOTO/calibration; try again shortly.
_CAPTURE_BUSY_CODES = {CODE_ASTRO_FUNCTION_BUSY, CODE_ASTRO_GOTO_RUNNING}
# Recoverable warnings the official app lets the user bypass ("continue shooting").
_CAPTURE_DARK_WARNINGS = {
    CODE_ASTRO_DARK_NOT_FOUND: "No matching dark frames for this exposure/gain/binning",
    CODE_ASTRO_DARK_TEMP_MISMATCH: "Matching dark frames were taken at a different sensor temperature",
}
_CAPTURE_BUSY_TIMEOUT_S = 45.0
_CAPTURE_BUSY_RETRY_S = 5.0
_CONTINUE_SHOOTING_TIMEOUT_S = 30.0
_CAPTURE_CONTINUE_AFTER_S = 10.0
_CAPTURE_START_TIMEOUT_S = 45.0
_CAPTURE_HEARTBEAT_S = 60.0


def _ir_index(name: Any) -> int:
    """IR index on START_CAPTURE: Duo-Band is 2, everything else is 1.

    VIS is applied with ``set_ir``; the capture command itself matches the
    SDK/session-app default (``perform_takeAstroPhoto(ir_index=1)``).
    """
    text = str(name or "").strip().lower()
    if text.startswith("duo") or text == "2":
        return 2
    return 1


def _capture_request(operation: str, args: list[Any], force_start: bool) -> Any:
    from dwarf_python_api.proto import astro_pb2

    if operation == "astro":
        message = astro_pb2.ReqCaptureRawLiveStacking()
        message.ir_index = int(args[0]) if args else 1
        message.force_start = force_start
        return message
    if operation == "mosaic":
        message = astro_pb2.ReqStartMosaic()
        message.horizontal_scale = int(args[0])
        message.vertical_scale = int(args[1])
        message.rotation = int(round(float(args[2]))) if len(args) > 2 else 0
        message.ir_index = int(args[3]) if len(args) > 3 else 1
        message.force_start = force_start
        return message
    wide_factory = getattr(astro_pb2, "ReqCaptureWideRawLiveStacking", None)
    if wide_factory is not None:
        message = wide_factory()
        if force_start and hasattr(message, "force_start"):
            message.force_start = True
        return message
    # Older SDK protos only ship the tele request; the wide start accepts an empty body.
    return astro_pb2.ReqCaptureRawLiveStacking()


def _capture_running(snapshot: dict[str, Any]) -> bool:
    return bool(snapshot.get("capture_active")) or snapshot.get("capture_state") == "running"


def _reset_session_capture(session: dict[str, Any] | None = None) -> None:
    """Drop leftover stacking counts so the HUD does not keep the previous run."""
    if _tap is None:
        return
    total = None
    target = ""
    if session is not None:
        camera = session.get("camera") or {}
        target = str((session.get("target") or {}).get("name") or "")
        try:
            total = int(camera.get("frame_count") or 0) or None
        except (TypeError, ValueError):
            total = None
    else:
        snapshot = _tap.snapshot()
        try:
            total = int(snapshot.get("capture_total") or 0) or None
        except (TypeError, ValueError):
            total = None
        target = str(snapshot.get("capture_target") or "")
    _tap.reset_capture_progress(total=total, target=target)


def _arm_sdk_capture_rejoin(wide: bool) -> None:
    """Mark the SDK cache so a reconnect still treats STOPPED as this capture ending."""
    try:
        from dwarf_python_api.lib import websockets_utils

        client = getattr(websockets_utils, "client_instance", None)
        if client is None:
            return
        if wide:
            client.RestartAstroWideCapture = True
            client.takeWidePhotoStarted = True
            client.AstroWideCapture = True
        else:
            client.RestartAstroCapture = True
            client.takePhotoStarted = True
            client.AstroCapture = True
    except Exception:
        pass


def _same_capture_target(session: dict[str, Any], snapshot: dict[str, Any]) -> bool:
    session_name = str((session.get("target") or {}).get("name") or "").strip().lower()
    live_name = str(snapshot.get("capture_target") or snapshot.get("tracking_target") or "").strip().lower()
    if not session_name or not live_name:
        return True
    return session_name == live_name or session_name in live_name or live_name in session_name


def _format_duration(seconds: float) -> str:
    value = max(0, int(round(float(seconds or 0))))
    hours, rem = divmod(value, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _capture_counts(snapshot: dict[str, Any]) -> tuple[int, int]:
    try:
        current = int(snapshot.get("capture_current") or 0)
    except (TypeError, ValueError):
        current = 0
    try:
        stacked = int(snapshot.get("capture_stacked") or 0)
    except (TypeError, ValueError):
        stacked = 0
    try:
        total = int(snapshot.get("capture_total") or 0)
    except (TypeError, ValueError):
        total = 0
    return max(current, stacked), total


def _capture_wait_label(name: str, snapshot: dict[str, Any]) -> str:
    frames, total = _capture_counts(snapshot)
    if total:
        return f"{name} · {frames}/{total}"
    if frames:
        return f"{name} · {frames} frames"
    return name


def _wait_for_capture_end(on_progress: Any = None, name: str = "Waiting for capture") -> None:
    """Watch telemetry until stacking stops.

    The SDK ``wait_astro`` call parks on an empty socket wait with no HUD
    updates, and it never sends CONTINUE SHOOTING when firmware accepts
    START_CAPTURE (code 0) then raises a missing-darks warning.
    """
    seen = False
    continued = False
    quiet_since: float | None = None
    started = time.monotonic()
    last_label = ""
    last_heartbeat = started
    log(f"{name}; watching the telescope for stacking progress…")
    while True:
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        snapshot = _tap.snapshot() if _tap is not None else {}
        elapsed = time.monotonic() - started
        if _capture_running(snapshot):
            if not seen:
                frames, total = _capture_counts(snapshot)
                detail = f"{frames}/{total}" if total else "stacking started"
                log(f"Capture running · {detail}")
            seen = True
            quiet_since = None
        elif seen:
            state = str(snapshot.get("capture_state") or "")
            if state in ("stopped", "idle"):
                log(f"{name} finished after {_format_duration(elapsed)}")
                return
            if quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= 20.0:
                log(f"{name} finished after {_format_duration(elapsed)}")
                return
        elif elapsed >= _CAPTURE_CONTINUE_AFTER_S and not continued:
            continued = True
            log("Capture has not started yet; trying CONTINUE SHOOTING", "warning")
            if _continue_shooting("Capture"):
                continue
        elif elapsed >= _CAPTURE_START_TIMEOUT_S:
            raise RuntimeError(
                f"{name} failed: the telescope never started stacking. "
                "If dark frames are missing, add matching darks or retry."
            )
        if on_progress:
            label = _capture_wait_label(name, snapshot)
            if label != last_label:
                on_progress(label)
                last_label = label
        if seen and time.monotonic() - last_heartbeat >= _CAPTURE_HEARTBEAT_S:
            last_heartbeat = time.monotonic()
            frames, total = _capture_counts(snapshot)
            count = f"{frames}/{total}" if total else f"{frames} frames"
            log(f"Still capturing · {count} · {_format_duration(elapsed)}")
        time.sleep(0.5)


def _join_existing_capture(session: dict[str, Any], step: Any) -> bool:
    if _tap is None:
        return False
    snapshot = _tap.snapshot()
    if not _capture_running(snapshot):
        return False
    if not _same_capture_target(session, snapshot):
        live = snapshot.get("capture_target") or snapshot.get("tracking_target") or "another target"
        log(f"Telescope is stacking {live}; not joining this session", "warning")
        return False
    wide = snapshot.get("capture_camera") == "wide" or str((session.get("camera") or {}).get("camera") or "") == "wide"
    log("Telescope is already stacking; joining the in-progress capture", "notice")
    step(
        "Waiting for wide capture" if wide else "Waiting for capture",
        "wait_wide_resume" if wide else "wait_astro_resume",
    )
    return True


def _continue_shooting(name: str) -> bool:
    """Send CMD_ASTRO_CONTINUE_SHOOTING after a recoverable capture warning.

    This is what the official app does when the user taps through the
    missing-darks warning. The SDK has no reply handler for it, so send it
    fire-and-forget and watch the reply code / capture state via telemetry.
    """
    if _tap is None:
        return False
    try:
        from dwarf_python_api.proto import astro_pb2

        factory = getattr(astro_pb2, "ReqContinueShooting", None)
    except Exception:
        factory = None
    if factory is None:
        log("Installed SDK has no ReqContinueShooting message", "debug")
        return False
    since = time.monotonic()
    # A leftover "running" flag from an earlier capture must not count as success.
    stale_running = _capture_running(_tap.snapshot())
    log(f"{name}: continuing without matching dark frames (CONTINUE SHOOTING)", "warning")
    try:
        if not send_without_response(factory(), CMD_ASTRO_CONTINUE_SHOOTING, _MODULE_ASTRO):
            return False
    except Exception as exc:
        log(f"Continue shooting could not be sent: {exc}", "debug")
        return False
    while time.monotonic() - since < _CONTINUE_SHOOTING_TIMEOUT_S:
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        code = _tap.response_after(CMD_ASTRO_CONTINUE_SHOOTING, since)
        if code is not None and code != 0:
            log(f"Continue shooting rejected: {_error_name(code)}", "warning")
            return False
        if _capture_running(_tap.snapshot()) and (code == 0 or not stale_running):
            log(f"{name}: capture running without dark-frame calibration", "notice")
            return True
        time.sleep(0.5)
    log("Continue shooting sent, but the telescope did not start capturing", "warning")
    return False


def _start_capture(name: str, operation: str, args: list[Any]) -> None:
    """Start tele/wide/mosaic stacking, surfacing the real firmware reply.

    - Engine busy (GOTO/calibration still winding down): wait and retry.
    - Missing or mismatched darks: warn, then CONTINUE SHOOTING like the
      official app; fall back to a forced start if that is refused.
    - Anything else: fail with the decoded error name and code.
    """
    command = _CAPTURE_STARTS[operation]
    label = name
    deadline = time.monotonic() + _CAPTURE_BUSY_TIMEOUT_S
    force_start = False
    _reset_session_capture()
    while True:
        since = time.monotonic()
        if _tap is not None:
            _tap.release_capture_progress()
        message = _capture_request(operation, args, force_start)
        result = _send_request(operation, message, command, _MODULE_ASTRO, label)
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        # connect_socket returns the reply code (0 = accepted) or False; never
        # compare with == 0 directly because False == 0 in Python.
        code = result if isinstance(result, int) and not isinstance(result, bool) else None
        if result is True or code == 0:
            return
        if code is None and _tap is not None:
            code = _tap.response_after(command, since)
            if code == 0:
                # Accepted, but the SDK gave up before the running notification.
                if _capture_running(_tap.snapshot()):
                    return
                raise RuntimeError(f"{name} failed: the telescope accepted the request but never started capturing")
        if code is None:
            raise RuntimeError(f"{name} failed: no reply from the telescope")
        if code in _CAPTURE_BUSY_CODES:
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{name} failed: {_error_name(code)}")
            log(f"{name}: astro engine still busy ({_error_name(code)}); retrying in {int(_CAPTURE_BUSY_RETRY_S)} s", "warning")
            _reset_session_capture()
            if _stop.wait(_CAPTURE_BUSY_RETRY_S):
                raise InterruptedError("Session stopped")
            continue
        if code in _CAPTURE_DARK_WARNINGS and not force_start:
            log(f"{name}: {_CAPTURE_DARK_WARNINGS[code]} ({_error_name(code)})", "warning")
            if _continue_shooting(name):
                return
            log(f"{name}: retrying with a forced start", "warning")
            force_start = True
            label = f"{name} (forced)"
            continue
        raise RuntimeError(f"{name} failed: {_error_name(code)}")


def run_session(session: dict[str, Any]) -> bool:
    global _session_phase, _stop_phase
    _stop.clear()
    _session_active.set()
    _session_phase = None
    v3_model = _device.get("model") in ("Dwarf 3", "Dwarf Mini")
    completed = False

    def step(name: str, operation: str | None = None, *args: Any, wait_seconds: float = 0) -> None:
        global _session_phase
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        emit({
            "event": "progress",
            "session_id": session["id"],
            "step": name,
            "wait_seconds": wait_seconds,
        })
        if not operation:
            return
        _session_phase = operation
        started = time.monotonic()
        if operation in _CAPTURE_STARTS:
            _start_capture(name, operation, list(args))
            return
        if operation in ("wait_astro", "wait_astro_resume", "wait_wide", "wait_wide_resume"):
            wide = operation in ("wait_wide", "wait_wide_resume")
            if _tap is None:
                sdk_op = "wait_wide_resume" if operation == "wait_wide_resume" else (
                    "wait_astro_resume" if operation == "wait_astro_resume" else (
                        "wait_wide" if wide else "wait_astro"
                    )
                )
                if operation.endswith("_resume"):
                    _arm_sdk_capture_rejoin(wide=wide)
                if sdk_call(sdk_op) is False:
                    raise RuntimeError(f"{name} failed")
                return
            if operation.endswith("_resume"):
                _arm_sdk_capture_rejoin(wide=wide)
            _wait_for_capture_end(on_progress=lambda text: step(text), name=name.split(" · ")[0])
            return
        if sdk_call(operation, *args) is False:
            if _stop.is_set():
                raise InterruptedError("Session stopped")
            raise RuntimeError(f"{name} failed")
        if v3_model and operation in _V3_OPERATION_WAITS:
            _await_operation(name, operation, started)

    try:
        completed = _run_session_steps(session, step)
        return completed
    finally:
        leftover = not completed and not _stop.is_set()
        phase = _session_phase
        _session_active.clear()
        _session_phase = None
        if leftover:
            _stop_phase = phase
            try:
                log("Stopping leftover telescope activity after session ended", "warning")
                stop_all()
            except Exception as exc:
                log(f"Could not stop leftover activity: {exc}", "debug")


def _wait_seconds(seconds: float, message: str | None = None, progress: Any = None) -> None:
    seconds = max(0.0, float(seconds or 0))
    if seconds <= 0:
        return
    label = (message or "Waiting").rstrip("…").strip() or "Waiting"
    if message:
        log(f"{label} ({_format_duration(seconds)})")
    if progress:
        progress(label, wait_seconds=seconds)
    if _stop.wait(seconds):
        raise InterruptedError("Session stopped")


def _clear_tracking(progress: Any = None) -> None:
    """Stop leftover GOTO/tracking so calibration or EQ can own the astro engine."""
    log("Stopping leftover GOTO/tracking")
    try:
        sdk_call("stop_goto")
    except Exception as exc:
        log(f"Stop GOTO skipped: {exc}", "debug")
    _wait_seconds(5, "Waiting after stop GOTO", progress)


def _engine_busy_error(exc: BaseException) -> bool:
    text = str(exc)
    return any(token in text for token in ("FUNCTION_BUSY", "GOTO_RUNNING", "-11501", "-11508"))


def _run_v3_until_ready(name: str, operation: str, step: Any, *args: Any) -> None:
    """Start a V3 astro operation, retrying if the engine is still busy."""
    deadline = time.monotonic() + _CAPTURE_BUSY_TIMEOUT_S
    while True:
        try:
            step(name, operation, *args)
            return
        except RuntimeError as exc:
            if not _engine_busy_error(exc) or time.monotonic() >= deadline:
                raise
            log(f"{name}: astro engine still busy; clearing GOTO and retrying", "warning")
            _clear_tracking(step)


def _run_session_steps(session: dict[str, Any], step: Any) -> bool:
    target = session["target"]
    camera = session["camera"]
    workflow = session["workflow"]
    mosaic = session["mosaic"]
    model_id = {"Dwarf II": "2", "Dwarf 3": "3", "Dwarf Mini": "5"}.get(_device.get("model"), "3")

    if not connect():
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        raise RuntimeError("Could not connect to telescope")
    latitude, longitude = _site_coordinates()
    if abs(latitude) < 1e-9 and abs(longitude) < 1e-9:
        raise RuntimeError(
            "Telescope location is lat=0, long=0. Set your observing site before running a session."
        )
    if str(session.get("current_step") or "") in {"Joining capture", "Recovered after restart"}:
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            if _stop.is_set():
                raise InterruptedError("Session stopped")
            if _tap is not None and _capture_running(_tap.snapshot()):
                break
            time.sleep(0.25)
    if _join_existing_capture(session, step):
        return True
    _reset_session_capture(session)
    step("Closing previous capture", "go_live")
    _reset_session_capture(session)
    if target.get("kind") == "solar":
        solar_name = (target.get("solar_name") or target["name"]).lower()
        step("Entering solar mode", "shooting_mode", 8 if solar_name == "sun" else 9 if solar_name == "moon" else 10, 2)
    else:
        step("Entering astro mode", "astro_mode")
    _wait_seconds(workflow.get("wait_before_seconds", 0), "Waiting before workflow", step)
    # Match astro_dwarf_session: focus, then EQ, then calibration (after stop_goto).
    if workflow.get("autofocus"):
        step("Auto focus", "autofocus", False)
    if workflow.get("infinite_focus"):
        step("Infinity focus", "autofocus", True)
    if workflow.get("polar_align"):
        if not workflow.get("infinite_focus"):
            step("Infinity focus before polar alignment", "autofocus", True)
            _wait_seconds(5, "Waiting after infinity focus", step)
        _clear_tracking(step)
        _run_v3_until_ready("Polar alignment", "polar", step)
    if workflow.get("calibrate"):
        step("Calibration exposure", "set_exposure", "1", model_id, camera["camera"])
        step("Calibration gain", "set_gain", 80, camera["camera"])
        if camera["camera"] != "wide":
            step("Calibration filter", "set_ir", "1")
        step("Calibration binning", "set_binning", 0)
        _wait_seconds(5, "Waiting for calibration camera settings to apply", step)
        _clear_tracking(step)
        _run_v3_until_ready("Calibration", "calibrate", step)
    if workflow.get("goto") and target.get("ra_hours") is not None:
        step("GOTO target", "goto", target["ra_hours"], target["dec_degrees"], target["name"], False)
    elif workflow.get("goto") and target.get("kind") == "solar":
        ids = {"mercury": 1, "venus": 2, "mars": 3, "jupiter": 4, "saturn": 5, "uranus": 6, "neptune": 7, "moon": 8, "sun": 9}
        name = (target.get("solar_name") or target["name"]).lower()
        step("GOTO solar target", "goto_solar", ids[name], name.title())
    exposure_name = firmware_exposure_name(camera["exposure_seconds"])
    log(f"Astro photo: exposure {exposure_name}s, gain {camera['gain']}, count {camera['frame_count']}", "notice")
    step("Set exposure", "set_exposure", exposure_name, model_id, camera["camera"])
    step("Set gain", "set_gain", camera["gain"], camera["camera"])
    if camera["camera"] != "wide":
        step("Set filter", "set_ir", camera["ir_filter"])
    step("Set count", "set_count", camera["frame_count"], camera["camera"])
    step("Set binning", "set_binning", firmware_binning(camera["binning"]))
    _wait_seconds(5, "Waiting for capture camera settings to apply", step)
    _wait_seconds(workflow.get("wait_after_seconds", 10), "Waiting after setup", step)
    _wait_seconds(2, "Waiting before capture", step)
    _wait_for_capture_slot(step)
    ir_index = _ir_index(camera.get("ir_filter"))
    imported_plan = int(mosaic.get("grid_rows") or 0) >= 1 and int(mosaic.get("grid_columns") or 0) >= 1
    if not imported_plan and max(1, mosaic["rows"] * mosaic["columns"]) > 1:
        step("Set mosaic count", "set_mosaic_count", camera["frame_count"])
        step("Start mosaic", "mosaic", mosaic["horizontal_scale"], mosaic["vertical_scale"], mosaic["rotation_degrees"], ir_index)
        step("Waiting for mosaic", "wait_astro")
    elif camera["camera"] == "wide":
        step("Start wide capture", "wide_astro")
        step("Waiting for wide capture", "wait_wide")
    else:
        step("Start capture", "astro", ir_index)
        step("Waiting for capture", "wait_astro")
    return True


# Used for a manual STOP ALL when telemetry shows nothing running. stop_wide is
# deliberately absent: the Dwarf 3 never answers it unless a wide capture is
# active, which stalls the SDK for its full 150 s timeout.
_FALLBACK_STOPS = ("stop_astro", "stop_goto", "stop_calibrate", "stop_autofocus", "stop_polar")
_STOP_COMMAND_TIMEOUT = 6.0
# START_CAPTURE can be accepted before the firmware is actually stacking.
# A stop sent in that gap is a no-op, then stacking starts and keeps going.
_CAPTURE_STOP_GRACE_S = 8.0
_CAPTURE_STOP_WAIT_S = 35.0
_STOP_STEP_LABELS = {
    "stop_astro": "Stopping capture",
    "stop_wide": "Stopping wide capture",
    "stop_goto": "Stopping GOTO",
    "stop_calibrate": "Stopping calibration",
    "stop_autofocus": "Stopping autofocus",
    "stop_polar": "Stopping polar alignment",
    "stop_motors": "Stopping motors",
}
_PHASE_STOP_LABELS = {
    "astro": "Waiting for capture to stop",
    "wait_astro": "Waiting for capture to stop",
    "wait_astro_resume": "Waiting for capture to stop",
    "mosaic": "Waiting for mosaic to stop",
    "set_mosaic_count": "Waiting for mosaic to stop",
    "wide_astro": "Waiting for wide capture to stop",
    "wait_wide": "Waiting for wide capture to stop",
    "wait_wide_resume": "Waiting for wide capture to stop",
    "goto": "Waiting for GOTO to stop",
    "goto_solar": "Waiting for GOTO to stop",
    "calibrate": "Waiting for calibration to stop",
    "autofocus": "Waiting for autofocus to stop",
    "polar": "Waiting for polar alignment to stop",
}


def _stop_wait_label(phase: str | None) -> str:
    if not phase:
        return "Waiting for the current command to unwind"
    return _PHASE_STOP_LABELS.get(phase, f"Waiting for {phase.replace('_', ' ')} to stop")


def _stop_step_label(operation: str) -> str:
    return _STOP_STEP_LABELS.get(operation, operation.replace("_", " ").title())


def _activity_still_running(snapshot: dict[str, Any]) -> bool:
    if _capture_running(snapshot):
        return True
    if snapshot.get("goto_state") in _BUSY_ASTRO:
        return True
    if snapshot.get("calibration_state") in _BUSY_ASTRO:
        return True
    if snapshot.get("autofocus_state") == "running":
        return True
    if snapshot.get("eq_state") in _BUSY_ASTRO:
        return True
    return False


def _retry_stop_capture(snapshot: dict[str, Any]) -> None:
    wide = snapshot.get("capture_camera") == "wide"
    operation = "stop_wide" if wide else "stop_astro"
    label = _stop_step_label(operation)
    report_status("stop", label)
    log(f"Capture still running after stop; {label.lower()} again", "warning")
    try:
        _sdk_call_bounded(operation, _STOP_COMMAND_TIMEOUT)
    except Exception as exc:
        log(f"{label} retry skipped: {exc}", "debug")


def _wait_for_stop_idle() -> None:
    """Stay on the stop until stacking actually ends, and catch a late start.

    Firmware often accepts START_CAPTURE, then begins stacking a few seconds
    later. A stop sent in that window looks successful and the session is
    already unwound, so we have to watch and send stop again.
    """
    if _tap is None:
        return
    snapshot = _tap.snapshot()
    if not _activity_still_running(snapshot):
        report_status("stop", "Waiting to confirm the telescope stopped")
        grace = time.monotonic() + _CAPTURE_STOP_GRACE_S
        while time.monotonic() < grace:
            snapshot = _tap.snapshot()
            if _activity_still_running(snapshot):
                break
            time.sleep(0.3)
        else:
            return
    report_status("stop", "Waiting for the telescope to stop")
    deadline = time.monotonic() + _CAPTURE_STOP_WAIT_S
    retried = False
    while time.monotonic() < deadline:
        snapshot = _tap.snapshot()
        if not _activity_still_running(snapshot):
            return
        if _capture_running(snapshot) and not retried:
            retried = True
            _retry_stop_capture(snapshot)
        time.sleep(0.4)
    if _activity_still_running(_tap.snapshot()):
        log("Telescope is still busy after stop commands", "warning")


def _stop_targets() -> list[str]:
    """Pick the stop commands that match what the telescope is actually doing."""
    phase = _stop_phase or _session_phase
    snapshot = _tap.snapshot() if _tap is not None else {}
    capturing = _capture_running(snapshot)
    wide_capture = capturing and snapshot.get("capture_camera") == "wide"
    operations: list[str] = []
    if phase in ("astro", "wait_astro", "wait_astro_resume", "mosaic", "set_mosaic_count") or (capturing and not wide_capture):
        operations.append("stop_astro")
    if phase in ("wide_astro", "wait_wide", "wait_wide_resume") or wide_capture:
        operations.append("stop_wide")
    if phase in ("goto", "goto_solar") or snapshot.get("goto_state") in _BUSY_ASTRO:
        operations.append("stop_goto")
    if phase == "calibrate" or snapshot.get("calibration_state") in _BUSY_ASTRO:
        operations.append("stop_calibrate")
    if phase == "autofocus" or snapshot.get("autofocus_state") == "running":
        operations.append("stop_autofocus")
    if phase == "polar" or snapshot.get("eq_state") in _BUSY_ASTRO:
        operations.append("stop_polar")
    if not operations and phase is None:
        operations.extend(_FALLBACK_STOPS)
    operations.append("stop_motors")
    return operations


def _sdk_call_bounded(operation: str, seconds: float) -> Any:
    """Run one SDK command but wake it up if the device never answers."""
    timer = threading.Timer(
        seconds,
        lambda: _in_flight == operation and _interrupt_sdk_wait(f"{operation} timed out"),
    )
    timer.daemon = True
    timer.start()
    try:
        return sdk_call(operation)
    finally:
        timer.cancel()


def stop_all() -> bool:
    """Send the stop commands. Runs on the command thread after the interrupted step unwinds."""
    global _stop_phase
    _stop.set()
    operations = _stop_targets()
    _stop_phase = None
    if not _connected.is_set() or (_tap is not None and _tap.snapshot().get("power_off")):
        log("Stop skipped; telescope is not connected", "debug")
        report_status("stop", "Telescope is not connected")
        return True
    report_status("stop", "Sending stop commands")
    for operation in operations:
        label = _stop_step_label(operation)
        report_status("stop", label)
        log(f"{label}…")
        try:
            _sdk_call_bounded(operation, _STOP_COMMAND_TIMEOUT)
        except Exception as exc:
            log(f"{label} skipped: {exc}", "debug")
    _wait_for_stop_idle()
    report_status("stop", "Stop complete")
    if _connected.is_set():
        request_state_refresh()
    return True


_REFRESH_AFTER = {
    "lights_on", "lights_off", "indicator_on", "indicator_off", "go_live",
    "photo_mode", "astro_mode", "shooting_mode", "set_ir", "set_binning",
    "photo", "wide_photo", "set_wb", "set_wb_preset", "set_brightness",
    "set_contrast", "set_saturation", "set_hue", "set_sharpness",
}


def _ensure_astro_mode() -> Any:
    """Enter DSO mode (2) unless the telescope already reports it.

    Firmware mode 8 is Sun, not generic astro. The SDK helper also runs
    ENTER_CAMERA and SWITCH_SHOOTING_TECH. Skip the whole sequence when
    already in mode 2 — the Dwarf 3 otherwise waits out a 150 s timeout.
    """
    if _tap is not None and _tap.snapshot().get("shooting_mode") == _ASTRO_SHOOTING_MODE:
        log("Already in DSO astro mode", "debug")
        return True
    function = getattr(_api, "perform_enter_astro_mode", None) if _api is not None else None
    if function is None:
        return sdk_call("shooting_mode", _ASTRO_SHOOTING_MODE, _ASTRO_SHOOTING_TECH)
    return _invoke_sdk("astro_mode", function)


def _album_camera(name: str = "") -> str:
    choice = str(name or _device.get("camera") or "tele").strip().lower()
    return "WIDE" if choice == "wide" else "TELE"


def _album_model_matches() -> bool:
    """Raise if the telescope at this IP is a different model. True if confirmed."""
    expected = str(_device.get("model") or "")
    if not expected:
        return False
    try:
        result = _http_json(f"http://{_device_ip()}:8082/deviceInfo", {})
    except Exception:
        return False
    payload = result.get("data") if isinstance(result, dict) else None
    if not isinstance(payload, dict):
        payload = result if isinstance(result, dict) else {}
    name = str(payload.get("deviceName") or payload.get("device_name") or "")
    actual = device_name_model(name)
    if actual and actual != expected:
        raise RuntimeError(
            f"This telescope is a {actual}, not a {expected}. "
            "Select the matching profile or update Settings."
        )
    return bool(actual) and actual == expected


def _album_connect():
    from ftplib import FTP, error_perm

    ip = str(_device.get("ip_address") or "").strip()
    if not ip:
        raise RuntimeError("Telescope IP is not set")
    confirmed = _album_model_matches()
    ftp = FTP()
    ftp.connect(ip, timeout=12)
    ftp.login("Anonymous", "")
    ftp.set_pasv(True)
    model = str(_device.get("model") or "")
    prefixes = {
        "Dwarf II": ("DWARF_",),
        "Dwarf 3": ("DWARF3_",),
        "Dwarf Mini": ("DWARF_mini_", "DWARF3_") if confirmed else ("DWARF_mini_",),
    }.get(model, ("DWARF3_", "DWARF_mini_", "DWARF_"))
    for remote in ("/Normal_Photos", "/DWARF_II/Normal_Photos"):
        try:
            ftp.cwd(remote)
            return ftp, remote, prefixes
        except error_perm:
            continue
    ftp.close()
    raise RuntimeError("Could not open the telescope photo album over FTP")


def album_list(limit: int = 12, camera: str = "") -> dict[str, Any]:
    ftp, remote, prefixes = _album_connect()
    try:
        names = ftp.nlst()
    finally:
        try:
            ftp.close()
        except Exception:
            pass
    camera_name = _album_camera(camera)
    starts = tuple(f"{prefix}{camera_name}" for prefix in prefixes)
    photos = sorted(
        (name for name in names if name.endswith(".jpg") and name.startswith(starts)),
        reverse=True,
    )[: max(1, int(limit))]
    return {"camera": camera_name.lower(), "directory": remote, "files": photos}


def album_download(name: str = "", dest_dir: str = "", camera: str = "") -> dict[str, Any]:
    listing = album_list(1 if not name else 40, camera)
    files = listing.get("files") or []
    chosen = str(name or (files[0] if files else "")).strip()
    if not chosen:
        raise RuntimeError("No stills found on the telescope")
    if chosen not in files and name:
        listing = album_list(80, camera)
        files = listing.get("files") or []
        if chosen not in files:
            raise RuntimeError(f"{chosen} is not in the telescope album")
    folder = Path(dest_dir) if dest_dir else Path(tempfile.mkdtemp(prefix="astro-dwarf-album-"))
    folder.mkdir(parents=True, exist_ok=True)
    local = folder / chosen
    ftp, remote, _prefixes = _album_connect()
    try:
        with local.open("wb") as handle:
            ftp.retrbinary(f"RETR {chosen}", handle.write)
    finally:
        try:
            ftp.close()
        except Exception:
            pass
    log(f"Downloaded {chosen} from {remote}")
    return {"path": str(local), "file": chosen, "directory": remote, "camera": listing.get("camera")}


def _device_ip() -> str:
    ip = str(_device.get("ip_address") or "").strip()
    if not ip:
        raise RuntimeError("Telescope IP is not set")
    return ip


def _http_json(url: str, payload: dict[str, Any], timeout: float = 20) -> Any:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


def _http_download(url: str, dest: Path, timeout: float = 90) -> None:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, dest.open("wb") as handle:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


def _media_url(ip: str, path: str) -> str:
    return album_http_url(ip, path)


def _ftp_download_file(ip: str, remote_path: str, dest: Path) -> None:
    from ftplib import FTP

    path = album_http_path(remote_path)
    parts = [part for part in path.split("/") if part]
    if not parts:
        raise RuntimeError("No session file path to download")
    ftp = FTP()
    ftp.connect(ip, timeout=12)
    ftp.login("Anonymous", "")
    ftp.set_pasv(True)
    try:
        if len(parts) > 1:
            ftp.cwd("/" + "/".join(parts[:-1]))
        with dest.open("wb") as handle:
            ftp.retrbinary(f"RETR {parts[-1]}", handle.write)
    finally:
        try:
            ftp.close()
        except Exception:
            pass


def astro_sessions_list() -> dict[str, Any]:
    ip = _device_ip()
    _album_model_matches()
    result = _http_json(
        f"http://{ip}:8082/album/list/mediaInfos",
        {"mediaType": 6, "pageIndex": 0, "pageSize": 0},
    )
    if not isinstance(result, dict) or result.get("code") != 0:
        raise RuntimeError(f"Unexpected album response: {result}")
    sessions = result.get("data") or []
    if not isinstance(sessions, list):
        sessions = []
    model = str(_device.get("model") or "")
    if model:
        sessions = [
            entry for entry in sessions
            if isinstance(entry, dict) and album_path_matches_model(
                str(entry.get("filePath") or entry.get("thumbnailPath") or ""),
                model,
            )
        ]
    log(f"Listed {len(sessions)} astro sessions on {ip}")
    return {"ip": ip, "sessions": sessions}


def astro_session_download(file_path: str = "", dest_dir: str = "") -> dict[str, Any]:
    ip = _device_ip()
    remote = str(file_path or "").strip()
    if not remote:
        raise RuntimeError("No session file path to download")
    url = _media_url(ip, remote)
    folder = Path(dest_dir) if dest_dir else Path(tempfile.mkdtemp(prefix="astro-dwarf-album-"))
    folder.mkdir(parents=True, exist_ok=True)
    web_path = album_http_path(remote)
    parts = [part for part in Path(web_path).parts if part not in {"/", "\\"}]
    name = f"{parts[-2]}_{parts[-1]}" if len(parts) >= 2 else (parts[-1] if parts else "stacked.jpg")
    local = folder / name
    try:
        _http_download(url, local)
    except RuntimeError as exc:
        try:
            _ftp_download_file(ip, web_path, local)
        except Exception as ftp_exc:
            raise RuntimeError(f"{exc}; FTP fallback failed: {ftp_exc}") from ftp_exc
    if not local.exists() or local.stat().st_size <= 0:
        raise RuntimeError(f"Download produced an empty file from {url}")
    log(f"Downloaded {name} from {url}")
    return {"path": str(local), "file": name, "url": url, "file_path": remote}


def polar_position() -> bool:
    function = getattr(_api, "motor_action", None) if _api is not None else None
    if function is None:
        raise RuntimeError("motor_action is not available in this SDK")
    model = str(_device.get("model") or "")
    steps = (5, 6, 9, 7) if model in {"Dwarf 3", "Dwarf Mini"} else (5, 6, 2, 3)
    for action in steps:
        if function(action) is False:
            return False
    return True


def dispatch(message: dict[str, Any]) -> Any:
    command = message["command"]
    if command == "configure":
        return configure(message["device"])
    if command == "connect":
        return connect()
    if command == "run_session":
        return run_session(message["session"])
    if command == "stop_all":
        return stop_all()
    if command == "telemetry":
        return _tap.snapshot() if _tap else {}
    if command == "device_state":
        if not _connected.is_set() and message.get("internal"):
            return False
        result = sdk_call("device_state")
        if _tap is not None:
            _tap.flush()
        return serializable_state(result)
    if command == "stack_status":
        return serializable_state(sdk_call(command))
    if command == "album_list":
        args = list(message.get("args") or [])
        limit = int(args[0]) if args else 12
        camera = str(args[1]) if len(args) > 1 else ""
        return album_list(limit, camera)
    if command == "album_download":
        args = list(message.get("args") or [])
        return album_download(
            str(args[0] if args else ""),
            str(args[1] if len(args) > 1 else ""),
            str(args[2] if len(args) > 2 else ""),
        )
    if command == "astro_sessions_list":
        return astro_sessions_list()
    if command == "astro_session_download":
        args = list(message.get("args") or [])
        return astro_session_download(
            str(args[0] if args else ""),
            str(args[1] if len(args) > 1 else ""),
        )
    if command == "polar_position":
        return polar_position()
    if command == "read_camera":
        args = list(message.get("args") or [])
        mode_id = int(args[0]) if args else 1
        return serializable_state(sdk_call("read_camera", mode_id))
    if command == "photo" and str(_device.get("camera") or "") == "wide":
        command = "wide_photo"
    if command in {"disconnect", "reboot", "power_down"}:
        _mark_disconnected()
        return sdk_call(command)
    if command in {"calibrate", "autofocus", "infinity", "polar"}:
        if _ensure_astro_mode() is False:
            return False
    if command == "astro_mode":
        result = _ensure_astro_mode()
        if result is not False:
            request_state_refresh()
        return result
    if command == "autofocus":
        # Astro AF mode 0. Mode 1 is infinity (the INFINITY pad).
        result = sdk_call("autofocus", False)
    elif command == "infinity":
        result = sdk_call("autofocus", True)
    else:
        capture_techniques = {
            "photo": 1,
            "wide_photo": 1,
            "burst_start": 3,
            "record_start": 4,
            "timelapse_start": 5,
        }
        if command in capture_techniques:
            if sdk_call("shooting_mode", 1, capture_techniques[command]) is False:
                return False
        result = sdk_call(command, *message.get("args", []))
    if command in _REFRESH_AFTER and result is not False:
        request_state_refresh()
    return result


def execute(message: dict[str, Any]) -> None:
    request_id = message.get("id")
    internal = bool(message.get("internal"))
    try:
        result = dispatch(message)
        if not internal:
            emit({"event": "response", "id": request_id, "ok": True, "result": result})
    except Exception as exc:
        if internal:
            log(f"Background {message.get('command')} failed: {exc}", "debug")
            return
        # Step failures and stops are expected outcomes; only dump real crashes.
        if not isinstance(exc, (RuntimeError, InterruptedError, NotImplementedError, TimeoutError)):
            traceback.print_exc(file=sys.stderr)
        emit({"event": "response", "id": request_id, "ok": False, "error": str(exc)})


def enqueue_command(message: dict[str, Any], priority: int = _PRIORITY_NORMAL) -> None:
    """Queue a command; keep only the newest joystick vector before a move or stop."""
    command = message.get("command")
    superseded: list[dict[str, Any]] = []
    if command in ("joystick", "stop_motors"):
        with _commands.mutex:
            retained = []
            for item in _commands.queue:
                if item[2].get("command") == "joystick":
                    superseded.append(item[2])
                else:
                    retained.append(item)
            _commands.queue.clear()
            _commands.queue.extend(retained)
            heapq.heapify(_commands.queue)
    for queued in superseded:
        emit({
            "event": "response",
            "id": queued.get("id"),
            "ok": True,
            "result": "superseded",
        })
    _put_command(message, priority)


_URGENT_COMMANDS = {"stop_all", "disconnect", "reboot", "power_down"}


def main() -> None:
    def command_loop() -> None:
        while True:
            _priority, _sequence, message = _commands.get()
            execute(message)

    threading.Thread(target=command_loop, daemon=True).start()
    try:
        for raw in sys.stdin:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                log(f"Invalid worker message: {raw!r}", "error")
                continue
            command = message.get("command")
            if command in _URGENT_COMMANDS:
                # The SDK is not thread-safe, so stop/disconnect never run alongside
                # another SDK call. Instead they wake the blocked call (which then
                # fails fast) and jump ahead of everything else in the queue.
                if command == "stop_all" or _session_active.is_set() or _in_flight is not None:
                    request_stop("Session stopped" if command == "stop_all" else "Telescope disconnected")
                enqueue_command(message, _PRIORITY_URGENT)
            else:
                enqueue_command(message)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        os._exit(0)


if __name__ == "__main__":
    main()
