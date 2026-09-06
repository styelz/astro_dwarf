"""Isolated telescope SDK worker.

One process is launched per physical telescope. JSON messages use stdout;
all SDK output and tracebacks use stderr so the Qt log panel can display them.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import threading
import traceback
import queue
from pathlib import Path
from typing import Any

_write_lock = threading.Lock()
_api = None
_device: dict[str, Any] = {}
_stop = threading.Event()
_commands: queue.Queue[dict[str, Any]] = queue.Queue()


def emit(payload: dict[str, Any]) -> None:
    with _write_lock:
        sys.__stdout__.write(json.dumps(payload, default=str) + "\n")
        sys.__stdout__.flush()


def log(message: str, level: str = "info") -> None:
    emit({"event": "log", "level": level, "message": message})


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
    "stop_astro": "perform_stopAstroPhoto",
    "wide_astro": "perform_takeAstroWidePhoto",
    "wait_wide": "perform_waitEndAstroWidePhoto",
    "stop_wide": "perform_stopAstroWidePhoto",
    "mosaic": "perform_start_mosaic_v3",
    "stack_status": "perform_read_astro_stacking_status_v3",
    "burst_start": "perform_start_burst_v3",
    "burst_stop": "perform_stop_burst_v3",
    "record_start": "perform_start_record_v3",
    "record_stop": "perform_stop_record_v3",
    "timelapse_start": "perform_start_timelapse_v3",
    "timelapse_stop": "perform_stop_timelapse_v3",
}


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
            ]
        ),
        encoding="utf-8",
    )
    os.chdir(folder)
    with contextlib.redirect_stdout(sys.stderr):
        from dwarf_python_api.lib import dwarf_utils

        _api = dwarf_utils
    log(f"Worker ready for {device.get('name')} at {device.get('ip_address')}")
    return True


def sdk_call(operation: str, *args: Any) -> Any:
    if _api is None:
        raise RuntimeError("Telescope worker is not configured")
    if operation == "manual_focus":
        from dwarf_python_api.proto import focus_pb2

        message = focus_pb2.ReqManualSingleStepFocus()
        message.direction = int(args[0])
        return _api.connect_socket(message, 15001, 0, 8)
    function_name = FUNCTIONS.get(operation)
    function = getattr(_api, function_name, None) if function_name else None
    if function is None:
        raise NotImplementedError(f"Installed SDK does not provide '{operation}'")
    log(f"{operation.replace('_', ' ').title()}…")
    with contextlib.redirect_stdout(sys.stderr):
        result = function(*args)
    log(f"{operation.replace('_', ' ').title()}: {result}")
    return result


def connect() -> bool:
    if sdk_call("time") is False:
        return False
    for operation in ("host_master", "device_state", "location"):
        try:
            sdk_call(operation)
        except NotImplementedError as exc:
            log(str(exc), "warning")
    return True


def run_session(session: dict[str, Any]) -> bool:
    _stop.clear()

    def step(name: str, operation: str | None = None, *args: Any) -> None:
        if _stop.is_set():
            raise InterruptedError("Session stopped")
        emit({"event": "progress", "session_id": session["id"], "step": name})
        if operation and sdk_call(operation, *args) is False:
            raise RuntimeError(f"{name} failed")

    target = session["target"]
    camera = session["camera"]
    workflow = session["workflow"]
    mosaic = session["mosaic"]
    model_id = {"Dwarf II": "2", "Dwarf 3": "3", "Dwarf Mini": "5"}.get(_device.get("model"), "3")

    if not connect():
        raise RuntimeError("Could not connect to telescope")
    step("Closing previous capture", "go_live")
    if target.get("kind") == "solar":
        solar_name = (target.get("solar_name") or target["name"]).lower()
        step("Entering solar mode", "shooting_mode", 8 if solar_name == "sun" else 9 if solar_name == "moon" else 10, 2)
    else:
        step("Entering astro mode", "astro_mode")
    if workflow.get("polar_align"):
        step("Polar alignment", "polar")
    if workflow.get("calibrate"):
        step("Calibration", "calibrate")
    if workflow.get("autofocus"):
        step("Auto focus", "autofocus", False)
    elif workflow.get("infinite_focus"):
        step("Infinity focus", "autofocus", True)
    if workflow.get("goto") and target.get("ra_hours") is not None:
        step("GOTO target", "goto", target["ra_hours"], target["dec_degrees"], target["name"])
    elif workflow.get("goto") and target.get("kind") == "solar":
        ids = {"mercury": 1, "venus": 2, "mars": 3, "jupiter": 4, "saturn": 5, "uranus": 6, "neptune": 7, "moon": 8, "sun": 9}
        name = (target.get("solar_name") or target["name"]).lower()
        step("GOTO solar target", "goto_solar", ids[name], name.title())
    step("Set exposure", "set_exposure", str(camera["exposure_seconds"]), model_id, camera["camera"])
    step("Set gain", "set_gain", camera["gain"], camera["camera"])
    step("Set filter", "set_ir", camera["ir_filter"])
    step("Set count", "set_count", camera["frame_count"], camera["camera"])
    step("Set binning", "set_binning", camera["binning"])
    if max(1, mosaic["rows"] * mosaic["columns"]) > 1:
        step("Set mosaic count", "set_mosaic_count", camera["frame_count"])
        step("Start mosaic", "mosaic", mosaic["horizontal_scale"], mosaic["vertical_scale"], mosaic["rotation_degrees"])
        step("Waiting for mosaic", "wait_astro")
    elif camera["camera"] == "wide":
        step("Start wide capture", "wide_astro")
        step("Waiting for wide capture", "wait_wide")
    else:
        step("Start capture", "astro")
        step("Waiting for capture", "wait_astro")
    return True


def stop_all() -> bool:
    _stop.set()
    for operation in ("stop_astro", "stop_wide", "stop_goto", "stop_calibrate", "stop_autofocus", "stop_motors"):
        try:
            sdk_call(operation)
        except Exception:
            pass
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
    if command == "infinity":
        return sdk_call("autofocus", True)
    return sdk_call(command, *message.get("args", []))


def execute(message: dict[str, Any]) -> None:
    request_id = message.get("id")
    try:
        emit({"event": "response", "id": request_id, "ok": True, "result": dispatch(message)})
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        emit({"event": "response", "id": request_id, "ok": False, "error": str(exc)})


def main() -> None:
    def command_loop() -> None:
        while True:
            execute(_commands.get())

    threading.Thread(target=command_loop, daemon=True).start()
    for raw in sys.stdin:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            log(f"Invalid worker message: {raw!r}", "error")
            continue
        # Preserve SDK command order. Stop is the sole intentional concurrent
        # operation so it can interrupt a blocking capture wait.
        if message.get("command") == "stop_all":
            threading.Thread(target=execute, args=(message,), daemon=True).start()
        else:
            _commands.put(message)


if __name__ == "__main__":
    main()
