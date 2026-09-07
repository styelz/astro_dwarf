"""Isolated telescope SDK worker.

One process is launched per physical telescope. JSON messages use stdout;
all SDK output and tracebacks use stderr so the Qt log panel can display them.
"""
from __future__ import annotations

import contextlib
import asyncio
import html
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

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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


def send_without_response(message: Any, command: int, module_id: int) -> bool:
    """Send commands whose V3 firmware does not return a request response."""
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
                f"BLE_PSD = {device.get('ble_password') or 'DWARF_12345678'}",
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
    if operation in ("joystick", "stop_motors"):
        from dwarf_python_api.proto import motor_control_pb2

        if operation == "joystick":
            message = motor_control_pb2.ReqMotorServiceJoystick()
            message.vector_angle = float(args[0])
            message.vector_length = float(args[1])
            return send_without_response(message, 14006, 6)
        return send_without_response(motor_control_pb2.ReqMotorServiceJoystickStop(), 14008, 6)
    if operation == "manual_focus":
        from dwarf_python_api.proto import focus_pb2

        message = focus_pb2.ReqManualSingleStepFocus()
        message.direction = int(args[0])
        return send_without_response(message, 15001, 8)
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
        if operation in ("calibrate", "stop_calibrate", "polar", "stop_polar"):
            from dwarf_python_api.proto import astro_pb2

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
    label = operation.replace("_", " ").title()
    log(f"{label}…", "sdk")
    with contextlib.redirect_stdout(sys.stderr):
        result = function(*args)
    log(f"{label}: {result}", "sdk")
    return result


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


def _safe_disconnect() -> None:
    try:
        sdk_call("disconnect")
    except Exception:
        pass


def _handshake() -> dict[str, Any] | None:
    if sdk_call("time") is False:
        return None
    telemetry: dict[str, Any] = {}
    for operation in ("host_master", "device_state", "location"):
        try:
            result = sdk_call(operation)
            if operation == "device_state":
                normalized = serializable_state(result)
                telemetry = normalized if isinstance(normalized, dict) else {"value": normalized}
        except NotImplementedError as exc:
            log(str(exc), "warning")
    return telemetry


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
    if camera["camera"] != "wide":
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
    if command in {"device_state", "stack_status"}:
        return serializable_state(sdk_call(command))
    if command in {"calibrate", "autofocus", "infinity", "polar"}:
        if sdk_call("astro_mode") is False:
            return False
    if command == "infinity":
        return sdk_call("autofocus", True)
    capture_techniques = {
        "burst_start": 3,
        "record_start": 4,
        "timelapse_start": 5,
    }
    if command in capture_techniques:
        if sdk_call("shooting_mode", 1, capture_techniques[command]) is False:
            return False
    return sdk_call(command, *message.get("args", []))


def execute(message: dict[str, Any]) -> None:
    request_id = message.get("id")
    try:
        emit({"event": "response", "id": request_id, "ok": True, "result": dispatch(message)})
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        emit({"event": "response", "id": request_id, "ok": False, "error": str(exc)})


def enqueue_command(message: dict[str, Any]) -> None:
    """Keep only the newest queued joystick vector before a move or stop."""
    command = message.get("command")
    superseded: list[dict[str, Any]] = []
    if command in ("joystick", "stop_motors"):
        with _commands.mutex:
            retained = []
            for queued in _commands.queue:
                if queued.get("command") == "joystick":
                    superseded.append(queued)
                else:
                    retained.append(queued)
            _commands.queue.clear()
            _commands.queue.extend(retained)
    for queued in superseded:
        emit({
            "event": "response",
            "id": queued.get("id"),
            "ok": True,
            "result": "superseded",
        })
    _commands.put(message)


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
            enqueue_command(message)


if __name__ == "__main__":
    main()
