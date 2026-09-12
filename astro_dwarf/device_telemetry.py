"""Telemetry and log capture for the isolated telescope worker.

The Dwarf SDK decodes most websocket notifications but only keeps a few of
them in its client cache and only returns response codes to callers. This
module taps the raw ``WsPacket`` stream (without editing the SDK), decodes
the hardware notifications the HUD cares about, and turns the SDK logger
into structured, level-tagged events.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, Callable

# Motor / notification command ids (dwarf_python_api/proto/protocol.proto).
CMD_STEP_MOTOR_GET_POSITION = 14011
# Steppers refuse absolute position reads/moves until they have been homed.
CODE_STEP_MOTOR_NEED_RESET = -14520
CMD_NOTIFY_TELE_WIDE_PICTURE_MATCHING = 15200
CMD_NOTIFY_ELE = 15201
CMD_NOTIFY_CHARGE = 15202
CMD_NOTIFY_SDCARD_INFO = 15203
CMD_NOTIFY_TELE_RECORD_TIME = 15204
CMD_NOTIFY_STATE_CAPTURE_RAW_DARK = 15206
CMD_NOTIFY_PROGRASS_CAPTURE_RAW_DARK = 15207
CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING = 15208
CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING = 15209
CMD_NOTIFY_STATE_ASTRO_CALIBRATION = 15210
CMD_NOTIFY_STATE_ASTRO_GOTO = 15211
CMD_NOTIFY_STATE_ASTRO_TRACKING = 15212
CMD_NOTIFY_RGB_STATE = 15221
CMD_NOTIFY_POWER_IND_STATE = 15222
CMD_NOTIFY_WS_HOST_SLAVE_MODE = 15223
CMD_NOTIFY_CPU_MODE = 15227
CMD_NOTIFY_POWER_OFF = 15229
CMD_NOTIFY_STREAM_TYPE = 15234
CMD_NOTIFY_WIDE_RECORD_TIME = 15235
CMD_NOTIFY_STATE_WIDE_CAPTURE_RAW_LIVE_STACKING = 15236
CMD_NOTIFY_PROGRASS_WIDE_CAPTURE_RAW_LIVE_STACKING = 15237
CMD_NOTIFY_EQ_SOLVING_STATE = 15239
CMD_NOTIFY_TELE_LONG_EXP_PROGRESS = 15241
CMD_NOTIFY_TEMPERATURE = 15243
CMD_NOTIFY_FOCUS_POSITION = 15257
CMD_NOTIFY_BODY_STATUS = 15262
CMD_NOTIFY_PROGRESS_CAPTURE_MOSAIC = 15263
CMD_NOTIFY_GENERAL_INT_PARAM = 15264
CMD_NOTIFY_SWITCH_SHOOTING_MODE = 15267
CMD_NOTIFY_RECORD_STATE = 15275
CMD_NOTIFY_CMOS_TEMPERATURE = 15292
CMD_GLOBAL_TASK_GET_DEVICE_STATE_INFO = 16405

TYPE_NOTIFICATION = 2
_RESPONSE_TYPES = (1, 3)  # WsPacket.type: 0 request, 1 reply, 2 notification, 3 response

CMD_ASTRO_START_CALIBRATION = 11000
CMD_ASTRO_START_GOTO_DSO = 11002
CMD_ASTRO_START_GOTO_SOLAR_SYSTEM = 11003
CMD_ASTRO_START_EQ_SOLVING = 11018
CMD_FOCUS_START_ASTRO_AUTO_FOCUS = 15004
CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING = 11005
CMD_ASTRO_START_WIDE_CAPTURE_LIVE_STACKING = 11016
CMD_ASTRO_START_TELE_MOSAIC = 11031
CMD_ASTRO_CONTINUE_SHOOTING = 11050
# Commands whose reply code the worker needs: long-running operations whose
# reply only arrives once the operation ends, and capture starts whose reply
# carries firmware warnings (missing darks, engine busy) the SDK only logs.
_TRACKED_RESPONSES = {
    CMD_ASTRO_START_CALIBRATION,
    CMD_ASTRO_START_GOTO_DSO,
    CMD_ASTRO_START_GOTO_SOLAR_SYSTEM,
    CMD_ASTRO_START_EQ_SOLVING,
    CMD_FOCUS_START_ASTRO_AUTO_FOCUS,
    CMD_ASTRO_START_CAPTURE_RAW_LIVE_STACKING,
    CMD_ASTRO_START_WIDE_CAPTURE_LIVE_STACKING,
    CMD_ASTRO_START_TELE_MOSAIC,
    CMD_ASTRO_CONTINUE_SHOOTING,
}

OPERATION_STATES = {0: "idle", 1: "running", 2: "stopping", 3: "stopped"}
ASTRO_STATES = {0: "idle", 1: "running", 2: "stopping", 3: "stopped", 4: "solving"}
CHARGING_STATES = {0: "discharging", 1: "charging", 2: "full"}
STREAM_TYPES = {0: "OFF", 1: "RTSP", 2: "JPEG"}
BODY_STATUS = {1: "EQ", 2: "AZ"}
# BatteryInfo.percentage is the real SoC. CMD_NOTIFY_ELE and the SDK cache
# (BatteryLevelDwarf) are the same remaining-% notify; the SDK only stores it
# on 10% jumps, so a 22% BatteryInfo and a latched 20% cache fight and the
# HUD flickers across the low-battery line.
_BATTERY_SDK_STEP = 10
_BATTERY_NOTIFY_JITTER = 3
_BATTERY_SOURCE_RANK = {"sdk": 0, "notify": 1, "state": 2}

_PICTURE_MATCHING_W = 1920
_PICTURE_MATCHING_H = 1080


def normalize_picture_matching(x: int, y: int, width: int, height: int) -> dict[str, float]:
    """Normalize a tele-in-wide rectangle without a position-dependent span."""
    if width <= 0 or height <= 0:
        return {}
    # Some firmware reports the same rectangle in the 3840x2160 still frame.
    # Its dimensions are roughly twice the live-frame rectangle, even when a
    # left/top rectangle does not cross the 1920x1080 boundary.
    high_resolution = (
        x + width > _PICTURE_MATCHING_W
        or y + height > _PICTURE_MATCHING_H
        or width > _PICTURE_MATCHING_W / 10
        or height > _PICTURE_MATCHING_H / 10
    )
    scale = 2 if high_resolution else 1
    span_w = _PICTURE_MATCHING_W * scale
    span_h = _PICTURE_MATCHING_H * scale
    nx = max(0.0, min(1.0, (x + width / 2.0) / span_w))
    ny = max(0.0, min(1.0, (y + height / 2.0) / span_h))
    return {
        "tele_match_cx": nx * (_PICTURE_MATCHING_W - 1),
        "tele_match_cy": ny * (_PICTURE_MATCHING_H - 1),
        "tele_match_nx": nx,
        "tele_match_ny": ny,
        "tele_match_nw": min(1.0, width / span_w),
        "tele_match_nh": min(1.0, height / span_h),
    }

PARAM_ID_PHOTO_TELE_EXPOSURE = 0x0101000000000001
PARAM_ID_PHOTO_TELE_GAIN = 0x0101000000000002
PARAM_ID_ASTRO_EXPOSURE = 0x0201000000000001
PARAM_ID_ASTRO_GAIN = 0x0201000000000002
PARAM_ID_PHOTO_WIDE_EXPOSURE = 0x0101100000000001
PARAM_ID_PHOTO_WIDE_GAIN = 0x0101100000000002
PARAM_ID_ASTRO_WIDE_EXPOSURE = 0x0201100000000001
PARAM_ID_ASTRO_WIDE_GAIN = 0x0201100000000002

_EXPOSURE_PARAMS = {PARAM_ID_PHOTO_TELE_EXPOSURE, PARAM_ID_ASTRO_EXPOSURE}
_GAIN_PARAMS = {PARAM_ID_PHOTO_TELE_GAIN, PARAM_ID_ASTRO_GAIN}
_WIDE_EXPOSURE_PARAMS = {PARAM_ID_PHOTO_WIDE_EXPOSURE, PARAM_ID_ASTRO_WIDE_EXPOSURE}
_WIDE_GAIN_PARAMS = {PARAM_ID_PHOTO_WIDE_GAIN, PARAM_ID_ASTRO_WIDE_GAIN}


class _ModuleProxy:
    """Delegate to a real module while overriding a few attribute names."""

    def __init__(self, real: Any, overrides: dict[str, Any]):
        object.__setattr__(self, "_real", real)
        object.__setattr__(self, "_overrides", overrides)

    def __getattr__(self, name: str) -> Any:
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        return getattr(object.__getattribute__(self, "_real"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_real"), name, value)


class _MessageProxy:
    """Wrap a protobuf message and report every successful ``ParseFromString``."""

    def __init__(self, message: Any, callback: Callable[[Any], None]):
        object.__setattr__(self, "_message", message)
        object.__setattr__(self, "_callback", callback)

    def ParseFromString(self, data: bytes) -> Any:  # noqa: N802 - protobuf API
        message = object.__getattribute__(self, "_message")
        result = message.ParseFromString(data)
        try:
            object.__getattribute__(self, "_callback")(message)
        except Exception:
            pass
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_message"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_message"), name, value)


def _protobuf_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, offset
        shift += 7
        if shift >= 64:
            break
    return value, offset


def _first_enum_field(data: bytes) -> int | None:
    """Read protobuf field 1 when it is a varint (enum/int)."""
    if not data:
        return None
    try:
        key, offset = _protobuf_varint(data, 0)
        if (key >> 3) != 1 or (key & 7) != 0:
            return None
        value, _ = _protobuf_varint(data, offset)
        return value
    except Exception:
        return None


def _exposure_name(index: Any, model_id: str) -> str:
    try:
        from dwarf_python_api.lib.data_utils import get_exposure_name_by_index

        name = get_exposure_name_by_index(int(index), model_id)
        if name:
            return str(name)
    except Exception:
        pass
    return str(index)


def _stacking_progress_changes(message: Any, mosaic: bool = False) -> dict[str, Any]:
    """Honor firmware ``update_type`` so a stacked-only packet cannot zero current.

    The SDK cache does the same: 0 = current, 1 = stacked, 2 = both.
    Proto3 defaults missing ints to 0, which is what made the HUD flash
    the real count then jump back to 0/N after a reconnect.
    """
    try:
        update_type = int(getattr(message, "update_type", 2))
    except (TypeError, ValueError):
        update_type = 2
    if update_type not in (0, 1, 2):
        update_type = 2
    changes: dict[str, Any] = {
        "capture_total": int(message.total_count),
        "capture_target": str(message.target_name or ""),
        "capture_active": True,
    }
    if mosaic:
        changes["mosaic_active"] = True
    try:
        current = int(message.current_count)
    except (TypeError, ValueError):
        current = 0
    try:
        stacked = int(message.stacked_count)
    except (TypeError, ValueError):
        stacked = 0
    # update_type=0 is also the proto3 default, so a full progress packet
    # that omits the field would otherwise never publish stacked_count.
    # A positive count is always a real value, never a missing-field zero.
    if update_type in (0, 2) or current:
        changes["capture_current"] = current
    if update_type in (1, 2) or stacked:
        changes["capture_stacked"] = stacked
    if not mosaic:
        try:
            if message.HasField("shooting_time"):
                changes["capture_shooting_s"] = int(message.shooting_time)
        except Exception:
            pass
        try:
            if message.HasField("stacked_time"):
                changes["capture_stacked_s"] = int(message.stacked_time)
        except Exception:
            pass
    return changes


class TelemetryTap:
    """Collects device telemetry from raw packets, the SDK cache and state dumps."""

    def __init__(self, emit: Callable[[dict[str, Any]], None], model_id: str = "3", flush_interval: float = 0.25):
        self._emit = emit
        self._model_id = model_id
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {}
        self._pending: dict[str, Any] = {}
        self._last_flush = 0.0
        self._notify = None
        self._base = None
        self._installed = False
        self._status_signature: dict[str, Any] = {}
        self._astro = None
        self._responses: dict[int, tuple[int, float]] = {}
        # After a new session starts, leftover stacking packets / SDK cache
        # counts from the previous run must not keep the HUD on e.g. 104/120.
        self._hold_stale_capture = False
        self._accept_sdk_capture_counts = True
        self._stale_capture_peak = 0
        self._battery_source = ""

    # ------------------------------------------------------------------ setup
    def install(self, websockets_utils: Any) -> bool:
        """Hook ``base__pb2.WsPacket`` and ``task_center.ResGetDeviceStateInfo``."""
        if self._installed:
            return True
        try:
            import dwarf_python_api.proto.base_pb2 as base_pb2
            import dwarf_python_api.proto.notify_pb2 as notify_pb2
        except Exception:
            return False
        self._base = base_pb2
        self._notify = notify_pb2
        try:
            import dwarf_python_api.proto.astro_pb2 as astro_pb2

            self._astro = astro_pb2
        except Exception:
            self._astro = None
        try:
            real_base = websockets_utils.base__pb2

            def make_packet(*args: Any, **kwargs: Any) -> Any:
                return _MessageProxy(real_base.WsPacket(*args, **kwargs), self._on_ws_packet)

            websockets_utils.base__pb2 = _ModuleProxy(real_base, {"WsPacket": make_packet})
        except Exception:
            return False
        try:
            real_task = websockets_utils.task_center

            def make_state(*args: Any, **kwargs: Any) -> Any:
                return _MessageProxy(real_task.ResGetDeviceStateInfo(*args, **kwargs), self.on_device_state)

            websockets_utils.task_center = _ModuleProxy(real_task, {"ResGetDeviceStateInfo": make_state})
        except Exception:
            pass
        self._installed = True
        return True

    # ------------------------------------------------------------------ state
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            merged = dict(self._state)
            merged.update(self._pending)
            return merged

    def _should_apply_battery(self, percent: int, source: str) -> bool:
        """Keep BatteryInfo.percentage over the coarse ELE / SDK cache reading."""
        with self._lock:
            raw = self._pending.get("battery_percent", self._state.get("battery_percent"))
            held = self._battery_source
            incoming = _BATTERY_SOURCE_RANK.get(source, 0)
            held_rank = _BATTERY_SOURCE_RANK.get(held, 0)
            if raw is None:
                self._battery_source = source
                return True
            try:
                current = int(raw)
            except (TypeError, ValueError):
                self._battery_source = source
                return True
            if current == percent:
                if incoming >= held_rank:
                    self._battery_source = source
                return False
            if incoming > held_rank or source == "state":
                self._battery_source = source
                return True
            delta = abs(current - percent)
            # SDK cache only moves on 10% jumps — never let it clobber 22% with 20%.
            if source == "sdk" and delta < _BATTERY_SDK_STEP:
                return False
            # Live ELE can update sooner than the next state dump; ignore 1–2% chatter.
            if percent < current and delta < _BATTERY_NOTIFY_JITTER:
                return False
            self._battery_source = source
            return True

    def reset(self) -> None:
        with self._lock:
            self._state.clear()
            self._pending.clear()
            self._status_signature.clear()
            self._responses.clear()
            self._hold_stale_capture = False
            self._accept_sdk_capture_counts = True
            self._stale_capture_peak = 0
            self._battery_source = ""

    def _capture_count_peak(self, data: dict[str, Any] | None = None) -> int:
        source = data if data is not None else self._state
        peak = 0
        for key in ("capture_current", "capture_stacked"):
            try:
                peak = max(peak, int(source.get(key) or 0))
            except (TypeError, ValueError):
                continue
        return peak

    def reset_capture_progress(self, total: int | None = None, target: str = "") -> None:
        """Zero leftover stacking counts so a new session does not show the last run."""
        with self._lock:
            peak = max(self._stale_capture_peak, self._capture_count_peak(), self._capture_count_peak(self._pending))
            self._stale_capture_peak = peak
            self._hold_stale_capture = True
            self._accept_sdk_capture_counts = False
        changes: dict[str, Any] = {
            "capture_current": 0,
            "capture_stacked": 0,
            "capture_active": False,
            "capture_state": "idle",
            "mosaic_active": False,
            "capture_target": target or "",
            "capture_shooting_s": 0,
            "capture_stacked_s": 0,
        }
        if total is not None:
            try:
                changes["capture_total"] = int(total)
            except (TypeError, ValueError):
                pass
        self.update(changes, force=True)

    def release_capture_progress(self) -> None:
        """Accept stacking notifications for the capture that is about to start."""
        with self._lock:
            self._hold_stale_capture = False

    def _fresh_stacking_progress(self, message: Any, mosaic: bool = False) -> dict[str, Any]:
        with self._lock:
            hold = self._hold_stale_capture
            stale_peak = self._stale_capture_peak
        if hold:
            return {}
        changes = _stacking_progress_changes(message, mosaic=mosaic)
        new_count = self._capture_count_peak(changes)
        if stale_peak > 1 and new_count >= stale_peak:
            # Leftover packets from the previous stack; wait for a fresh 0/1.
            return {}
        with self._lock:
            self._stale_capture_peak = 0
            self._accept_sdk_capture_counts = True
        return changes

    def response_after(self, cmd: int, since: float) -> int | None:
        """Return the reply code for ``cmd`` received after monotonic time ``since``."""
        with self._lock:
            item = self._responses.get(cmd)
        if item is None or item[1] < since:
            return None
        return item[0]

    def update(self, changes: dict[str, Any], force: bool = False) -> None:
        if not changes:
            return
        now = time.monotonic()
        with self._lock:
            for key, value in changes.items():
                if value is None:
                    continue
                if self._state.get(key) != value or key not in self._state:
                    self._pending[key] = value
            if not self._pending:
                return
            due = force or now - self._last_flush >= self._flush_interval
            if not due:
                return
            payload = self._pending
            self._pending = {}
            self._state.update(payload)
            self._last_flush = now
        self._emit({"event": "telemetry", "data": payload})

    def flush(self) -> None:
        with self._lock:
            if not self._pending:
                return
            payload = self._pending
            self._pending = {}
            self._state.update(payload)
            self._last_flush = time.monotonic()
        self._emit({"event": "telemetry", "data": payload})

    # -------------------------------------------------------------- decoding
    def _on_ws_packet(self, packet: Any) -> None:
        try:
            cmd = int(packet.cmd)
            kind = int(packet.type)
            data = bytes(packet.data)
        except Exception:
            return
        self.on_packet(cmd, kind, data)

    def _parse(self, factory_name: str, data: bytes) -> Any:
        factory = getattr(self._notify, factory_name, None) if self._notify else None
        if factory is None:
            return None
        message = factory()
        message.ParseFromString(data)
        return message

    def _decode_named_state(
        self,
        factory_name: str,
        data: bytes,
        state_key: str,
        target_key: str,
        states: dict[int, str],
    ) -> dict[str, Any]:
        """Decode goto/tracking notifications even when target_name is not valid UTF-8."""
        try:
            message = self._parse(factory_name, data)
            target = str(message.target_name or "")
            return {
                state_key: states.get(int(message.state), str(message.state)),
                target_key: target,
            }
        except Exception:
            state = _first_enum_field(data)
            if state is None:
                return {}
            return {state_key: states.get(state, str(state))}

    def on_packet(self, cmd: int, kind: int, data: bytes) -> None:
        """Decode one incoming packet into telemetry changes (never raises)."""
        if kind in _RESPONSE_TYPES and cmd in _TRACKED_RESPONSES:
            self._record_response(cmd, data)
        try:
            changes = self._decode(cmd, kind, data)
        except Exception:
            return
        if changes:
            self.update(changes, force=cmd in (
                CMD_NOTIFY_STATE_ASTRO_GOTO,
                CMD_NOTIFY_STATE_ASTRO_CALIBRATION,
                CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING,
                CMD_NOTIFY_STATE_WIDE_CAPTURE_RAW_LIVE_STACKING,
                CMD_NOTIFY_POWER_OFF,
            ))

    def _record_response(self, cmd: int, data: bytes) -> None:
        try:
            if cmd == CMD_ASTRO_START_EQ_SOLVING and self._astro is not None:
                message = self._astro.ResStartEqSolving()
            elif self._base is not None:
                message = self._base.ComResponse()
            else:
                return
            message.ParseFromString(data)
            code = int(message.code)
        except Exception:
            return
        with self._lock:
            self._responses[cmd] = (code, time.monotonic())
        if cmd == CMD_ASTRO_START_EQ_SOLVING:
            changes: dict[str, Any] = {}
            azi = getattr(message, "azi_err", None)
            alt = getattr(message, "alt_err", None)
            if azi is not None:
                try:
                    changes["eq_azi_err"] = float(azi)
                except (TypeError, ValueError):
                    pass
            if alt is not None:
                try:
                    changes["eq_alt_err"] = float(alt)
                except (TypeError, ValueError):
                    pass
            if changes:
                self.update(changes, force=True)

    def _decode(self, cmd: int, kind: int, data: bytes) -> dict[str, Any]:
        if self._notify is None or self._base is None:
            return {}
        if cmd == CMD_STEP_MOTOR_GET_POSITION:
            if kind not in _RESPONSE_TYPES:
                return {}
            try:
                from dwarf_python_api.proto import motor_control_pb2

                message = motor_control_pb2.ResMotorPosition()
                message.ParseFromString(data)
            except Exception:
                return {}
            code = int(message.code)
            motor_id = int(message.id)
            now = time.monotonic()
            # Always stamp the reply (including errors such as NEED_RESET) so the
            # worker can stop waiting instead of timing out on every axis.
            changes: dict[str, Any] = {
                "motor_pos_last_code": code,
                "motor_pos_last_at": now,
            }
            if code == 0:
                changes[f"motor_pos_{motor_id}"] = float(message.position)
                changes[f"motor_pos_{motor_id}_at"] = now
            return changes
        if kind != TYPE_NOTIFICATION and cmd >= CMD_NOTIFY_ELE:
            return {}
        if cmd == CMD_NOTIFY_TELE_WIDE_PICTURE_MATCHING:
            message = self._parse("PictureMatching", data)
            if message is None:
                return {}
            width = int(message.width)
            height = int(message.height)
            x = int(message.x)
            y = int(message.y)
            return normalize_picture_matching(x, y, width, height)
        if cmd == CMD_NOTIFY_ELE:
            message = self._base.ComResWithInt()
            message.ParseFromString(data)
            try:
                percent = int(message.value)
            except (TypeError, ValueError):
                return {}
            if not self._should_apply_battery(percent, "notify"):
                return {}
            return {"battery_percent": percent}
        if cmd == CMD_NOTIFY_CHARGE:
            message = self._parse("ChargingState", data)
            state = int(message.state)
            return {"charging_state": CHARGING_STATES.get(state, str(state)), "charging": state == 1}
        if cmd == CMD_NOTIFY_SDCARD_INFO:
            message = self._parse("StorageInfo", data)
            return {
                "storage_free_gb": int(message.available_size),
                "storage_total_gb": int(message.total_size),
                "storage_valid": bool(message.is_valid) or int(message.total_size) > 0,
            }
        if cmd == CMD_NOTIFY_TEMPERATURE:
            message = self._parse("Temperature", data)
            return {"temperature_c": int(message.temperature)}
        if cmd == CMD_NOTIFY_CMOS_TEMPERATURE:
            message = self._parse("CmosTemperature", data)
            if not message.HasField("temperature"):
                return {}
            key = "cmos_wide_c" if int(message.camera_type) == 1 else "cmos_tele_c"
            return {key: int(message.temperature)}
        if cmd == CMD_NOTIFY_FOCUS_POSITION:
            message = self._parse("FocusPosition", data)
            return {"focus_position": int(message.pos)}
        if cmd == CMD_NOTIFY_STREAM_TYPE:
            message = self._parse("StreamType", data)
            value = int(message.stream_type)
            key = "stream_type_wide" if int(message.cam_id) == 1 else "stream_type"
            return {key: STREAM_TYPES.get(value, str(value))}
        if cmd == CMD_NOTIFY_RGB_STATE:
            message = self._parse("RgbState", data)
            return {"lights_on": int(message.state) == 1}
        if cmd == CMD_NOTIFY_POWER_IND_STATE:
            message = self._parse("PowerIndState", data)
            return {"indicator_on": int(message.state) == 1}
        if cmd == CMD_NOTIFY_WS_HOST_SLAVE_MODE:
            message = self._parse("HostSlaveMode", data)
            return {"host_mode": int(message.mode) == 0, "host_locked": bool(message.lock)}
        if cmd == CMD_NOTIFY_CPU_MODE:
            message = self._parse("CPUMode", data)
            return {"cpu_mode": int(message.mode)}
        if cmd == CMD_NOTIFY_BODY_STATUS:
            message = self._parse("BodyStatus", data)
            return {"mount_mode": BODY_STATUS.get(int(message.body_status), "")}
        if cmd == CMD_NOTIFY_POWER_OFF:
            return {"power_off": True}
        if cmd == CMD_NOTIFY_STATE_ASTRO_GOTO:
            return self._decode_named_state("AstroGotoState", data, "goto_state", "goto_target", ASTRO_STATES)
        if cmd == CMD_NOTIFY_STATE_ASTRO_TRACKING:
            changes = self._decode_named_state(
                "AstroTrackingState", data, "tracking_state", "tracking_target", OPERATION_STATES
            )
            if changes.get("tracking_state") == "running":
                # The motion motor runs one astro function at a time: tracking
                # taking over means the GOTO slew/solve has finished, even when
                # the firmware never sent a final GOTO idle/stopped notification.
                changes["goto_state"] = "idle"
            return changes
        if cmd == CMD_NOTIFY_STATE_ASTRO_CALIBRATION:
            message = self._parse("AstroCalibrationState", data)
            return {
                "calibration_state": ASTRO_STATES.get(int(message.state), str(message.state)),
                "calibration_phase": int(message.plate_solving_times),
            }
        if cmd == CMD_NOTIFY_EQ_SOLVING_STATE:
            message = self._parse("EqSolvingState", data)
            changes = {"eq_state": OPERATION_STATES.get(int(message.state), str(message.state))}
            for attr, key in (("azi_err", "eq_azi_err"), ("alt_err", "eq_alt_err")):
                if not hasattr(message, attr):
                    continue
                try:
                    changes[key] = float(getattr(message, attr))
                except (TypeError, ValueError):
                    continue
            return changes
        if cmd in (CMD_NOTIFY_STATE_CAPTURE_RAW_LIVE_STACKING, CMD_NOTIFY_STATE_WIDE_CAPTURE_RAW_LIVE_STACKING):
            message = self._parse("CaptureRawState", data)
            state = OPERATION_STATES.get(int(message.state), str(message.state))
            with self._lock:
                hold = self._hold_stale_capture
            if hold and state == "running":
                return {}
            changes: dict[str, Any] = {"capture_state": state}
            changes["capture_camera"] = "wide" if cmd == CMD_NOTIFY_STATE_WIDE_CAPTURE_RAW_LIVE_STACKING else "tele"
            if state in ("idle", "stopped"):
                changes["capture_active"] = False
            elif state == "running":
                changes["capture_active"] = True
            return changes
        if cmd in (CMD_NOTIFY_PROGRASS_CAPTURE_RAW_LIVE_STACKING, CMD_NOTIFY_PROGRASS_WIDE_CAPTURE_RAW_LIVE_STACKING):
            message = self._parse("ProgressCaptureRawLiveStacking", data)
            return self._fresh_stacking_progress(message)
        if cmd == CMD_NOTIFY_PROGRESS_CAPTURE_MOSAIC:
            message = self._parse("ProgressCaptureMosaic", data)
            return self._fresh_stacking_progress(message, mosaic=True)
        if cmd == CMD_NOTIFY_STATE_CAPTURE_RAW_DARK:
            message = self._parse("OperationStateNotify", data)
            state = OPERATION_STATES.get(int(message.state), str(message.state))
            changes = {"dark_state": state}
            if state != "running":
                changes["dark_progress"] = 0
                changes["dark_remaining_s"] = 0
            return changes
        if cmd == CMD_NOTIFY_PROGRASS_CAPTURE_RAW_DARK:
            message = self._parse("ProgressCaptureRawDark", data)
            return {
                "dark_state": "running",
                "dark_progress": int(message.progress),
                "dark_remaining_s": int(message.remaining_time),
            }
        if cmd in (CMD_NOTIFY_TELE_RECORD_TIME, CMD_NOTIFY_WIDE_RECORD_TIME):
            message = self._parse("RecordTime", data)
            return {"record_seconds": int(message.record_time)}
        if cmd == CMD_NOTIFY_RECORD_STATE:
            message = self._parse("RecordState", data)
            state = OPERATION_STATES.get(int(message.state), str(message.state))
            changes = {"record_state": state}
            if state != "running":
                changes["record_seconds"] = 0
            return changes
        if cmd == CMD_NOTIFY_TELE_LONG_EXP_PROGRESS:
            message = self._parse("LongExpPhotoProgress", data)
            return {
                "exposure_total_s": float(message.total_time),
                "exposure_elapsed_s": float(message.exposured_time),
            }
        if cmd == CMD_NOTIFY_GENERAL_INT_PARAM:
            message = self._parse("GeneralIntParam", data)
            param_id = int(message.param_id)
            value = int(message.value)
            if param_id in _EXPOSURE_PARAMS:
                return {"exposure_text": _exposure_name(value, self._model_id), "exposure_auto": int(message.mode) == 0}
            if param_id in _GAIN_PARAMS:
                return {"gain": value}
            if param_id in _WIDE_EXPOSURE_PARAMS:
                return {"wide_exposure_text": _exposure_name(value, self._model_id)}
            if param_id in _WIDE_GAIN_PARAMS:
                return {"wide_gain": value}
            return {}
        return {}

    # ---------------------------------------------------- full device state
    def on_device_state(self, message: Any) -> None:
        """Normalise a full ``ResGetDeviceStateInfo`` message."""
        try:
            changes = self.decode_device_state(message)
        except Exception:
            return
        if "battery_percent" in changes:
            try:
                percent = int(changes["battery_percent"])
            except (TypeError, ValueError):
                changes.pop("battery_percent", None)
            else:
                if not self._should_apply_battery(percent, "state"):
                    changes.pop("battery_percent", None)
        if changes:
            changes["state_snapshot_at"] = time.time()
            self.update(changes, force=True)

    def decode_device_state(self, message: Any) -> dict[str, Any]:
        changes: dict[str, Any] = {}
        if getattr(message, "code", 0):
            return changes
        changes["shooting_mode"] = int(getattr(message, "shooting_mode", 0))
        info = getattr(message, "device_state_info", None)
        if info is not None:
            battery = getattr(info, "battery_info", None)
            if battery is not None and info.HasField("battery_info"):
                if battery.percentage:
                    changes["battery_percent"] = int(battery.percentage)
                if battery.HasField("cycle_count"):
                    changes["battery_cycles"] = int(battery.cycle_count)
                if battery.HasField("soh"):
                    changes["battery_soh"] = int(battery.soh)
            if info.HasField("charging_state"):
                state = int(info.charging_state.state)
                changes["charging_state"] = CHARGING_STATES.get(state, str(state))
                changes["charging"] = state == 1
            if info.HasField("storage_info"):
                storage = info.storage_info
                changes["storage_free_gb"] = int(storage.available_size)
                changes["storage_total_gb"] = int(storage.total_size)
                changes["storage_valid"] = bool(storage.is_valid or storage.total_size)
            if info.HasField("temperature"):
                changes["temperature_c"] = int(info.temperature.temperature)
            if info.HasField("rgb_state"):
                changes["lights_on"] = int(info.rgb_state.state) == 1
            if info.HasField("power_ind_state"):
                changes["indicator_on"] = int(info.power_ind_state.state) == 1
            if info.HasField("cpu_mode"):
                changes["cpu_mode"] = int(info.cpu_mode.mode)
            if info.HasField("body_status"):
                status = int(info.body_status.body_status)
                changes["mount_mode"] = BODY_STATUS.get(status, "")
            if info.HasField("auto_shutdown"):
                changes["auto_shutdown"] = int(info.auto_shutdown.state)
            if info.HasField("lens_defog"):
                changes["lens_defog"] = int(info.lens_defog.state) == 1
            if info.HasField("auto_cooling"):
                changes["auto_cooling"] = int(info.auto_cooling.state) == 1
        for prefix, field in (("tele", "tele_camera_state_info"), ("wide", "wide_camera_state_info")):
            camera = getattr(message, field, None)
            if camera is None or not message.HasField(field):
                continue
            if camera.resolution_width and camera.resolution_height:
                changes[f"{prefix}_resolution"] = f"{int(camera.resolution_width)}×{int(camera.resolution_height)}"
            if camera.h_fov or camera.v_fov:
                changes[f"{prefix}_fov"] = f"{float(camera.h_fov):.2f}° × {float(camera.v_fov):.2f}°"
                changes[f"{prefix}_fov_h"] = float(camera.h_fov)
                changes[f"{prefix}_fov_v"] = float(camera.v_fov)
            if camera.resolution_width and camera.resolution_height:
                # Numeric size: tap-to-center scales clicks into the wide camera's pixel frame.
                changes[f"{prefix}_width"] = int(camera.resolution_width)
                changes[f"{prefix}_height"] = int(camera.resolution_height)
            if camera.HasField("cmos_temperature") and camera.cmos_temperature.HasField("temperature"):
                changes[f"cmos_{prefix}_c"] = int(camera.cmos_temperature.temperature)
            if camera.HasField("stream_type"):
                value = int(camera.stream_type.stream_type)
                changes["stream_type" if prefix == "tele" else "stream_type_wide"] = STREAM_TYPES.get(value, str(value))
            exclusive = camera.exclusive_state if camera.HasField("exclusive_state") else None
            if exclusive is not None:
                which = exclusive.WhichOneof("current_state")
                if which == "capture_raw_state":
                    state = OPERATION_STATES.get(int(exclusive.capture_raw_state.state), "idle")
                    with self._lock:
                        hold = self._hold_stale_capture
                    if not (hold and state == "running"):
                        changes["capture_state"] = state
                        changes["capture_active"] = state == "running"
                elif which == "record_state":
                    changes["record_state"] = OPERATION_STATES.get(int(exclusive.record_state.state), "idle")
                elif which is None and prefix == "tele":
                    # Tracking owns the motors during stacking, so this oneof
                    # can be empty while capture notifications are still live.
                    snapshot = self.snapshot()
                    if snapshot.get("capture_state") != "running" and not snapshot.get("capture_active"):
                        changes["capture_active"] = False
        focus = getattr(message, "focus_motor_state_info", None)
        if focus is not None and message.HasField("focus_motor_state_info"):
            if focus.HasField("focus_position"):
                changes["focus_position"] = int(focus.focus_position.pos)
            if focus.HasField("exclusive_state"):
                which = focus.exclusive_state.WhichOneof("current_state")
                if which:
                    state = int(getattr(focus.exclusive_state, which).state)
                    changes["autofocus_state"] = OPERATION_STATES.get(state, str(state))
                else:
                    changes["autofocus_state"] = "idle"
        motion = getattr(message, "motion_motor_state_info", None)
        if motion is not None and message.HasField("motion_motor_state_info") and motion.HasField("exclusive_state"):
            exclusive = motion.exclusive_state
            which = exclusive.WhichOneof("current_state")
            if which == "astro_calibration_state":
                changes["calibration_state"] = ASTRO_STATES.get(int(exclusive.astro_calibration_state.state), "idle")
                changes["calibration_phase"] = int(exclusive.astro_calibration_state.plate_solving_times)
            elif which == "astro_goto_state":
                changes["goto_state"] = ASTRO_STATES.get(int(exclusive.astro_goto_state.state), "idle")
                changes["goto_target"] = str(exclusive.astro_goto_state.target_name or "")
            elif which == "astro_tracking_state":
                changes["tracking_state"] = OPERATION_STATES.get(int(exclusive.astro_tracking_state.state), "idle")
                changes["tracking_target"] = str(exclusive.astro_tracking_state.target_name or "")
                # Exclusive state: tracking owns the motors, so no GOTO or calibration is running.
                changes["goto_state"] = "idle"
                changes["calibration_state"] = "idle"
            elif which == "eq_state":
                changes["eq_state"] = OPERATION_STATES.get(int(exclusive.eq_state.state), "idle")
            elif which is None:
                changes.setdefault("goto_state", "idle")
                changes.setdefault("calibration_state", "idle")
        connection = getattr(message, "connection_state_info", None)
        if connection is not None and message.HasField("connection_state_info") and connection.HasField("host_slave_mode"):
            changes["host_mode"] = int(connection.host_slave_mode.mode) == 0
            changes["host_locked"] = bool(connection.host_slave_mode.lock)
        return changes

    # ------------------------------------------------------- SDK cache diff
    def poll_client_status(self, status: Any) -> None:
        """Merge the SDK's own notification cache (``get_client_status``)."""
        if not isinstance(status, dict):
            return
        full = status.get("fullStatus", status)
        if not isinstance(full, dict) or full.get("error"):
            return
        changes = normalize_client_status(full, self._model_id)
        if not changes:
            return
        snapshot = self.snapshot()
        with self._lock:
            accept_sdk_counts = self._accept_sdk_capture_counts
        if "battery_percent" in changes:
            try:
                percent = int(changes["battery_percent"])
            except (TypeError, ValueError):
                changes.pop("battery_percent", None)
            else:
                if not self._should_apply_battery(percent, "sdk"):
                    changes.pop("battery_percent", None)
        if not accept_sdk_counts:
            changes.pop("capture_current", None)
            changes.pop("capture_stacked", None)
        elif snapshot.get("capture_active") or snapshot.get("capture_state") == "running":
            # After a reconnect the SDK cache starts at 0 until it sees the
            # next progress packet; never let that clobber notification counts.
            for key in ("capture_current", "capture_stacked"):
                if key not in changes:
                    continue
                try:
                    if int(changes[key]) < int(snapshot.get(key) or 0):
                        changes.pop(key, None)
                except (TypeError, ValueError):
                    continue
        if changes:
            self.update(changes, force=True)


def normalize_client_status(full: dict[str, Any], model_id: str = "3") -> dict[str, Any]:
    changes: dict[str, Any] = {}

    def put(key: str, value: Any) -> None:
        if value is not None:
            changes[key] = value

    if full.get("BatteryLevelDwarf") is not None:
        put("battery_percent", int(full["BatteryLevelDwarf"]))
    if full.get("totalSizeDwarf") is not None:
        put("storage_total_gb", int(full["totalSizeDwarf"]))
        put("storage_free_gb", int(full.get("availableSizeDwarf") or 0))
        put("storage_valid", True)
    if full.get("TemperatureLevelDwarf") is not None:
        put("temperature_c", int(full["TemperatureLevelDwarf"]))
    cmos = full.get("CmosTemperatureDwarf") or {}
    if isinstance(cmos, dict):
        for key, value in cmos.items():
            try:
                camera = int(key)
            except (TypeError, ValueError):
                continue
            put("cmos_wide_c" if camera == 1 else "cmos_tele_c", int(value))
    if full.get("FocusValueDwarf") is not None:
        put("focus_position", int(full["FocusValueDwarf"]))
    if full.get("StreamTypeDwarf") is not None:
        value = int(full["StreamTypeDwarf"])
        put("stream_type", STREAM_TYPES.get(value, str(value)))
    if full.get("PowerIndicatorDwarf") is not None:
        put("indicator_on", int(full["PowerIndicatorDwarf"]) == 1)
    if full.get("RgbIndicatorDwarf") is not None:
        put("lights_on", int(full["RgbIndicatorDwarf"]) == 1)
    if full.get("HostMode") is not None:
        put("host_mode", bool(full["HostMode"]))
    capturing = bool(full.get("AstroCapture")) or bool(full.get("AstroWideCapture"))
    if capturing:
        # The SDK sets AstroCapture as soon as START_CAPTURE is *sent*, even when
        # the device rejects it as busy. Frame counts are still useful; activity
        # comes from the capture-state notifications instead.
        wide = bool(full.get("AstroWideCapture")) and not bool(full.get("AstroCapture"))
        count_key, stacked_key = ("takeWidePhotoCount", "takeWidePhotoStacked") if wide else ("takePhotoCount", "takePhotoStacked")
        if full.get("takeMosaicCount"):
            count_key, stacked_key = "takeMosaicCount", "takeMosaicStacked"
        put("capture_current", int(full.get(count_key) or 0))
        put("capture_stacked", int(full.get(stacked_key) or 0))
    params = full.get("CameraParamsDwarf") or {}
    if isinstance(params, dict):
        for raw_id, entry in params.items():
            try:
                param_id = int(raw_id)
                value = int((entry or {}).get("value"))
            except (TypeError, ValueError, AttributeError):
                continue
            if param_id in _EXPOSURE_PARAMS:
                put("exposure_text", _exposure_name(value, model_id))
                put("exposure_auto", int((entry or {}).get("mode", 1)) == 0)
            elif param_id in _GAIN_PARAMS:
                put("gain", value)
            elif param_id in _WIDE_EXPOSURE_PARAMS:
                put("wide_exposure_text", _exposure_name(value, model_id))
            elif param_id in _WIDE_GAIN_PARAMS:
                put("wide_gain", value)
    return changes


# ---------------------------------------------------------------- SDK logs
NOTICE_LEVEL = 22
SUCCESS_LEVEL = 25

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RE = re.compile(r"[ \t]+")
_NOISE_PREFIXES = (
    "wait for frames",
    "receiving...",
    "receiving...  data",
    "------------------",
    "#----------------#",
    "result_receive_messages",
    "end result_receive_messages",
    "result_notification_messages",
    "end result_notification_messages",
    "timeout: init",
    "timeout: reset",
    "timeout: cancelled",
    "terminating timeout",
    "terminating ping",
    "terminating receive",
    "sent a ping frame",
    "pong",
    "ping cancelled",
    "initializing...",
    "already initialized",
    "continue decoding",
    "decoding cmd_",
    "decoding ",
    "result sent for",
    "send cmd >>",
    ">> cmd_",
    "receive cmd >>",
    "msg data len is",
    "log file disabled",
    "file_log_level",
    "root_level",
    "{'cmd_send'",
    "{\"cmd_send\"",
)
# SDK lines that are technically NOTICE/SUCCESS/INFO but are plumbing chatter; keep them
# available under the DEBUG filter instead of the main log.
_DEMOTE_PREFIXES = (
    "--- shooting_mode_and_techs",
    "shooting_mode=",
    "--- end shooting_mode_and_techs",
    "success get device state info",
    "get device state info code",
    "terminating ",
    "result : ",
    "receiving command",
    "sendind init end",
    "sending init end",
    "ok cmd_",
    "cmd_notify_rgb_state received",
    "cmd_notify_power_ind_state received",
    "disconnect signal sent",
    "websocketclient terminated",
    "websocket terminated",
    "disconnected",  # the app logs its own "Disconnected" line
    "dwarf stream video type is unknown",  # stream_type 0 = camera not streaming yet
    "skipping malformed astrogotostate",
    # Centre-tap probes the encoders; on an unhomed mount the firmware answers
    # NEED_RESET and the worker falls back to Dual Lenses Locating itself.
    "error motor need reset",
    "error cmd_step_motor_get_position code code_step_motor_need_reset",
    # Dwarf 3 firmware often rejects IANA/GMT/UTC timezone strings; SET_TIME
    # already applied the offset, so the worker tries the next format.
    "error cmd_system_set_time_zone",
    "receive id data >>",
    "receive code data >>",
    "receive position data >>",
    ">> code_step_motor_need_reset",
    "success cmd_step_motor_get_position",
)
_MAX_LOG_CHARS = 400


def sanitize_log_text(text: Any) -> str:
    value = str(text or "")
    value = _ANSI_RE.sub("", value)
    value = _CONTROL_RE.sub("", value)
    lines = [_SPACE_RE.sub(" ", line).strip() for line in value.replace("\r", "\n").split("\n")]
    value = " ⏎ ".join(line for line in lines if line)
    if len(value) > _MAX_LOG_CHARS:
        value = value[: _MAX_LOG_CHARS - 1] + "…"
    return value


def is_noise(text: str) -> bool:
    lowered = text.lower()
    if not lowered:
        return True
    return lowered.startswith(_NOISE_PREFIXES)


def is_chatter(text: str) -> bool:
    """SDK plumbing lines that should be demoted to debug rather than shown as notices."""
    return text.lower().startswith(_DEMOTE_PREFIXES)


def level_name(levelno: int) -> str:
    if levelno >= logging.ERROR:
        return "error"
    if levelno >= logging.WARNING:
        return "warning"
    if levelno >= SUCCESS_LEVEL:
        return "success"
    if levelno >= NOTICE_LEVEL:
        return "notice"
    if levelno >= logging.INFO:
        return "sdk"
    return "debug"


class SdkLogHandler(logging.Handler):
    """Forward SDK logger records to the worker's structured event stream."""

    def __init__(self, emit: Callable[[dict[str, Any]], None]):
        super().__init__(level=logging.DEBUG)
        self._emit = emit

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401 - logging API
        try:
            text = sanitize_log_text(record.getMessage())
        except Exception:
            return
        if not text:
            return
        level = level_name(record.levelno)
        if is_chatter(text):
            level = "debug"
        elif level in ("sdk", "debug") and is_noise(text):
            return
        try:
            self._emit({"event": "log", "level": level, "message": text, "source": "sdk"})
        except Exception:
            pass


def install_sdk_logging(emit: Callable[[dict[str, Any]], None]) -> bool:
    """Replace the SDK's console handler with the structured handler."""
    logger = logging.getLogger("my_logger")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            logger.removeHandler(handler)
    if any(isinstance(handler, SdkLogHandler) for handler in logger.handlers):
        return True
    logger.addHandler(SdkLogHandler(emit))
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return True
