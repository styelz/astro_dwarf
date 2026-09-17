from __future__ import annotations

import json
import logging
import sys
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from uuid import uuid4

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QProcess,
    QProcessEnvironment,
    QObject,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage

from .screen_color import ScreenColorPicker
from .version import __version__
from .domain import (
    Camera,
    CameraSettings,
    CaptureDefaults,
    Device,
    DeviceModel,
    HardwareProfile,
    Mosaic,
    Session,
    SessionStatus,
    SessionTemplate,
    Target,
    TargetKind,
    WifiMode,
    Workflow,
    LOCAL_ALBUM_SUFFIXES,
    album_http_url,
    album_is_astro_media,
    album_is_video_name,
    album_local_file_in_dir,
    album_media_kind,
    album_path_matches_model,
    apply_camera_fov_defaults,
    camera_fov,
    camera_settings_from_capture,
    capture_defaults_from_dict,
    clamp_cutoff_hour,
    DEVICE_COLORS,
    default_device_name,
    device_from_dict,
    firmware_exposure_name,
    is_first_device_setup,
    next_device_color,
    normalize_device_color,
    parse_mosaic_pa,
    history_record_for_run,
    normalized_stellarium_url,
    session_from_dict,
    to_dict,
)
from .services import (
    DurationEngine,
    STELLARIUM_WEB_URL,
    SKY_WEB_BOOT_JS,
    SKY_WEB_HARVEST_JS,
    StellariumClient,
    generate_mosaic_plan,
    import_telescopius,
    mosaic_group_title,
    mosaic_grid_size,
    mosaic_pane_footprints,
    mosaic_pane_number,
    mosaic_pane_workflow,
    mosaic_session_footprints,
    mosaic_south_up,
    next_free_start,
    observing_date,
    pane_sort_key,
    device_mosaic_pa,
    parse_sky_web_target,
    parse_in_zone,
    SKY_WEB_CONTEXT_POLL_JS,
    SKY_WEB_DBLCLICK_POLL_JS,
    SKY_WEB_OPACITY_POLL_JS,
    sky_web_fov_script,
    sky_web_live_script,
    sky_web_pane_script,
    sky_web_site_script,
    sky_web_template_notes,
    session_window,
    sessions_overlap,
    stagger_mosaic_sessions,
    store_local_iso,
    zoneinfo_from_name,
)
from .duration_suggest import suggest_hardware_profile
from .location import has_site_coordinates, match_timezone, resolve_location, suggested_timezone, timezone_locations
from .runtime import (
    PROCESS_CREATION_FLAGS,
    is_frozen,
    kill_pid_tree,
    linux_webengine_available,
    native_webview_plugin_present,
    prepare_worker_environment,
    worker_command,
)
from .storage import SessionStore
from .image_enhance import (
    CacheEnhanceJob,
    CacheEnhanceSignals,
    PreviewEnhanceJob,
    PreviewEnhanceSignals,
    canonical_image_url,
    enhance_available,
    enhance_cache_key,
    is_enhance_cache_valid,
    set_enhance_levels,
)
from .stream_preview import (
    LiveFrames,
    MosaicFrames,
    StreamPlayer,
    live_frame_data_url,
    port_is_open,
    preview_window_is_live,
    set_live_frames,
    set_mosaic_frames,
    stream_port,
)
from .telemetry_view import AlertEngine, camera_params_to_telemetry, derive_activity, format_telemetry


def _sky_web_blocked_by_gpu() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    from .qt_display import needs_software_qt

    return needs_software_qt()


def _webview_available() -> bool:
    # Linux has no WebView2/WKWebView. Stellarium Web is Qt WebEngine there,
    # but only when the session can create a GL context.
    if sys.platform.startswith("linux"):
        return linux_webengine_available()
    try:
        from PySide6.QtWebView import QtWebView  # noqa: F401
    except Exception:
        return False
    # Importing QtWebView is not enough: the backend lives in plugins/webview
    # and is loaded only when QML creates a WebView. Missing that plugin aborts.
    if is_frozen() and not native_webview_plugin_present():
        return False
    return True


class TelescopeProcess(QObject):
    logReceived = Signal(str, str)
    progressReceived = Signal(str, str, float)
    statusReceived = Signal(str, str)
    telemetryReceived = Signal(dict)
    availabilityChanged = Signal()

    def __init__(self, device: Device, parent: QObject | None = None):
        super().__init__(parent)
        self.device = device
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        if sys.platform == "win32" and hasattr(self.process, "setCreateProcessArgumentsModifier"):
            self.process.setCreateProcessArgumentsModifier(
                lambda args: args.setCreateFlags(int(args.createFlags()) | PROCESS_CREATION_FLAGS)
            )
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUNBUFFERED", "1")
        prepare_worker_environment(environment)
        self.process.setProcessEnvironment(environment)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)
        self.process.errorOccurred.connect(self._process_error)
        self.process.started.connect(self._process_started)
        self.process.finished.connect(self._finished)
        self._stdout = ""
        self._stderr = ""
        self._sequence = 0
        self._callbacks: dict[int, Callable[[bool, Any], None]] = {}
        self._queued_commands: list[tuple[str, dict[str, Any] | None, Callable[[bool, Any], None] | None]] = []
        self.configured = False
        self.connected = False
        self.busy = False
        self._reject_link = False
        self._stopping = False

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start(self) -> None:
        if self.running:
            return
        self.logReceived.emit("info", f"Starting isolated worker for {self.device.name}")
        program, arguments = worker_command()
        self.process.start(program, arguments)

    def _process_started(self) -> None:
        self.send("configure", {"device": to_dict(self.device)}, self._configured)

    def _configured(self, ok: bool, result: Any) -> None:
        self.configured = ok
        self.logReceived.emit("success" if ok else "error", "Worker configured" if ok else str(result))
        if ok:
            queued, self._queued_commands = self._queued_commands, []
            for command, payload, callback in queued:
                self.send(command, payload, callback)
        else:
            queued, self._queued_commands = self._queued_commands, []
            for _command, _payload, callback in queued:
                if callback:
                    callback(False, result)
        self.availabilityChanged.emit()

    def send(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        callback: Callable[[bool, Any], None] | None = None,
    ) -> int:
        if command != "configure" and not self.configured:
            self._queued_commands.append((command, payload, callback))
            self.start()
            return 0
        if not self.running:
            self.start()
        self._sequence += 1
        request_id = self._sequence
        if callback:
            self._callbacks[request_id] = callback
        message = {"id": request_id, "command": command, **(payload or {})}
        self.process.write((json.dumps(message) + "\n").encode())
        return request_id

    def connect_device(
        self,
        callback: Callable[[bool, Any], None],
        claimed_ips: list[str] | None = None,
    ) -> None:
        self._reject_link = False
        ips = [str(ip).strip() for ip in (claimed_ips or []) if str(ip).strip()]
        self.send(
            "connect",
            {"claimed_ips": ips},
            callback=lambda ok, result: self._connected(ok, result, callback),
        )

    def _connected(self, ok: bool, result: Any, callback: Callable[[bool, Any], None]) -> None:
        handshake = bool(ok and result)
        self.connected = handshake and not self._reject_link
        self.availabilityChanged.emit()
        callback(handshake, result)

    def disconnect_device(self, callback: Callable[[bool, Any], None] | None = None) -> None:
        self._reject_link = True

        def done(ok: bool, result: Any) -> None:
            self.connected = False
            self.availabilityChanged.emit()
            if callback:
                callback(ok, result)

        self.send("disconnect", callback=done)

    def run_session(self, session: Session, callback: Callable[[bool, Any], None]) -> None:
        self.busy = True
        self.availabilityChanged.emit()

        def done(ok: bool, result: Any) -> None:
            self.busy = False
            self.availabilityChanged.emit()
            callback(ok, result)

        self.send("run_session", {"session": to_dict(session)}, done)

    def stop_all(self) -> None:
        self.send("stop_all", callback=lambda ok, result: self.logReceived.emit(
            "warning" if ok else "error", "Stop commands sent" if ok else str(result)
        ))

    def shutdown(self, wait: bool = True) -> None:
        self._stopping = True
        if not self.running:
            return
        pid = int(self.process.processId() or 0)
        try:
            self.process.closeWriteChannel()
        except RuntimeError:
            pass
        try:
            self.process.kill()
        except RuntimeError:
            pass
        kill_pid_tree(pid)
        if wait:
            try:
                self.process.waitForFinished(400)
            except RuntimeError:
                pass

    def _read_stdout(self) -> None:
        self._stdout += bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        while "\n" in self._stdout:
            line, self._stdout = self._stdout.split("\n", 1)
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self.logReceived.emit("info", line)
                continue
            event = message.get("event")
            if event == "log":
                self.logReceived.emit(message.get("level", "info"), message.get("message", ""))
            elif event == "telemetry":
                data = message.get("data")
                if isinstance(data, dict) and data:
                    self.telemetryReceived.emit(data)
            elif event == "progress":
                try:
                    wait_seconds = float(message.get("wait_seconds") or 0)
                except (TypeError, ValueError):
                    wait_seconds = 0.0
                self.progressReceived.emit(message["session_id"], message["step"], wait_seconds)
            elif event == "status":
                self.statusReceived.emit(str(message.get("kind") or ""), str(message.get("step") or ""))
            elif event == "connected":
                if not self._reject_link and not self.connected:
                    self.connected = True
                    self.availabilityChanged.emit()
            elif event == "response":
                try:
                    request_id = int(message.get("id") or 0)
                except (TypeError, ValueError):
                    request_id = 0
                callback = self._callbacks.pop(request_id, None)
                if callback:
                    callback(bool(message.get("ok")), message.get("result") if message.get("ok") else message.get("error"))

    def _read_stderr(self) -> None:
        self._stderr += bytes(self.process.readAllStandardError()).decode(errors="replace")
        while "\n" in self._stderr:
            line, self._stderr = self._stderr.split("\n", 1)
            if line.strip():
                self.logReceived.emit("sdk", line.rstrip())

    def _finished(self, exit_code: int, _status) -> None:
        self.configured = self.connected = self.busy = False
        if not self._stopping:
            self.logReceived.emit("warning" if exit_code == 0 else "error", f"Worker stopped (code {exit_code})")
        pending, self._callbacks = self._callbacks, {}
        for callback in pending.values():
            callback(False, "Telescope worker stopped")
        self.availabilityChanged.emit()

    def _process_error(self, error) -> None:
        if self._stopping:
            return
        try:
            self.logReceived.emit("error", f"Worker error: {error}")
        except RuntimeError:
            pass


_ACTIVITY_START = {
    "burst_start": "burst",
    "record_start": "record",
    "timelapse_start": "timelapse",
    "polar": "polar",
    "calibrate": "calibrate",
    "autofocus": "autofocus",
    "infinity": "infinity",
    "track": "goto",
    "sky_track": "goto",
    "stack": "imaging",
}
# Session steps that should light a command pad. Astro autofocus has no
# firmware state notify (calibrate / GOTO / EQ do), so the pad stays dark
# unless the running session step is mapped here.
_SESSION_STEP_ACTIVITY = {
    "auto focus": "autofocus",
    "infinity focus": "infinity",
    "infinity focus before polar alignment": "infinity",
}
_SESSION_STEP_ACTIVITIES = frozenset(_SESSION_STEP_ACTIVITY.values())


def _activity_for_session_step(step: str) -> str:
    base = str(step or "").split(" · ")[0].strip().lower()
    return _SESSION_STEP_ACTIVITY.get(base, "")


_ACTIVITY_STOP = {
    "burst_stop": "burst",
    "record_stop": "record",
    "timelapse_stop": "timelapse",
    "stop_polar": "polar",
    "stop_calibrate": "calibrate",
    "stop_autofocus": "autofocus",
    "stop_goto": "goto",
    "stop_astro": "imaging",
}
_ACTIVITY_CLEAR = {"stop_all", "stop_session", "reboot", "power_down", "go_live"}
_STOP_ACTIONS = {"stop_all", "stop_session"}
_CAPTURE_PREVIEW_STEPS = {
    "Start capture",
    "Start wide capture",
    "Start mosaic",
    "Waiting for capture",
    "Waiting for mosaic",
    "Waiting for wide capture",
    "Waiting for stack",
    "Waiting for wide stack",
    "Joining capture",
    "Imaging",
    "Imaging (wide)",
}
_MEDIA_LOCKED_STATUS = (
    "The telescope album isn't available while it's capturing. "
    "Wait until imaging finishes, or switch to Local."
)


_STACK_RESULT_RETRY_MS = 2000
_STACK_RESULT_RETRY_S = 30.0
_STACK_RESULT_LOADING = "Loading completed stack…"
_STACK_RESULT_READY = (
    "Completed stack from the telescope. This is not live video. Dismiss it, or start live view."
)


def stacking_preview_result_copy(
    ok: bool,
    stopped: bool,
    target: str,
    scheduler_enabled: bool,
) -> tuple[str, str]:
    """Caption shown over the completed stack after capture ends."""
    name = str(target or "this target").strip() or "this target"
    if ok:
        title = "SESSION COMPLETE"
    elif stopped:
        title = "SESSION STOPPED"
    else:
        title = "SESSION FAILED"
    extra = f"{name} · completed stack from the telescope. This is not live video."
    if scheduler_enabled:
        extra += " The next capture will show stacking preview if you leave this up."
    else:
        extra += " Dismiss it, or start live view."
    return title, extra


# Calibrate ACK is not completion — firmware calibration_state lights the pad.
# Live autofocus/infinity stay on the pad until telemetry goes idle or Stop.
_ACTIVITY_TRANSIENT = {"calibrate"}
_ACTION_LABELS = {
    "calibrate": "Calibration started",
    "stop_calibrate": "Calibration stopped",
    "autofocus": "Autofocus started",
    "infinity": "Infinity focus started",
    "stop_autofocus": "Autofocus stopped",
    "polar": "Polar alignment started",
    "stop_polar": "Polar alignment stopped",
    "polar_position": "Polar positioning started",
    "go_live": "Closed previous capture",
    "photo_mode": "Photo mode",
    "astro_mode": "Astro mode",
    "lights_on": "Ring light on",
    "lights_off": "Ring light off",
    "indicator_on": "Power indicator on",
    "indicator_off": "Power indicator off",
    "burst_start": "Burst started",
    "burst_stop": "Burst stopped",
    "record_start": "Recording started",
    "record_stop": "Recording stopped",
    "timelapse_start": "Timelapse started",
    "timelapse_stop": "Timelapse stopped",
    "photo": "Photo captured",
    "wide_photo": "Wide photo captured",
    "set_wb_preset": "White balance set",
    "set_wb": "White balance set",
    "set_brightness": "Brightness set",
    "set_contrast": "Contrast set",
    "set_saturation": "Saturation set",
    "set_hue": "Hue set",
    "set_sharpness": "Sharpness set",
    "set_burst_count": "Burst count set",
    "set_burst_interval": "Burst interval set",
    "set_timelapse_interval": "Timelapse interval set",
    "set_timelapse_duration": "Timelapse duration set",
    "set_stack_format": "Stack format set",
    "set_count": "Stack count set",
    "set_auto_calibration": "Auto calibration updated",
    "track": "Tracking started",
    "sky_track": "Sky-map tracking started",
    "stop_goto": "Tracking stopped",
    "stack": "Stack started",
    "stop_astro": "Stack stopped",
    "stop_all": "Stop sent",
    "stop_session": "Session stop sent",
    "reboot": "Reboot requested",
    "power_down": "Power down requested",
    "open_camera": "Tele camera opened",
    "open_wide_camera": "Wide camera opened",
}
_ACTION_DETAILS = {
    "calibrate": "Device will plate-solve and report progress",
    "autofocus": "Watch the focus position in VITALS",
    "polar_position": "Homes and slews the mount to the polar-alignment pose",
    "track": "Firmware will plate-solve this pointing and start sidereal tracking",
    "sky_track": "Telescope will slew to the sky-map target, plate-solve, and start sidereal tracking",
    "stack": "Live stacking uses the current exposure, gain and count",
    "reboot": "The connection will drop for ~60 s",
    "power_down": "The connection will drop",
}
_LOG_LIMIT = 600
_LOG_TRIM_BATCH = 100
_LOG_GLYPHS = {
    "DEBUG": "·",
    "SDK": "›",
    "INFO": "●",
    "NOTICE": "◆",
    "SUCCESS": "✓",
    "WARNING": "⚠",
    "ERROR": "✗",
}
_LOG_FILTERS = {
    # filter name -> levels shown (None = everything)
    "all": {"INFO", "NOTICE", "SUCCESS"},
    "device": {"NOTICE", "SUCCESS"},
    "alerts": {"WARNING", "ERROR"},
    "debug": None,
}


class LogListModel(QAbstractListModel):
    TimeRole = Qt.ItemDataRole.UserRole + 1
    LevelRole = Qt.ItemDataRole.UserRole + 2
    DeviceRole = Qt.ItemDataRole.UserRole + 3
    MessageRole = Qt.ItemDataRole.UserRole + 4
    GlyphRole = Qt.ItemDataRole.UserRole + 5
    CategoryRole = Qt.ItemDataRole.UserRole + 6
    CountRole = Qt.ItemDataRole.UserRole + 7

    countsChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._all: list[dict[str, Any]] = []
        self._visible: list[dict[str, Any]] = []
        self._filter = "all"
        self._counts: dict[str, int] = {"WARNING": 0, "ERROR": 0}
        self._unread: dict[str, int] = {"WARNING": 0, "ERROR": 0}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._visible)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._visible)):
            return None
        entry = self._visible[index.row()]
        if role == self.TimeRole:
            return entry["time"]
        if role == self.LevelRole:
            return entry["level"]
        if role == self.DeviceRole:
            return entry["device"]
        if role == self.MessageRole:
            return entry["message"]
        if role == self.GlyphRole:
            return _LOG_GLYPHS.get(entry["level"], "●")
        if role == self.CategoryRole:
            return entry.get("category", "app")
        if role == self.CountRole:
            return entry.get("count", 1)
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TimeRole: b"time",
            self.LevelRole: b"level",
            self.DeviceRole: b"device",
            self.MessageRole: b"message",
            self.GlyphRole: b"glyph",
            self.CategoryRole: b"category",
            self.CountRole: b"count",
        }

    def visible_entries(self) -> list[dict[str, Any]]:
        return list(self._visible)

    @property
    def filter_name(self) -> str:
        return self._filter

    def warning_count(self) -> int:
        return self._unread.get("WARNING", 0)

    def error_count(self) -> int:
        return self._unread.get("ERROR", 0)

    def _clear_unread(self) -> None:
        if not any(self._unread.values()):
            return
        self._unread = {"WARNING": 0, "ERROR": 0}
        self.countsChanged.emit()

    def _note_unread(self, level: str) -> None:
        if level not in self._unread or self._filter == "alerts":
            return
        self._unread[level] += 1
        self.countsChanged.emit()

    @staticmethod
    def _same_line(last: dict[str, Any] | None, entry: dict[str, Any]) -> bool:
        return (
            last is not None
            and last.get("message") == entry.get("message")
            and last.get("level") == entry.get("level")
            and last.get("device") == entry.get("device")
        )

    def _visible_row(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "time": entry.get("time", ""),
            "level": entry.get("level", "INFO"),
            "device": entry.get("device", ""),
            "message": entry.get("message", ""),
            "category": entry.get("category", "app"),
            "count": int(entry.get("count", 1)),
        }

    def _coalesced_visible(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entry in self._all:
            if not self._is_visible(entry):
                continue
            if rows and self._same_line(rows[-1], entry):
                rows[-1]["count"] = int(rows[-1].get("count", 1)) + int(entry.get("count", 1))
                rows[-1]["time"] = entry.get("time", rows[-1]["time"])
            else:
                rows.append(self._visible_row(entry))
        return rows

    def _bump_visible(self, entry: dict[str, Any]) -> bool:
        if not (self._visible and self._same_line(self._visible[-1], entry)):
            return False
        last = self._visible[-1]
        last["count"] = int(last.get("count", 1)) + int(entry.get("count", 1))
        last["time"] = entry.get("time", last["time"])
        row = len(self._visible) - 1
        self.dataChanged.emit(self.index(row), self.index(row), [self.TimeRole, self.CountRole])
        return True

    def append(self, entry: dict[str, Any]) -> None:
        last = self._all[-1] if self._all else None
        if last is not None and self._same_line(last, entry):
            last["count"] = int(last.get("count", 1)) + 1
            last["time"] = entry["time"]
            self._note_unread(str(last.get("level") or ""))
            self._bump_visible({
                "time": entry["time"],
                "level": last["level"],
                "device": last["device"],
                "message": last["message"],
                "count": 1,
            })
            return
        entry.setdefault("count", 1)
        self._all.append(entry)
        level = entry["level"]
        if level in self._counts:
            self._counts[level] += 1
            self._note_unread(level)
        if self._is_visible(entry) and not self._bump_visible(entry):
            row = len(self._visible)
            self.beginInsertRows(QModelIndex(), row, row)
            self._visible.append(self._visible_row(entry))
            self.endInsertRows()
        if len(self._all) > _LOG_LIMIT:
            self._trim(_LOG_TRIM_BATCH + len(self._all) - _LOG_LIMIT)

    def _trim(self, count: int) -> None:
        removed = self._all[:count]
        del self._all[:count]
        for entry in removed:
            if entry["level"] in self._counts:
                self._counts[entry["level"]] = max(0, self._counts[entry["level"]] - 1)
        for level in self._unread:
            self._unread[level] = min(self._unread[level], self._counts[level])
        self.beginResetModel()
        self._visible = self._coalesced_visible()
        self.endResetModel()
        self.countsChanged.emit()

    def clear(self) -> None:
        self.beginResetModel()
        self._all.clear()
        self._visible.clear()
        self._counts = {"WARNING": 0, "ERROR": 0}
        self._unread = {"WARNING": 0, "ERROR": 0}
        self.endResetModel()
        self.countsChanged.emit()

    def set_filter(self, name: str) -> None:
        name = name if name in _LOG_FILTERS else "all"
        if name == "alerts":
            self._clear_unread()
        if name == self._filter:
            return
        self._filter = name
        self.beginResetModel()
        self._visible = self._coalesced_visible()
        self.endResetModel()

    def _is_visible(self, entry: dict[str, Any]) -> bool:
        allowed = _LOG_FILTERS.get(self._filter)
        if allowed is None:
            return True
        return entry.get("level") in allowed


class _PreviewWindowFilter(QObject):
    def eventFilter(self, _watched, event) -> bool:
        if event.type() in (
            QEvent.Type.Expose,
            QEvent.Type.Show,
            QEvent.Type.WindowActivate,
            QEvent.Type.ApplicationActivate,
        ):
            backend = self.parent()
            if backend is not None:
                backend._on_preview_window_state()
        return False


class AppBackend(QObject):
    devicesChanged = Signal()
    sessionsChanged = Signal()
    currentSessionChanged = Signal()
    templatesChanged = Signal()
    historyChanged = Signal()
    durationSuggestionChanged = Signal()
    selectedDeviceChanged = Signal()
    statusChanged = Signal()
    schedulerEnabledChanged = Signal()
    clockChanged = Signal()
    sessionProgressChanged = Signal()
    toast = Signal(str, str, str, "QVariantMap")
    commandFeedback = Signal(str, str, bool)
    logFilterChanged = Signal()
    logCountsChanged = Signal()
    locationLookupReady = Signal("QVariantMap")
    locationLookupBusyChanged = Signal()
    deviceDiscoveryReady = Signal("QVariantList")
    deviceDiscoveryBusyChanged = Signal()
    _asyncResult = Signal(str, object)
    uiBusyChanged = Signal()
    previewActiveChanged = Signal()
    previewPlayingChanged = Signal()
    previewStatusChanged = Signal()
    previewTelePlayingChanged = Signal()
    previewWidePlayingChanged = Signal()
    previewHoldChanged = Signal()
    previewStackingChanged = Signal()
    previewResultChanged = Signal()
    mosaicPreviewChanged = Signal()
    enhanceImagesChanged = Signal()
    deepCleanImagesChanged = Signal()
    enhanceDenoiseChanged = Signal()
    enhanceSkyCrushChanged = Signal()
    enhanceCacheChanged = Signal()
    mediaChanged = Signal()
    mediaItemsChanged = Signal()
    appSettingsChanged = Signal()
    skyTargetChanged = Signal()
    stellariumRcChanged = Signal()
    _openTeleStream = Signal(str)
    _openWideStream = Signal(str)
    _closeWideStream = Signal()
    _closePreviewStreams = Signal()
    _previewReady = Signal(int, str, str)

    def __init__(self, data_root: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.store = SessionStore(data_root)
        self._devices = self.store.devices.all()
        if not self._devices:
            self._devices = [self.store.seed_device()]
        self._settings = self.store.load_app_settings(self._devices)
        wanted = str(self._settings.last_device_id or "")
        ids = {item.id for item in self._devices}
        self._selected_device_id = wanted if wanted in ids else self._devices[0].id
        if self._selected_device_id != wanted:
            self._settings = replace(self._settings, last_device_id=self._selected_device_id)
            self.store.save_app_settings(self._settings)
        self._log_model = LogListModel(self)
        self._log_model.countsChanged.connect(self.logCountsChanged)
        self._screen_color = ScreenColorPicker(self)
        self._workers: dict[str, TelescopeProcess] = {}
        self._active_sessions: dict[str, str] = {}
        self._stop_requested: set[str] = set()
        self._scheduler_enabled = False
        self._clock_text = datetime.now(self._zone_for()).strftime("%H:%M:%S")
        self._connecting_ids: set[str] = set()
        self._cancel_connect_ids: set[str] = set()
        self._cancel_disconnect_done: set[str] = set()
        self._disconnecting_ids: set[str] = set()
        self._pending_reconnect_ids: set[str] = set()
        self._pending_actions: dict[str, str] = {}
        self._pending_details: dict[str, str] = {}
        self._device_activity: dict[str, str] = {}
        self._device_telemetry: dict[str, dict[str, Any]] = {}
        self._session_capture_base: dict[str, int] = {}
        self._session_capture_peak: dict[str, int] = {}
        self._session_timing: dict[str, dict[str, Any]] = {}
        self._hold_session_capture: set[str] = set()
        self._pending_session_finish: dict[str, tuple[str, bool, Any]] = {}
        self.historyChanged.connect(self.durationSuggestionChanged)
        self._recovered_sessions: dict[str, str] = {}
        self._resume_attempted: set[str] = set()
        self._telemetry_updated: dict[str, float] = {}
        self._alerts = AlertEngine()
        self._last_toast: tuple[str, str, float] = ("", "", 0.0)
        self._device_lights: dict[str, bool] = {}
        self._device_indicators: dict[str, bool] = {}
        self._album_items: list[dict[str, Any]] = []
        self._album_path = ""
        self._album_busy = ""
        self._media_source = "astro"
        self._media_items: list[dict[str, Any]] = []
        self._media_selected_id = ""
        self._media_device_id = ""
        self._media_request_id = 0
        self._media_status = ""
        self._media_locked = False
        self._media_download_queue: list[str] = []
        self._media_download_batch = 0
        self._media_download_ok = 0
        self._media_download_failed = 0
        self._telemetry_tick = 0
        self._sessions_view: list[dict[str, Any]] | None = None
        self._upcoming_sessions_view: list[dict[str, Any]] | None = None
        self._current_session_view: dict[str, Any] | None = None
        self._devices_view: list[dict[str, Any]] | None = None
        self._selected_device_view: dict[str, Any] | None = None
        self._devices_dirty = True
        self._devices_notify_timer = QTimer(self)
        self._devices_notify_timer.setSingleShot(True)
        self._devices_notify_timer.setInterval(200)
        self._devices_notify_timer.timeout.connect(self._flush_devices_notify)
        self._retarget_timer = QTimer(self)
        self._retarget_timer.setSingleShot(True)
        self._retarget_timer.setInterval(250)
        self._retarget_timer.timeout.connect(self._flush_preview_retarget)
        self._pending_retarget: tuple[str, str, float] | None = None
        self._stack_result_timer = QTimer(self)
        self._stack_result_timer.setSingleShot(True)
        self._stack_result_timer.setInterval(_STACK_RESULT_RETRY_MS)
        self._stack_result_timer.timeout.connect(self._fetch_stack_result_image)
        self._stack_result_token = 0
        self._stack_result_loaded = False
        self._stack_result_device_id = ""
        self._stack_result_target = ""
        self._stack_result_camera = ""
        self._stack_result_since = 0
        self._stack_result_started = 0.0
        self._stack_result_final_detail = ""
        self._joystick_inflight: set[str] = set()
        self._joystick_pending: dict[str, tuple[float, float]] = {}
        self._center_tap_inflight: set[str] = set()
        self._center_tap_pending: dict[str, tuple[float, float, str]] = {}
        self._center_tap_token: dict[str, int] = {}
        self._ui_busy = ""
        self._sky_target: Target | None = None
        self._web_view_available = _webview_available()
        self._sky_web_blocked_by_gpu = _sky_web_blocked_by_gpu()
        self._stellarium_rc_live = False
        self._stellarium_rc_watch = False
        self._stellarium_rc_inflight = False
        self._stellarium_rc_timer = QTimer(self)
        self._stellarium_rc_timer.setInterval(4000)
        self._stellarium_rc_timer.timeout.connect(self._poll_stellarium_rc)
        self._location_lookup_busy = False
        self._device_discovery_busy = False
        self._device_discovery_token = 0
        self._asyncResult.connect(self._handle_async_result)
        self._sync_shared_device_fields()
        for device in self._devices:
            self._create_worker(device)
        recovered = self.store.recover_running()
        if recovered:
            self._recovered_sessions = {item.id: item.device_id for item in recovered}
            self.add_log("warning", f"Recovered {len(recovered)} interrupted session(s)")
        self._sequence_colliding_mosaics()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self.live_images = LiveFrames(self)
        set_live_frames(self.live_images)
        self.mosaic_frames = MosaicFrames(self)
        set_mosaic_frames(self.mosaic_frames)
        self._mosaic_pane_urls: dict[str, str] = {}
        self._mosaic_firmware_pane = 1
        self._mosaic_firmware_stacked = 0
        self._preview_token = 0
        self._preview_active = False
        self._preview_playing = False
        self._preview_tele_playing = False
        self._preview_wide_playing = False
        self._preview_status = ""
        self._last_preview_ui: dict[str, float] = {}
        self._preview_window = None
        self._preview_window_filter = None
        self._preview_hold_device_id = ""
        self._preview_hold_target = ""
        self._preview_tele_url = ""
        self._preview_wide_url = ""
        self._preview_stack_mode = False
        self._preview_result = False
        self._preview_result_title = ""
        self._preview_result_detail = ""
        self._enhance_images = True
        self._deep_clean_images = False
        self._enhance_denoise = 1.0
        self._enhance_sky_crush = 1.0
        self._raw_preview_images = {"tele": QImage(), "wide": QImage()}
        self._enhance_job_token = {"tele": 0, "wide": 0}
        self._enhance_pool = QThreadPool(self)
        self._enhance_pool.setMaxThreadCount(1)
        self._enhance_cache_pool = QThreadPool(self)
        self._enhance_cache_pool.setMaxThreadCount(1)
        self._preview_enhance_signals = PreviewEnhanceSignals(self)
        self._preview_enhance_signals.finished.connect(self._on_preview_enhanced)
        self._enhance_cache_rev = 0
        self._enhance_inflight: set[str] = set()
        self._enhance_failed: set[str] = set()
        self._cache_enhance_signals = CacheEnhanceSignals(self)
        self._cache_enhance_signals.finished.connect(self._on_enhance_cache_ready)
        self._shut_down = False
        self._preview_thread = QThread(self)
        self._tele_player = StreamPlayer()
        self._wide_player = StreamPlayer()
        self._tele_player.moveToThread(self._preview_thread)
        self._wide_player.moveToThread(self._preview_thread)
        self._tele_player.frameReady.connect(self._on_tele_frame)
        self._wide_player.frameReady.connect(self._on_wide_frame)
        self._tele_player.failed.connect(self._on_tele_failed)
        self._wide_player.failed.connect(self._on_wide_failed)
        self._tele_player.statusChanged.connect(self._on_tele_status)
        self._wide_player.statusChanged.connect(self._on_wide_status)
        self._openTeleStream.connect(self._tele_player.openStream, Qt.QueuedConnection)
        self._openWideStream.connect(self._wide_player.openStream, Qt.QueuedConnection)
        self._closeWideStream.connect(self._wide_player.closeStream, Qt.QueuedConnection)
        self._closePreviewStreams.connect(self._tele_player.closeStream, Qt.QueuedConnection)
        self._closePreviewStreams.connect(self._wide_player.closeStream, Qt.QueuedConnection)
        self._previewReady.connect(self._open_ready_stream)
        self._preview_thread.start()
        self._window_frame_hook = None
        self._pending_window_frame = None

    def _create_worker(self, device: Device, reconnect: bool = False) -> TelescopeProcess:
        old = self._workers.pop(device.id, None)
        self._release_worker(old)
        worker = TelescopeProcess(device, self)
        worker.logReceived.connect(lambda level, message, did=device.id: self.add_log(level, message, did))
        worker.telemetryReceived.connect(lambda data, did=device.id: self._on_telemetry(did, data))
        worker.progressReceived.connect(self._session_progress)
        worker.statusReceived.connect(lambda kind, step, did=device.id: self._on_worker_status(did, kind, step))
        worker.availabilityChanged.connect(self._worker_status_changed)
        self._workers[device.id] = worker
        worker.start()
        if reconnect:
            self._pending_reconnect_ids.add(device.id)

            def on_ready() -> None:
                try:
                    worker.availabilityChanged.disconnect(on_ready)
                except RuntimeError:
                    self._pending_reconnect_ids.discard(device.id)
                    return
                self._pending_reconnect_ids.discard(device.id)
                if worker.configured and not worker.connected:
                    self.connectDevice(device.id)
                else:
                    self._disarm_scheduler_if_offline()

            worker.availabilityChanged.connect(on_ready)
        return worker

    def _release_worker(self, worker: TelescopeProcess | None) -> None:
        if worker is None:
            return
        for signal in (
            worker.logReceived,
            worker.telemetryReceived,
            worker.progressReceived,
            worker.statusReceived,
            worker.availabilityChanged,
        ):
            try:
                signal.disconnect()
            except (RuntimeError, TypeError):
                pass
        worker.shutdown()
        worker.deleteLater()

    def _worker_status_changed(self) -> None:
        selected_offline = False
        for device_id, worker in self._workers.items():
            if worker.connected:
                continue
            if device_id == self._selected_device_id:
                selected_offline = True
            self._pending_actions.pop(device_id, None)
            self._pending_details.pop(device_id, None)
            self._device_activity.pop(device_id, None)
            self._device_telemetry.pop(device_id, None)
            self._telemetry_updated.pop(device_id, None)
            self._hold_session_capture.discard(device_id)
            self._pending_session_finish.pop(device_id, None)
        if selected_offline:
            self.stopPreview()
            if self._media_source != "local" and self._album_busy == "list":
                self._clear_media(self._media_offline_status(self._selected_device_id))
        self._disarm_scheduler_if_offline()
        self._notify_devices()

    def _drop_device_link(self, device_id: str) -> None:
        """Mark the telescope offline so live video and commands stop with it."""
        worker = self._workers.get(device_id)
        if worker:
            worker.busy = False
            if worker.connected:
                worker.connected = False
                worker.availabilityChanged.emit()
                return
        if device_id == self._selected_device_id:
            self.stopPreview()
        self._disarm_scheduler_if_offline()
        self._notify_devices()

    def _invalidate_session_views(self) -> None:
        self._sessions_view = None
        self._upcoming_sessions_view = None
        self._current_session_view = None

    def _emit_sessions_changed(self) -> None:
        self._invalidate_session_views()
        sessions_changed = self.sessionsChanged
        sessions_changed.emit()
        self.currentSessionChanged.emit()

    def _refresh_selected_session_views(self) -> None:
        self._upcoming_sessions_view = None
        self._current_session_view = None
        sessions_changed = self.sessionsChanged
        sessions_changed.emit()
        self.currentSessionChanged.emit()

    def _rebuild_sessions_view(self) -> None:
        items = self._decorate_session_groups([
            self._session_dict(session)
            for session in sorted(
                self.store.sessions.all(),
                key=lambda item: (item.scheduled_start, pane_sort_key(item.name), item.name),
            )
        ])
        self._sessions_view = items
        self._refresh_session_derived()

    def _refresh_session_derived(self) -> None:
        items = self._sessions_view or []
        session_id = self._active_sessions.get(self._selected_device_id)
        if session_id:
            self._current_session_view = next((item for item in items if item["id"] == session_id), {})
        else:
            self._current_session_view = {}
        self._upcoming_sessions_view = [
            item for item in items
            if item["status"] == SessionStatus.PLANNED and item["device_id"] == self._selected_device_id
        ][:8]

    def _ensure_sessions_view(self) -> list[dict[str, Any]]:
        if self._sessions_view is None:
            self._rebuild_sessions_view()
        assert self._sessions_view is not None
        if self._current_session_view is None or self._upcoming_sessions_view is None:
            self._refresh_session_derived()
        return self._sessions_view

    def _apply_session_step(self, session: Session, step: str) -> Session:
        updated = replace(session, current_step=step)
        self.store.sessions.save(updated)
        timing = self._session_timing.get(updated.id) or {}
        started_at = float(timing.get("step_started_at") or 0)
        wait_seconds = float(timing.get("step_wait_seconds") or 0)
        if self._sessions_view:
            for item in self._sessions_view:
                if item.get("id") == updated.id:
                    item["current_step"] = step
                    item["step_started_at"] = started_at
                    item["step_wait_seconds"] = wait_seconds
                    break
        if self._current_session_view and self._current_session_view.get("id") == updated.id:
            self._current_session_view["current_step"] = step
            self._current_session_view["step_started_at"] = started_at
            self._current_session_view["step_wait_seconds"] = wait_seconds
        elif self._active_sessions.get(self._selected_device_id) == updated.id:
            self._current_session_view = None
        self._sync_session_activity(updated.device_id, step)
        self.currentSessionChanged.emit()
        self.sessionProgressChanged.emit()
        return updated

    def _rebuild_devices_view(self) -> None:
        result = []
        now = time.time()
        for device in self._devices:
            worker = self._workers.get(device.id)
            data = to_dict(device)
            connecting = device.id in self._connecting_ids
            cancelling = device.id in self._cancel_connect_ids
            disconnecting = device.id in self._disconnecting_ids
            if cancelling:
                status = "Cancelling"
            elif connecting:
                status = "Connecting"
            elif disconnecting:
                status = "Disconnecting"
            elif worker and worker.busy:
                status = "Imaging"
            elif worker and worker.connected:
                status = "Connected"
            else:
                status = "Offline"
            connected = bool(worker and worker.connected)
            raw_view = dict(self._device_telemetry.get(device.id, {}) if connected else {})
            apply_camera_fov_defaults(raw_view, device.model)
            telemetry = format_telemetry(
                raw_view,
                self._telemetry_updated.get(device.id) if connected else None,
                now,
            )
            activity = self._hud_activity(device.id, telemetry.get("activity") or "")
            if not activity:
                session_id = self._active_sessions.get(device.id)
                session = self.store.sessions.get(session_id) if session_id else None
                if session:
                    activity = _activity_for_session_step(session.current_step)
            raw_telemetry = self._device_telemetry.get(device.id, {})
            if not connected:
                lights_on = False
                indicator_on = False
            elif "lights_on" in raw_telemetry:
                lights_on = bool(raw_telemetry["lights_on"])
                indicator_on = bool(raw_telemetry.get("indicator_on", self._device_indicators.get(device.id, False)))
            else:
                lights_on = self._device_lights.get(device.id, False)
                indicator_on = self._device_indicators.get(device.id, False)
            data.update({
                "connected": connected,
                "busy": bool(worker and worker.busy),
                "connecting": connecting,
                "cancelling": cancelling,
                "disconnecting": disconnecting,
                "pending_action": self._pending_actions.get(device.id, ""),
                "pending_detail": self._pending_details.get(device.id, ""),
                "activity": activity,
                "activity_detail": telemetry["activity_detail"],
                "activity_from_device": bool(telemetry["activity"]),
                "status": status,
                "lights_on": lights_on,
                "indicator_on": indicator_on,
                "telemetry": telemetry,
            })
            result.append(data)
        self._devices_view = result
        selected = next((item for item in result if item["id"] == self._selected_device_id), None)
        self._selected_device_view = selected if selected is not None else (result[0] if result else {})
        self._devices_dirty = False

    def _flush_devices_notify(self) -> None:
        if self._devices_dirty or self._devices_view is None:
            self._rebuild_devices_view()
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()
        self.statusChanged.emit()

    def _notify_devices(self, immediate: bool = True) -> None:
        self._devices_dirty = True
        if immediate:
            self._devices_notify_timer.stop()
            self._flush_devices_notify()
            return
        if not self._devices_notify_timer.isActive():
            self._devices_notify_timer.start()

    def _on_telemetry(self, device_id: str, data: dict[str, Any]) -> None:
        """Merge a telemetry delta from the worker and raise transition alerts."""
        if not isinstance(data, dict) or not data:
            return
        data = dict(data)
        if device_id in self._hold_session_capture:
            # Firmware often never sends a 0/0 reset — the first packet is
            # stacked=1. Release as soon as this session's capture starts.
            starting = (
                data.get("capture_active") is True
                or data.get("capture_state") == "running"
                or "capture_current" in data
                or "capture_stacked" in data
            )
            if starting:
                self._hold_session_capture.discard(device_id)
            else:
                for key in ("capture_current", "capture_stacked", "capture_active", "capture_state", "mosaic_active"):
                    if key == "capture_state" and data.get(key) in ("idle", "stopped"):
                        continue
                    if key == "capture_active" and data.get(key) is False:
                        continue
                    data.pop(key, None)
                if not data:
                    self._sync_preview_for_capture(
                        device_id,
                        dict(self._device_telemetry.get(device_id) or {}),
                        dict(self._device_telemetry.get(device_id) or {}),
                    )
                    return
        previous = dict(self._device_telemetry.get(device_id, {}))
        current = dict(previous)
        current.update(data)
        self._device_telemetry[device_id] = current
        self._telemetry_updated[device_id] = time.time()
        if "tele_match_width" in data:
            self._finish_center_tap(device_id)
        if "lights_on" in data:
            self._device_lights[device_id] = bool(data["lights_on"])
        if "indicator_on" in data:
            self._device_indicators[device_id] = bool(data["indicator_on"])
        for alert in self._alerts.evaluate(previous, current):
            self.add_log(alert["level"], alert["message"] + (f" — {alert['detail']}" if alert["detail"] else ""), device_id)
            if alert["toast"]:
                self._toast(alert["message"], alert["level"], alert["detail"])
        activity, _detail = derive_activity(current)
        if activity:
            # Infinity uses the same autofocus_state as AUTO FOCUS. Keep the
            # pad that started the move so Stop stays on INFINITY.
            if not (activity == "autofocus" and self._device_activity.get(device_id) == "infinity"):
                self._device_activity[device_id] = activity
        elif previous and derive_activity(previous)[0]:
            self._device_activity.pop(device_id, None)
            session_id = self._active_sessions.get(device_id)
            session = self.store.sessions.get(session_id) if session_id else None
            if session:
                wanted = _activity_for_session_step(session.current_step)
                if wanted:
                    self._device_activity[device_id] = wanted
        # Photo AF often reports idle without a prior running sample. Drop the
        # AUTO FOCUS latch from _begin_activity when firmware says it is done.
        if (
            data.get("autofocus_state") in ("idle", "stopped")
            and self._device_activity.get(device_id) in ("autofocus", "infinity")
            and not activity
        ):
            session_id = self._active_sessions.get(device_id)
            session = self.store.sessions.get(session_id) if session_id else None
            wanted = _activity_for_session_step(session.current_step) if session else ""
            if wanted not in ("autofocus", "infinity"):
                self._device_activity.pop(device_id, None)
        if data.get("power_off"):
            self._drop_device_link(device_id)
            return
        self._track_session_capture(device_id, current)
        self._maybe_resume_held_preview(device_id)
        self._maybe_resume_interrupted_session(device_id)
        self._sync_preview_for_capture(device_id, previous, current)
        self._sync_mosaic_preview(device_id, previous)
        self._notify_devices(immediate=False)
        self._sync_media_lock()

    def _toast(self, message: str, level: str = "info", detail: str = "", meta: dict | None = None) -> None:
        """Emit a toast, collapsing identical messages fired within two seconds."""
        text = str(message or "").strip()
        if not text:
            return
        level = str(level or "info").lower()
        now = time.monotonic()
        last_text, last_level, last_at = self._last_toast
        if text == last_text and level == last_level and now - last_at < 2.0:
            return
        self._last_toast = (text, level, now)
        self.toast.emit(text, level, str(detail or ""), dict(meta or {}))

    def _toast_templates(self, message: str, template_ids: list[str] | tuple[str, ...]) -> None:
        ids = [str(item).strip() for item in template_ids if str(item).strip()]
        label = "VIEW TEMPLATE" if len(ids) <= 1 else "VIEW TEMPLATES"
        self._toast(message, "success", "", {"kind": "template", "ids": ids, "link": label})

    def _set_activity(self, device_id: str, activity: str) -> None:
        current = self._device_activity.get(device_id, "")
        if activity:
            if current == activity:
                return
            self._device_activity[device_id] = activity
        elif current:
            self._device_activity.pop(device_id, None)
        else:
            return
        self._notify_devices()

    def _sync_session_activity(self, device_id: str, step: str) -> None:
        """Light session command pads when the telescope does not report the action."""
        if derive_activity(self._device_telemetry.get(device_id, {}))[0]:
            return
        wanted = _activity_for_session_step(step)
        current = self._device_activity.get(device_id, "")
        if wanted:
            self._set_activity(device_id, wanted)
            return
        if current in _SESSION_STEP_ACTIVITIES:
            self._set_activity(device_id, "")

    def _hud_activity(self, device_id: str, telemetry_activity: str) -> str:
        stored = self._device_activity.get(device_id, "")
        if telemetry_activity == "autofocus" and stored == "infinity":
            return "infinity"
        return telemetry_activity or stored

    def _begin_activity(self, device_id: str, operation: str) -> None:
        if operation in _ACTIVITY_CLEAR:
            self._set_activity(device_id, "")
            return
        mode = _ACTIVITY_START.get(operation)
        if mode:
            self._set_activity(device_id, mode)

    def _complete_activity(self, device_id: str, operation: str, ok: bool) -> None:
        if operation in _ACTIVITY_CLEAR:
            self._set_activity(device_id, "")
            return
        expected = _ACTIVITY_STOP.get(operation)
        if expected:
            current = self._device_activity.get(device_id)
            aliases = ("autofocus", "infinity") if expected == "autofocus" else (expected,)
            if ok and current in aliases:
                self._set_activity(device_id, "")
            return
        mode = _ACTIVITY_START.get(operation)
        if mode and (not ok or mode in _ACTIVITY_TRANSIENT) and self._device_activity.get(device_id) == mode:
            self._set_activity(device_id, "")

    def _set_pending_action(self, device_id: str, action: str) -> None:
        current = self._pending_actions.get(device_id, "")
        if action:
            if current == action:
                return
            self._pending_actions[device_id] = action
            if action not in _STOP_ACTIONS:
                self._pending_details.pop(device_id, None)
        elif current:
            self._pending_actions.pop(device_id, None)
            self._pending_details.pop(device_id, None)
        else:
            return
        self._notify_devices()

    def _set_pending_detail(self, device_id: str, detail: str) -> None:
        text = str(detail or "").strip()
        current = self._pending_details.get(device_id, "")
        if text:
            if current == text:
                return
            self._pending_details[device_id] = text
        elif current:
            self._pending_details.pop(device_id, None)
        else:
            return
        self._notify_devices()

    def _on_worker_status(self, device_id: str, kind: str, step: str) -> None:
        if kind != "stop" or self._pending_actions.get(device_id) not in _STOP_ACTIONS:
            return
        self._set_pending_detail(device_id, step)

    def _initial_stop_detail(self, device_id: str) -> str:
        session_id = self._active_sessions.get(device_id)
        session = self.store.sessions.get(session_id) if session_id else None
        telemetry = self._device_telemetry.get(device_id, {})
        target = str(telemetry.get("capture_target") or telemetry.get("tracking_target") or "")
        if session and session.target.name:
            target = target or session.target.name
        if telemetry.get("capture_active"):
            return f"Stopping capture{f' · {target}' if target else ''}"
        if session:
            step = str(session.current_step or "").strip()
            name = session.target.name if session else "session"
            if step and step not in {"Waiting", "Starting worker", "Stopping"}:
                return f"Stopping {step.lower()} · {name}"
            return f"Stopping session · {name}"
        activity = self._device_activity.get(device_id) or ""
        if activity:
            return f"Stopping {activity.replace('_', ' ')}"
        return "Stopping telescope activity"

    def _with_pending(self, device_id: str, action: str, callback: Callable[[bool, Any], None] | None = None) -> Callable[[bool, Any], None]:
        self._set_pending_action(device_id, action)

        def done(ok: bool, result: Any) -> None:
            self._set_pending_action(device_id, "")
            if callback:
                callback(ok, result)

        return done

    def add_log(self, level: str, message: str, device_id: str = "") -> None:
        text = str(message or "").strip()
        if not text:
            return
        device = next((d.name for d in self._devices if d.id == device_id), "System")
        level_name = str(level or "info").upper()
        if level_name not in _LOG_GLYPHS:
            level_name = "INFO"
        category = "device" if device_id else "app"
        if level_name in ("SDK", "DEBUG"):
            category = "sdk"
        self._log_model.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level_name,
            "device": device,
            "message": text,
            "category": category,
        })

    @Property(str, constant=True)
    def appVersion(self) -> str:
        return __version__

    @Property("QVariantList", constant=True)
    def timezones(self) -> list[dict[str, Any]]:
        return list(timezone_locations())

    @Property("QVariant", constant=True)
    def suggestedLocation(self) -> dict[str, Any]:
        return suggested_timezone() or {}

    @Property("QVariantList", constant=True)
    def deviceColorPresets(self) -> list[str]:
        return list(DEVICE_COLORS)

    @Property("QVariantList", notify=devicesChanged)
    def devices(self) -> list[dict[str, Any]]:
        if self._devices_dirty or self._devices_view is None:
            self._rebuild_devices_view()
        return self._devices_view or []

    @Property(str, notify=selectedDeviceChanged)
    def selectedDeviceId(self) -> str:
        return self._selected_device_id

    @Property("QVariantMap", notify=selectedDeviceChanged)
    def selectedDevice(self) -> dict[str, Any]:
        if self._devices_dirty or self._selected_device_view is None:
            self._rebuild_devices_view()
        return self._selected_device_view or {}

    def _needs_first_device(self) -> bool:
        return is_first_device_setup(self._devices)

    @Property(bool, notify=devicesChanged)
    def needsFirstDevice(self) -> bool:
        return self._needs_first_device()

    def _session_dict(self, session: Session) -> dict[str, Any]:
        device = next((item for item in self._devices if item.id == session.device_id), None)
        data = to_dict(session)
        start = parse_in_zone(session.scheduled_start, self._zone_for(device))
        planned = max(0.0, float(session.planned_duration_seconds or 0))
        if device and planned <= 0:
            planned = max(0.0, float(DurationEngine.calculate(session, device.hardware)))
        finish = start + timedelta(seconds=planned)
        actual_seconds = 0.0
        if session.actual_started_at and session.actual_ended_at:
            try:
                actual_seconds = max(
                    0.0,
                    (
                        datetime.fromisoformat(session.actual_ended_at)
                        - datetime.fromisoformat(session.actual_started_at)
                    ).total_seconds(),
                )
            except ValueError:
                actual_seconds = 0.0
        data["device_name"] = device.name if device else "Unknown"
        data["device_color"] = device.color if device else "#4DE8FF"
        data["target_name"] = session.target.name
        data["scheduled_start"] = store_local_iso(start, start.tzinfo or self._zone_for(device))
        data["start_date"] = start.date().isoformat()
        data["start_time"] = start.strftime("%H:%M")
        data["end_time"] = store_local_iso(finish, start.tzinfo or self._zone_for(device))
        data["start_epoch_ms"] = int(start.timestamp() * 1000)
        data["end_epoch_ms"] = int(finish.timestamp() * 1000)
        data["planned_duration_seconds"] = planned
        data["actual_duration_seconds"] = actual_seconds
        data["duration_text"] = self._duration_text(planned)
        data["summary"] = f"{session.camera.frame_count} × {session.camera.exposure_seconds:g}s"
        group_id = session.mosaic.group_id or ""
        data["group_id"] = group_id
        data["group_title"] = mosaic_group_title(session.target.name, group_id)
        data["display_title"] = data["group_title"]
        data["grid_text"] = session.mosaic.grid_text
        data["subtitle"] = session.name if session.name != session.target.name else data["summary"]
        data["observing_date"] = observing_date(
            session.scheduled_start,
            self._cutoff_hour(),
            self._zone_for(device),
        )
        data["pane_index"] = pane_sort_key(session.name)[0]
        data["pane_name"] = session.name
        data["pane_position"] = session.mosaic.position_text
        timing = self._session_timing.get(session.id) or {}
        data["step_started_at"] = float(timing.get("step_started_at") or 0)
        data["step_wait_seconds"] = float(timing.get("step_wait_seconds") or 0)
        return data

    def _decorate_session_groups(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[tuple[str, str], int] = {}
        for item in items:
            group_id = item.get("group_id") or ""
            if not group_id:
                continue
            key = (group_id, item.get("device_id") or "")
            counts[key] = counts.get(key, 0) + 1
        for item in items:
            group_id = item.get("group_id") or ""
            device_id = item.get("device_id") or ""
            pane_count = counts.get((group_id, device_id), 1) if group_id else 1
            grouped = pane_count > 1
            item["pane_count"] = pane_count
            item["is_grouped"] = grouped
            item["group_key"] = f"{group_id}|{device_id}" if grouped else f"session:{item.get('id', '')}"
        return items

    @Property("QVariantList", notify=sessionsChanged)
    def sessions(self) -> list[dict[str, Any]]:
        return self._ensure_sessions_view()

    def _template_dict(self, template: SessionTemplate, members: list[SessionTemplate] | None = None) -> dict[str, Any]:
        members = members or [template]
        first = sorted(members, key=lambda item: pane_sort_key(item.name))[0]
        data = to_dict(first)
        group_id = first.mosaic.group_id or ""
        grouped = len(members) > 1
        title = mosaic_group_title(first.name, group_id) if grouped else first.name
        ordered = sorted(members, key=lambda item: pane_sort_key(item.name))
        data["id"] = first.id
        data["group_id"] = group_id
        data["is_group"] = grouped
        data["pane_count"] = len(members)
        data["pane_name"] = first.name
        data["name"] = title
        data["target_name"] = mosaic_group_title(first.target.name, group_id) if grouped else first.target.name
        data["member_ids"] = [item.id for item in ordered]
        data["members"] = [self._template_member_dict(item) for item in ordered]
        data["grid_text"] = first.mosaic.grid_text
        exposure = f"{first.camera.frame_count} × {first.camera.exposure_seconds:g}s"
        if grouped:
            grid = f"{first.mosaic.grid_text} · " if first.mosaic.grid_text else ""
            data["summary"] = f"{len(members)} panes · {grid}{exposure}"
        else:
            data["summary"] = f"{exposure} · {first.mosaic.rows}×{first.mosaic.columns}"
        data.update(self._template_detail_fields(first, ordered))
        return data

    def _template_detail_fields(self, first: SessionTemplate, members: list[SessionTemplate]) -> dict[str, Any]:
        cam = first.camera
        mosaic = first.mosaic
        target = first.target
        workflow = first.workflow
        ir = str(cam.ir_filter or "VIS").replace(" Filter", "").upper()
        camera_bits = ["WIDE" if cam.camera == Camera.WIDE else "TELE"]
        camera_bits.append("2K" if int(cam.binning or 1) >= 2 else "4K")
        if cam.camera != Camera.WIDE and ir:
            camera_bits.append(ir)
        steps: list[str] = []
        if workflow.calibrate or workflow.polar_align:
            steps.append("POS")
        if workflow.calibrate:
            steps.append("CAL")
        if workflow.autofocus:
            steps.append("AF")
        elif workflow.infinite_focus:
            steps.append("INF")
        if workflow.polar_align:
            steps.append("POLAR")
        if workflow.goto:
            steps.append("GOTO")
        if mosaic.imported_plan or len(members) > 1:
            mosaic_text = f"{len(members)} pane" + ("" if len(members) == 1 else "s")
            if mosaic.grid_text:
                mosaic_text += f" · {mosaic.grid_text}"
        elif mosaic.rows > 1 or mosaic.columns > 1:
            mosaic_text = f"{mosaic.rows}×{mosaic.columns}"
            if mosaic.rotation_degrees:
                mosaic_text += f" · {mosaic.rotation_degrees:g}°"
        else:
            mosaic_text = "Single pane"
        if target.kind == TargetKind.EQUATORIAL and target.ra_hours is not None and target.dec_degrees is not None:
            coords = f"RA {float(target.ra_hours):.3f}h  DEC {float(target.dec_degrees):+.3f}°"
        elif target.kind == TargetKind.SOLAR:
            coords = target.solar_name or target.name or "Solar"
        else:
            coords = ""
        seconds = 0.0
        profile = HardwareProfile()
        for index, item in enumerate(members):
            timed = replace(item, workflow=mosaic_pane_workflow(item.workflow, index))
            seconds += DurationEngine.calculate(timed, profile)
        return {
            "capture_text": f"{cam.frame_count} × {cam.exposure_seconds:g}s",
            "gain_text": f"G{cam.gain}",
            "camera_text": " · ".join(camera_bits),
            "mosaic_text": mosaic_text,
            "workflow_text": " · ".join(steps) if steps else "Capture only",
            "coords_text": coords,
            "duration_text": self._duration_text(seconds),
            "duration_seconds": seconds,
        }

    def _template_member_dict(self, template: SessionTemplate) -> dict[str, Any]:
        data = to_dict(template)
        data["pane_name"] = template.name
        data["pane_position"] = template.mosaic.position_text
        return data

    @Property("QVariantList", notify=templatesChanged)
    def templates(self) -> list[dict[str, Any]]:
        grouped: dict[str, list[SessionTemplate]] = {}
        singles: list[SessionTemplate] = []
        for template in self.store.templates.all():
            group_id = template.mosaic.group_id
            if group_id:
                grouped.setdefault(group_id, []).append(template)
            else:
                singles.append(template)
        result = [self._template_dict(members[0], members) for members in grouped.values()]
        result.extend(self._template_dict(template) for template in singles)
        result.sort(key=lambda item: item["name"].lower())
        return result

    @Slot(str, result="QVariantList")
    def sessionPanes(self, session_id: str) -> list[dict[str, Any]]:
        session = self.store.sessions.get(session_id)
        if not session:
            return []
        siblings = sorted(self._mosaic_siblings(session), key=lambda item: pane_sort_key(item.name))
        if len(siblings) < 2:
            return []
        return [self._session_dict(item) for item in siblings]

    @Property("QVariantList", notify=historyChanged)
    def history(self) -> list[dict[str, Any]]:
        result = []
        device_by_id = {device.id: device for device in self._devices}
        for record in sorted(self.store.history.all(), key=lambda item: item.recorded_at, reverse=True):
            session = self.store.sessions.get(record.session_id)
            data = to_dict(record)
            device = device_by_id.get(record.device_id)
            data["device_name"] = device.name if device else "Unknown"
            data["device_color"] = device.color if device else "#4DE8FF"
            data["date"] = self._history_date(record.scheduled_start, device)
            data["planned_text"] = self._duration_text(record.planned_duration_seconds)
            data["actual_text"] = self._duration_text(record.actual_duration_seconds)
            data["ok"] = str(record.outcome).strip().lower() == "completed"
            planned_frames = int(record.frame_count or 0)
            captured = record.captured_frame_count
            if captured is None:
                captured = planned_frames if data["ok"] else 0
            data["planned_frames"] = planned_frames
            data["captured_frames"] = int(captured)
            data["frame_text"] = f"{int(captured)}/{planned_frames}"
            data["scheduled_text"] = self._stamp_text(record.scheduled_start, device)
            data["started_text"] = self._stamp_text(record.actual_started_at, device)
            data["ended_text"] = self._stamp_text(record.actual_ended_at, device)
            data["has_session"] = session is not None
            if not data.get("summary") and session:
                data["summary"] = f"{session.camera.frame_count} × {session.camera.exposure_seconds:g}s"
            if not data.get("notes") and session:
                data["notes"] = session.notes
            delta = record.actual_duration_seconds - record.planned_duration_seconds
            data["delta_seconds"] = delta
            if abs(delta) < 1:
                data["delta_text"] = "On plan"
            elif delta > 0:
                data["delta_text"] = self._duration_text(delta) + " over"
            else:
                data["delta_text"] = self._duration_text(-delta) + " under"
            steps = []
            for name, seconds in (record.step_seconds or {}).items():
                if float(seconds) < 1:
                    continue
                steps.append(f"{name} {self._duration_text(seconds)}")
            data["step_text"] = " · ".join(steps)
            result.append(data)
        return result

    @Property("QVariantMap", notify=durationSuggestionChanged)
    def durationSuggestion(self) -> dict[str, Any]:
        device = next((item for item in self._devices if item.id == self._selected_device_id), None)
        if not device:
            return {"available": False, "run_count": 0, "changes": [], "summary": "", "note": "", "change_text": ""}
        sessions = {item.id: item for item in self.store.sessions.all()}
        hint = suggest_hardware_profile(
            self.store.history.all(),
            device.hardware,
            sessions,
            device.id,
        )
        if hint.get("available") and hint.get("summary"):
            hint["summary"] = f"{device.name}: {hint['summary']}"
        return hint

    @Slot()
    def applyDurationSuggestion(self) -> None:
        suggestion = self.durationSuggestion
        if not suggestion.get("available"):
            return
        device = self._device_by_id(self._selected_device_id)
        updates = {}
        for change in suggestion.get("changes") or []:
            key = str(change.get("key") or "")
            if key in device.hardware.__dataclass_fields__:
                updates[key] = float(change["suggested"])
        if not updates:
            return
        updated = replace(device, hardware=replace(device.hardware, **updates))
        self.store.devices.save(updated)
        self._devices = [updated if item.id == updated.id else item for item in self._devices]
        for session in self.store.upcoming(updated.id):
            self._save_session(replace(
                session,
                planned_duration_seconds=DurationEngine.calculate(session, updated.hardware),
            ), notify=False)
        self._sequence_colliding_mosaics()
        self._notify_devices()
        self.clockChanged.emit()
        self._emit_sessions_changed()
        self.durationSuggestionChanged.emit()
        self._toast("Duration profile updated from history", "success")

    @Property(str, notify=logFilterChanged)
    def logFilter(self) -> str:
        return self._log_model.filter_name

    @Slot(str)
    def setLogFilter(self, name: str) -> None:
        self._log_model.set_filter(str(name or "all"))
        self.logFilterChanged.emit()

    @Property(int, notify=logCountsChanged)
    def logWarningCount(self) -> int:
        return self._log_model.warning_count()

    @Property(int, notify=logCountsChanged)
    def logErrorCount(self) -> int:
        return self._log_model.error_count()

    @Slot()
    def clearLog(self) -> None:
        self._log_model.clear()

    @Property(QObject, constant=True)
    def logModel(self) -> LogListModel:
        return self._log_model

    @Property(QObject, constant=True)
    def screenColor(self) -> ScreenColorPicker:
        return self._screen_color

    @Slot(result=str)
    def allLogText(self) -> str:
        lines = []
        for entry in self._log_model.visible_entries():
            count = int(entry.get("count", 1))
            suffix = f"  (×{count})" if count > 1 else ""
            lines.append(f"{entry['time']}  {entry['level']:<8}[{entry['device']}]  {entry['message']}{suffix}")
        return "\n".join(lines)

    @Property("QVariantMap", notify=currentSessionChanged)
    def currentSession(self) -> dict[str, Any]:
        self._ensure_sessions_view()
        return self._current_session_view or {}

    @Property(str, notify=clockChanged)
    def clockText(self) -> str:
        return self._clock_text

    @Property("QVariantMap", notify=clockChanged)
    def localNow(self) -> dict[str, Any]:
        device = self._device_by_id(self._selected_device_id)
        tz = self._zone_for(device)
        now = datetime.now(tz)
        cutoff = self._cutoff_hour()
        observing = now - timedelta(days=1) if now.hour < cutoff else now
        return {
            "timezone": device.timezone_name if device else "UTC",
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M:%S"),
            "hour": now.hour,
            "minute": now.minute,
            "year": now.year,
            "month": now.month,
            "day": now.day,
            "epoch_ms": int(now.timestamp() * 1000),
            "observing_date": observing.date().isoformat(),
            "observing_year": observing.year,
            "observing_month": observing.month,
            "observing_day": observing.day,
        }

    @Property(int, notify=appSettingsChanged)
    def observingDayCutoffHour(self) -> int:
        return self._cutoff_hour()

    @Slot(int)
    def setObservingDayCutoffHour(self, hour: int) -> None:
        hour = clamp_cutoff_hour(hour)
        if hour == self._settings.observing_day_cutoff_hour:
            return
        self._settings = replace(self._settings, observing_day_cutoff_hour=hour)
        self._persist_app_settings()

    @Property(str, notify=appSettingsChanged)
    def stellariumUrl(self) -> str:
        return self._settings.stellarium_url

    @Slot(str)
    def setStellariumUrl(self, url: str) -> None:
        url = normalized_stellarium_url(url)
        if url == self._settings.stellarium_url:
            return
        self._settings = replace(self._settings, stellarium_url=url)
        self._persist_app_settings()
        self._poll_stellarium_rc()

    @Property(bool, notify=stellariumRcChanged)
    def stellariumRcLive(self) -> bool:
        return self._stellarium_rc_live

    @Slot(bool)
    def setStellariumRcWatch(self, enabled: bool) -> None:
        watching = bool(enabled)
        if watching == self._stellarium_rc_watch:
            if watching:
                self._poll_stellarium_rc()
            return
        self._stellarium_rc_watch = watching
        if watching:
            self._stellarium_rc_timer.start()
            self._poll_stellarium_rc()
            return
        self._stellarium_rc_timer.stop()
        self._set_stellarium_rc_live(False)

    def _set_stellarium_rc_live(self, live: bool) -> None:
        live = bool(live)
        if live == self._stellarium_rc_live:
            return
        self._stellarium_rc_live = live
        self.stellariumRcChanged.emit()

    def _poll_stellarium_rc(self) -> None:
        if not self._stellarium_rc_watch or self._stellarium_rc_inflight:
            return
        url = self._settings.stellarium_url
        self._stellarium_rc_inflight = True

        def work() -> None:
            try:
                live = StellariumClient(url).available()
            except Exception:
                live = False
            self._asyncResult.emit("stellariumRcPing", (True, live))

        threading.Thread(target=work, daemon=True).start()

    def _mosaic_south_up(self) -> bool:
        device = self._schedule_device()
        if device is None:
            return False
        return mosaic_south_up(device.latitude)

    @Property(bool, notify=selectedDeviceChanged)
    def mosaicSouthUp(self) -> bool:
        return self._mosaic_south_up()

    def _mosaic_pa(self) -> float:
        device = self._schedule_device()
        if device is None:
            return 0.0
        return device_mosaic_pa(device.latitude, device.mosaic_pa)

    @Property(float, notify=selectedDeviceChanged)
    def mosaicPa(self) -> float:
        return self._mosaic_pa()

    @Slot(float)
    def setMosaicPa(self, position_angle: float) -> None:
        device = self._schedule_device()
        if device is None:
            return
        pa = parse_mosaic_pa(position_angle)
        if pa is None:
            return
        if device.mosaic_pa is not None and abs(float(device.mosaic_pa) - pa) < 1e-6:
            return
        if not self._commit_device(device, replace(device, mosaic_pa=pa)):
            return
        self._notify_devices()

    @Property(bool, constant=True)
    def webViewAvailable(self) -> bool:
        return self._web_view_available

    @Property(bool, constant=True)
    def skyWebBlockedByGpu(self) -> bool:
        return self._sky_web_blocked_by_gpu

    @Property(str, constant=True)
    def stellariumWebUrl(self) -> str:
        return STELLARIUM_WEB_URL

    @Property(str, constant=True)
    def skyWebHarvestScript(self) -> str:
        return SKY_WEB_HARVEST_JS

    @Property(str, constant=True)
    def skyWebBootScript(self) -> str:
        return SKY_WEB_BOOT_JS

    @Property(str, constant=True)
    def skyWebContextPollScript(self) -> str:
        return SKY_WEB_CONTEXT_POLL_JS

    @Property(str, constant=True)
    def skyWebDblclickPollScript(self) -> str:
        return SKY_WEB_DBLCLICK_POLL_JS

    @Property(str, constant=True)
    def skyWebOpacityPollScript(self) -> str:
        return SKY_WEB_OPACITY_POLL_JS

    @Slot(str, bool, float, int, result=str)
    def skyWebLiveScript(self, data_url: str, enabled: bool, opacity: float = 0.65, live_pane: int = 0) -> str:
        return sky_web_live_script(data_url, enabled, opacity, live_pane)

    @Slot("QVariantMap", result=str)
    def skyWebPaneScript(self, pane_urls: Any = None) -> str:
        return sky_web_pane_script(pane_urls if isinstance(pane_urls, dict) else self._mosaic_pane_urls)

    def _sky_live_uses_stack_frame(self) -> bool:
        """Stacking preview and completed-stack result live in the tele slot."""
        if self._preview_stack_mode or self._preview_result:
            return True
        device_id = str(self._selected_device_id or "")
        return bool(device_id) and self._preview_stacking(device_id)

    @Slot(str, result=str)
    def skyLiveFrameDataUrl(self, camera: str = "") -> str:
        if self._sky_live_uses_stack_frame():
            return live_frame_data_url(self.live_images.peek("tele"))
        choice = str(camera or "").strip().lower()
        if choice not in ("tele", "wide"):
            _fov_h, _fov_v, choice = self._mosaic_fov()
        image = self.live_images.peek(choice)
        if image.isNull():
            other = "wide" if choice == "tele" else "tele"
            image = self.live_images.peek(other)
        return live_frame_data_url(image)

    @Property(str, notify=selectedDeviceChanged)
    def skyWebSiteScript(self) -> str:
        device = self._schedule_device()
        if device is None:
            return sky_web_site_script(0.0, 0.0, "UTC", "UTC")
        return sky_web_site_script(
            device.latitude,
            device.longitude,
            device.timezone_name,
            device.name,
        )

    @Property("QVariantMap", notify=skyTargetChanged)
    def skyTarget(self) -> dict[str, Any]:
        target = self._sky_target
        if target is None or target.ra_hours is None or target.dec_degrees is None:
            return {}
        return {
            "name": target.name,
            "ra_hours": float(target.ra_hours),
            "dec_degrees": float(target.dec_degrees),
            "locked": True,
        }

    def _set_sky_target(self, target: Target | None) -> None:
        self._sky_target = target
        self.skyTargetChanged.emit()

    def _device_fov(
        self, device_id: str = "", camera: Camera | str | None = None
    ) -> tuple[float, float, str]:
        device = self._schedule_device(device_id)
        if camera is None:
            camera = device.camera if device is not None else Camera.TELE
        choice = Camera.WIDE if str(getattr(camera, "value", camera) or "") == Camera.WIDE.value else Camera.TELE
        telemetry = self._device_telemetry.get(device.id if device is not None else "") or {}
        prefix = "wide" if choice == Camera.WIDE else "tele"
        try:
            fov_h = float(telemetry.get(f"{prefix}_fov_h") or 0)
            fov_v = float(telemetry.get(f"{prefix}_fov_v") or 0)
        except (TypeError, ValueError):
            fov_h = fov_v = 0.0
        if fov_h <= 0 or fov_v <= 0:
            model = device.model if device is not None else DeviceModel.DWARF_3
            fov_h, fov_v = camera_fov(model, choice)
        return fov_h, fov_v, choice.value

    def _mosaic_fov(self) -> tuple[float, float, str]:
        return self._device_fov()

    def _mosaic_group_sessions(self, device_id: str, group_id: str) -> list[Session]:
        if not group_id:
            return []
        return [
            item
            for item in self.store.sessions.values()
            if item.device_id == device_id and item.mosaic.group_id == group_id
        ]

    def _mosaic_context(self, device_id: str = "") -> tuple[Session | None, list[Session]]:
        owner = str(device_id or self._selected_device_id or "")
        session_id = self._active_sessions.get(owner)
        session = self.store.sessions.get(session_id) if session_id else None
        if session is None:
            view = self._current_session_view or {}
            if str(view.get("device_id") or "") == owner:
                session = self.store.sessions.get(str(view.get("id") or ""))
        if session is None:
            group = self.mosaic_frames.group()
            if group and not group.startswith("session:"):
                members = self._mosaic_group_sessions(owner, group)
                if members:
                    running = next((item for item in members if item.status == SessionStatus.RUNNING), None)
                    session = running or members[-1]
                    return session, members
            return None, []
        group_id = session.mosaic.group_id or ""
        members = self._mosaic_group_sessions(owner, group_id) if group_id else [session]
        return session, members

    def _mosaic_layout(self, session: Session | None, members: list[Session]) -> tuple[int, int, int, str]:
        if session is None:
            return 1, 1, 0, ""
        mosaics = [session.mosaic, *(item.mosaic for item in members)]
        rows, columns = mosaic_grid_size(*mosaics)
        index = mosaic_pane_number(session.mosaic, columns, session.name)
        if not session.mosaic.imported_plan and session.mosaic.panes > 1:
            index = max(1, min(session.mosaic.panes, int(self._mosaic_firmware_pane or 1)))
        group = session.mosaic.group_id or f"session:{session.id}"
        return columns, rows, index, group

    def _mosaic_is_active(self, session: Session | None, members: list[Session]) -> bool:
        if session is None:
            return False
        columns, rows, _index, _group = self._mosaic_layout(session, members)
        if columns <= 1 and rows <= 1:
            return False
        if session.status == SessionStatus.RUNNING:
            return True
        if any(item.status == SessionStatus.RUNNING for item in members):
            return True
        if self.mosaic_frames.indexes() and (
            self._preview_result
            or self._preview_stack_mode
            or any(item.status in {SessionStatus.DONE, SessionStatus.RUNNING} for item in members)
        ):
            return True
        return False

    def _snapshot_mosaic_pane(self, index: int) -> None:
        if index < 1:
            return
        image = self.live_images.peek("tele")
        if image.isNull():
            image = self.live_images.peek("wide")
        if image.isNull():
            return
        self._store_mosaic_pane_image(index, image)

    def _store_mosaic_pane_image(self, index: int, image: QImage) -> None:
        if index < 1 or image is None or image.isNull():
            return
        self.mosaic_frames.put(index, image)
        url = live_frame_data_url(self.mosaic_frames.peek(index))
        key = str(index)
        if url and self._mosaic_pane_urls.get(key) != url:
            self._mosaic_pane_urls[key] = url
            self.mosaicPreviewChanged.emit()

    def _clear_mosaic_preview(self) -> None:
        had = bool(self.mosaic_frames.indexes() or self._mosaic_pane_urls or self.mosaic_frames.group())
        self.mosaic_frames.clear()
        self._mosaic_pane_urls = {}
        self._mosaic_firmware_pane = 1
        self._mosaic_firmware_stacked = 0
        if had:
            self.mosaicPreviewChanged.emit()

    def _advance_firmware_mosaic_pane(self, previous: dict[str, Any], current: dict[str, Any], panes: int) -> int:
        reported = current.get("mosaic_index")
        try:
            if reported is not None and int(reported) >= 1:
                return max(1, min(panes, int(reported)))
        except (TypeError, ValueError):
            pass
        try:
            stacked = int(current.get("capture_stacked") or 0)
        except (TypeError, ValueError):
            stacked = 0
        try:
            previous_stacked = int(self._mosaic_firmware_stacked or previous.get("capture_stacked") or 0)
        except (TypeError, ValueError):
            previous_stacked = 0
        pane = max(1, min(panes, int(self._mosaic_firmware_pane or 1)))
        if previous_stacked >= 2 and stacked <= 1 and pane < panes:
            self._snapshot_mosaic_pane(pane)
            pane += 1
        self._mosaic_firmware_stacked = stacked
        return pane

    def _sync_mosaic_preview(self, device_id: str = "", previous: dict[str, Any] | None = None) -> None:
        owner = str(device_id or self._selected_device_id or "")
        if owner and owner != self._selected_device_id:
            return
        session, members = self._mosaic_context(owner)
        columns, rows, index, group = self._mosaic_layout(session, members)
        active = self._mosaic_is_active(session, members)
        if session is not None and not session.mosaic.imported_plan and session.mosaic.panes > 1:
            telemetry = self._device_telemetry.get(owner) or {}
            index = self._advance_firmware_mosaic_pane(previous or {}, telemetry, session.mosaic.panes)
            self._mosaic_firmware_pane = index
        stored = self.mosaic_frames.group()
        same_group = bool(stored) and stored == group
        if group and not same_group:
            self._mosaic_pane_urls = {}
            self._mosaic_firmware_pane = 1
            self._mosaic_firmware_stacked = 0
        if not active:
            if stored and not same_group:
                self._clear_mosaic_preview()
            elif stored:
                before = self.mosaic_frames.snapshot()[:4]
                self.mosaic_frames.set_layout(columns, rows, 0, False, stored)
                if before != self.mosaic_frames.snapshot()[:4]:
                    self.mosaicPreviewChanged.emit()
            return
        before = self.mosaic_frames.snapshot()
        self.mosaic_frames.set_layout(columns, rows, index, True, group)
        after = self.mosaic_frames.snapshot()
        if before[:4] != after[:4]:
            self.mosaicPreviewChanged.emit()

    @Property("QVariantMap", notify=mosaicPreviewChanged)
    def mosaicPreview(self) -> dict[str, Any]:
        active, columns, rows, current, images = self.mosaic_frames.snapshot()
        return {
            "active": active and (columns > 1 or rows > 1),
            "columns": columns,
            "rows": rows,
            "current_index": current,
            "live_pane": current if active else 0,
            "completed": sorted(images),
        }

    @Property("QVariantMap", notify=mosaicPreviewChanged)
    def skyMosaicPaneUrls(self) -> dict[str, str]:
        return dict(self._mosaic_pane_urls)

    @Property(str, notify=selectedDeviceChanged)
    def mosaicFovText(self) -> str:
        fov_h, fov_v, camera = self._mosaic_fov()
        return f"{camera.upper()} {fov_h:.2f}° × {fov_v:.2f}°"

    @Slot("QVariant", int, int, float, str, float, result=str)
    def skyWebFovScript(
        self, web_raw: Any, columns: int, rows: int, overlap: float, color: str, position_angle: float = 0.0
    ) -> str:
        fov_h, fov_v, camera = self._mosaic_fov()
        south_up = self._mosaic_south_up()
        payload: dict[str, Any] = {
            "color": str(color or "").strip() or "#7ee0d0",
            "label": f"{camera.upper()} {fov_h:.2f}° × {fov_v:.2f}°  PA {float(position_angle) % 360.0:.0f}°",
            "fov_h": fov_h,
            "fov_v": fov_v,
            "south_up": south_up,
            "position_angle": float(position_angle) % 360.0,
            "columns": 1,
            "rows": 1,
            "overlap": 0.0,
            "panes": [],
            "mode": "center",
        }
        target: Target | None
        try:
            target = parse_sky_web_target(self._snapshot_web_raw(web_raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            target = self._sky_target
        grid_ok = True
        try:
            columns_n = int(columns)
            rows_n = int(rows)
            overlap_n = float(overlap)
            grid_ok = columns_n >= 1 and rows_n >= 1
        except (TypeError, ValueError):
            columns_n, rows_n, overlap_n, grid_ok = 1, 1, 0.0, False
        if grid_ok:
            payload["columns"] = columns_n
            payload["rows"] = rows_n
            payload["overlap"] = max(0.0, min(0.8, overlap_n))
        if target is not None and target.ra_hours is not None and target.dec_degrees is not None:
            payload["target_ra_hours"] = float(target.ra_hours)
            payload["target_dec_degrees"] = float(target.dec_degrees)
        session, members = self._mosaic_context()
        mosaic_columns, mosaic_rows, live_pane, _group = self._mosaic_layout(session, members)
        if self._mosaic_is_active(session, members) and (mosaic_columns > 1 or mosaic_rows > 1):
            payload["columns"] = mosaic_columns
            payload["rows"] = mosaic_rows
            payload["live_pane"] = live_pane
            member_panes = mosaic_session_footprints(
                members or ([session] if session is not None else []),
                fov_h,
                fov_v,
                payload["position_angle"],
            )
            if member_panes:
                payload["panes"] = member_panes
                payload["mode"] = "panes"
                return sky_web_fov_script(payload)
            if session is not None and session.target.ra_hours is not None and session.target.dec_degrees is not None:
                try:
                    payload["panes"] = mosaic_pane_footprints(
                        session.target,
                        mosaic_columns,
                        mosaic_rows,
                        fov_h,
                        fov_v,
                        overlap_n,
                        south_up=south_up,
                        position_angle=payload["position_angle"],
                    )
                    payload["mode"] = "panes"
                    return sky_web_fov_script(payload)
                except ValueError:
                    pass
        if target is not None and target.ra_hours is not None and target.dec_degrees is not None and grid_ok:
            try:
                payload["panes"] = mosaic_pane_footprints(
                    target,
                    columns_n,
                    rows_n,
                    fov_h,
                    fov_v,
                    overlap_n,
                    south_up=south_up,
                    position_angle=payload["position_angle"],
                )
                payload["mode"] = "panes"
            except ValueError:
                payload["mode"] = "center"
        return sky_web_fov_script(payload)

    @Slot("QVariant")
    def pushSkyToDesktop(self, web_raw: Any) -> None:
        payload = self._snapshot_web_raw(web_raw)

        def work() -> str:
            target = self._resolve_stellarium_target(payload)
            self._push_sky_to_desktop(target)
            return target.name

        self._run_async("stellariumPush", work)

    @Slot(str)
    def openExternalUrl(self, url: str) -> None:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return
        QDesktopServices.openUrl(QUrl(parsed.geturl()))

    @Property(float, notify=sessionProgressChanged)
    def sessionProgress(self) -> float:
        self._ensure_sessions_view()
        session = self._current_session_view or {}
        planned = float(session.get("planned_duration_seconds") or 0)
        started = session.get("actual_started_at")
        if not session or not started or planned <= 0:
            return 0.0
        started_at = datetime.fromisoformat(started)
        now = datetime.now(started_at.tzinfo) if started_at.tzinfo else self._now_local()
        return min(1.0, max(0.0, (now - started_at).total_seconds() / planned))

    def _tick(self) -> None:
        clock = self._now_local().strftime("%H:%M:%S")
        if clock != self._clock_text:
            self._clock_text = clock
            self.clockChanged.emit()
        if self._active_sessions:
            self.sessionProgressChanged.emit()
        self._telemetry_tick += 1
        if self._telemetry_tick % 15 == 0 and any(worker.connected for worker in self._workers.values()):
            # Refresh the derived "stale" markers even when the device is quiet.
            self._notify_devices()
        self._scheduler_tick()

    @Property(bool, notify=schedulerEnabledChanged)
    def schedulerEnabled(self) -> bool:
        return self._scheduler_enabled

    @Property(bool, notify=devicesChanged)
    def anyDeviceConnected(self) -> bool:
        return self._any_device_connected()

    def _any_device_connected(self) -> bool:
        return any(worker.connected for worker in self._workers.values())

    @Slot(bool)
    def setSchedulerEnabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._scheduler_enabled:
            return
        if enabled and not self._any_device_connected():
            self._toast("Connect a telescope before starting the scheduler", "warning")
            return
        self._scheduler_enabled = enabled
        self.schedulerEnabledChanged.emit()
        self.add_log("info", "Scheduler started" if enabled else "Scheduler stopped")
        if enabled:
            QTimer.singleShot(0, self._scheduler_tick)

    def _disarm_scheduler_if_offline(self) -> None:
        """Drop the scheduler once the last telescope link is gone."""
        if not self._scheduler_enabled or self._any_device_connected() or self._pending_reconnect_ids:
            return
        self._scheduler_enabled = False
        self.schedulerEnabledChanged.emit()
        self.add_log("warning", "Scheduler disarmed: no telescope is connected")
        self._toast("Scheduler disarmed", "warning", "Connect a telescope and re-arm it to resume the queue")

    @Property("QVariantList", notify=sessionsChanged)
    def upcomingSessions(self) -> list[dict[str, Any]]:
        self._ensure_sessions_view()
        return self._upcoming_sessions_view or []

    @Property(str, notify=selectedDeviceChanged)
    def videoUrl(self) -> str:
        device = next(item for item in self._devices if item.id == self._selected_device_id)
        stacking = self._preview_stacking(device.id)
        camera = Camera.TELE if stacking else device.camera
        return self._stream_url(device, camera, stacking=stacking)

    @Property(bool, notify=previewActiveChanged)
    def previewActive(self) -> bool:
        return self._preview_active

    @Property(bool, notify=previewPlayingChanged)
    def previewPlaying(self) -> bool:
        return self._preview_playing

    @Property(str, notify=previewStatusChanged)
    def previewStatus(self) -> str:
        return self._preview_status

    @Property(bool, notify=previewTelePlayingChanged)
    def previewTelePlaying(self) -> bool:
        return self._preview_tele_playing

    @Property(bool, notify=previewWidePlayingChanged)
    def previewWidePlaying(self) -> bool:
        return self._preview_wide_playing

    @Property(bool, notify=previewHoldChanged)
    def previewHeld(self) -> bool:
        return bool(self._preview_hold_device_id) and self._preview_hold_device_id == self._selected_device_id

    @Property(bool, notify=previewStackingChanged)
    def previewStacking(self) -> bool:
        return bool(self._preview_stack_mode)

    @Property(bool, notify=previewResultChanged)
    def previewResult(self) -> bool:
        return bool(self._preview_result)

    @Property(str, notify=previewResultChanged)
    def previewResultTitle(self) -> str:
        return self._preview_result_title

    @Property(str, notify=previewResultChanged)
    def previewResultDetail(self) -> str:
        return self._preview_result_detail

    @Property(bool, notify=enhanceImagesChanged)
    def enhanceImages(self) -> bool:
        return bool(self._enhance_images)

    @enhanceImages.setter
    def enhanceImages(self, value: bool) -> None:
        self.setEnhanceImages(value)

    @Slot(bool)
    def setEnhanceImages(self, value: bool) -> None:
        on = bool(value)
        if on == self._enhance_images:
            return
        self._enhance_images = on
        if on:
            self._enhance_failed.clear()
            self._enhance_cache_rev += 1
            self.enhanceCacheChanged.emit()
        self.enhanceImagesChanged.emit()
        self._refresh_preview_enhance()

    @Property(bool, notify=deepCleanImagesChanged)
    def deepCleanImages(self) -> bool:
        return bool(self._deep_clean_images)

    @deepCleanImages.setter
    def deepCleanImages(self, value: bool) -> None:
        self.setDeepCleanImages(value)

    @Slot(bool)
    def setDeepCleanImages(self, value: bool) -> None:
        on = bool(value)
        if on == self._deep_clean_images:
            return
        self._deep_clean_images = on
        self.deepCleanImagesChanged.emit()
        self._refresh_preview_enhance()

    def _clamp_enhance_level(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 1.0

    def _apply_enhance_levels(self) -> None:
        set_enhance_levels(self._enhance_denoise, self._enhance_sky_crush)
        self._enhance_failed.clear()
        self._enhance_cache_rev += 1
        self.enhanceCacheChanged.emit()
        self._refresh_preview_enhance()

    @Property(float, notify=enhanceDenoiseChanged)
    def enhanceDenoise(self) -> float:
        return float(self._enhance_denoise)

    @enhanceDenoise.setter
    def enhanceDenoise(self, value: float) -> None:
        self.setEnhanceDenoise(value)

    @Slot(float)
    def setEnhanceDenoise(self, value: float) -> None:
        level = self._clamp_enhance_level(value)
        if abs(level - self._enhance_denoise) < 1e-6:
            return
        self._enhance_denoise = level
        self.enhanceDenoiseChanged.emit()
        self._apply_enhance_levels()

    @Property(float, notify=enhanceSkyCrushChanged)
    def enhanceSkyCrush(self) -> float:
        return float(self._enhance_sky_crush)

    @enhanceSkyCrush.setter
    def enhanceSkyCrush(self, value: float) -> None:
        self.setEnhanceSkyCrush(value)

    @Slot(float)
    def setEnhanceSkyCrush(self, value: float) -> None:
        level = self._clamp_enhance_level(value)
        if abs(level - self._enhance_sky_crush) < 1e-6:
            return
        self._enhance_sky_crush = level
        self.enhanceSkyCrushChanged.emit()
        self._apply_enhance_levels()

    @Property(int, notify=enhanceCacheChanged)
    def enhanceCacheGeneration(self) -> int:
        return self._enhance_cache_rev

    @Slot(str, str, result=str)
    def mediaEnhanceSource(self, url: str, profile: str) -> str:
        """Return a file:// JPEG of the enhanced image, building it in the background."""
        text = canonical_image_url(str(url or "").strip()) or str(url or "").strip()
        if not text:
            return ""
        if not enhance_available():
            return text
        kind = "deep" if str(profile or "").strip().lower() == "deep" else "std"
        key = enhance_cache_key(text, kind)
        dest = self._enhance_cache_dir() / f"{key}.jpg"
        if is_enhance_cache_valid(dest):
            self._enhance_failed.discard(key)
            return QUrl.fromLocalFile(str(dest.resolve())).toString()
        if key in self._enhance_failed:
            return ""
        if key not in self._enhance_inflight:
            self._enhance_inflight.add(key)
            self._enhance_cache_pool.start(
                CacheEnhanceJob(key, text, "deep" if kind == "deep" else "standard", dest, self._cache_enhance_signals)
            )
        return ""

    @Slot(str, str, result=bool)
    def mediaEnhanceFailed(self, url: str, profile: str) -> bool:
        text = canonical_image_url(str(url or "").strip()) or str(url or "").strip()
        if not text:
            return False
        kind = "deep" if str(profile or "").strip().lower() == "deep" else "std"
        return enhance_cache_key(text, kind) in self._enhance_failed

    @Slot(str, result=str)
    def mediaFileUrl(self, path: str) -> str:
        return self._media_file_url(path)

    def _enhance_cache_dir(self) -> Path:
        folder = self.store.root / "enhance-cache"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _on_enhance_cache_ready(self, key: str) -> None:
        key = str(key or "")
        self._enhance_inflight.discard(key)
        dest = self._enhance_cache_dir() / f"{key}.jpg"
        if is_enhance_cache_valid(dest):
            self._enhance_failed.discard(key)
        else:
            self._enhance_failed.add(key)
        self._enhance_cache_rev += 1
        self.enhanceCacheChanged.emit()

    @Property(str, notify=mediaChanged)
    def mediaSource(self) -> str:
        return self._media_source

    @Property("QVariantList", notify=mediaItemsChanged)
    def mediaItems(self) -> list[dict[str, Any]]:
        return list(self._media_items)

    @Property(str, notify=mediaChanged)
    def mediaStatus(self) -> str:
        return self._media_status

    @Property(str, notify=mediaChanged)
    def mediaSelectedId(self) -> str:
        return self._media_selected_id

    @Property("QVariantMap", notify=mediaChanged)
    def selectedMedia(self) -> dict[str, Any]:
        return next((item for item in self._media_items if item.get("id") == self._media_selected_id), {})

    @Property(str, notify=mediaChanged)
    def mediaBusy(self) -> str:
        return self._album_busy

    @Property(bool, notify=mediaChanged)
    def mediaLocked(self) -> bool:
        return self._session_is_capturing(self._selected_device_id)

    @Property(str, notify=previewHoldChanged)
    def previewHoldMessage(self) -> str:
        if not self.previewHeld:
            return ""
        session_id = self._active_sessions.get(self._preview_hold_device_id)
        session = self.store.sessions.get(session_id) if session_id else None
        step = str(session.current_step or "").strip() if session else ""
        target = self._preview_hold_target or (session.target.name if session else "this target")
        if not step or step in {"Starting worker", "Waiting"}:
            step = "Leaving live camera mode"
        return (
            f"{step} · {target}. Live view is paused so the telescope can prepare "
            "without locking the app. The stream returns when capture starts."
        )

    def _stream_url(self, device: Device, camera: Camera, stacking: bool | None = None) -> str:
        if stacking is None:
            stacking = self._preview_stacking(device.id)
        if stacking and device.model in (DeviceModel.DWARF_3, DeviceModel.DWARF_MINI):
            # RTSP stops when an astro session starts. Dwarflab documents this
            # HTTP snapshot for the tele stacking preview; wide has no equivalent.
            if camera == Camera.WIDE:
                return ""
            return f"http://{device.ip_address}:8092/mainstream"
        if device.model in (DeviceModel.DWARF_3, DeviceModel.DWARF_MINI):
            return f"rtsp://{device.ip_address}/{'ch1' if camera == Camera.WIDE else 'ch0'}/stream0"
        return f"http://{device.ip_address}:8092/{'secondstream' if camera == Camera.WIDE else 'mainstream'}"

    def _preview_stacking(self, device_id: str) -> bool:
        """Dwarf 3/Mini need the HTTP stacking JPEG while capture is running."""
        device = next((item for item in self._devices if item.id == device_id), None)
        if device is None or device.model not in (DeviceModel.DWARF_3, DeviceModel.DWARF_MINI):
            return False
        return self._session_is_capturing(device_id)

    def _set_preview_status(self, text: str) -> None:
        if self._preview_status == text:
            return
        self._preview_status = text
        self.previewStatusChanged.emit()

    @Slot(str)
    def startPreview(self, device_id: str) -> None:
        device = self._device_by_id(device_id)
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            self.add_log("warning", "Preview needs an active telescope connection", device_id)
            return
        if self._device_is_stopping(device_id):
            self.add_log("info", "Live view stays paused while the telescope stops", device_id)
            return
        if self._preview_should_attach_only(device_id):
            self._clear_preview_hold()
            stacking = self._preview_stacking(device_id)
            self.add_log(
                "info",
                "Attaching to stacking preview" if stacking else "Attaching live view without interrupting the session",
                device_id,
            )
            self._attach_preview_streams(
                device_id,
                "Attaching to stacking preview…" if stacking else "Attaching to live view…",
            )
            return
        if self._preview_hold_device_id == device_id and self._session_is_capturing(device_id):
            self._resume_held_preview(device_id)
            return
        if self._preview_hold_device_id == device_id and self._active_sessions.get(device_id):
            self.add_log("info", "Live view stays paused until this session starts capturing", device_id)
            self._refresh_preview_hold()
            return
        self._clear_preview_hold()
        token = self._arm_preview_ui("Starting live camera…")
        tele_url = self._stream_url(device, Camera.TELE)
        wide_url = self._stream_url(device, Camera.WIDE)
        host = urlparse(tele_url).hostname or device.ip_address
        port = stream_port(tele_url)

        def after_cameras(ok: bool, result: Any) -> None:
            if token != self._preview_token:
                return
            if not ok:
                self.add_log("error", f"Could not open camera: {result}", device_id)
                self._set_preview_status("Camera failed to open")
                return
            self._schedule_camera_param_refresh(device_id)
            self._begin_stream_wait(token, tele_url, wide_url, host, port)

        def after_photo(ok: bool, result: Any) -> None:
            if token != self._preview_token:
                return
            if not ok:
                after_cameras(False, result)
                return
            self._on_telemetry(device_id, {"shooting_mode": 1, "shooting_tech": 1})
            if device.model in (DeviceModel.DWARF_3, DeviceModel.DWARF_MINI):
                # V3 photo mode already initializes both RTSP cameras. The
                # legacy tele open command can hang after wide was opened.
                after_cameras(True, result)
                return
            primary_op = "open_wide_camera" if device.camera == Camera.WIDE else "open_camera"
            secondary_op = "open_camera" if device.camera == Camera.WIDE else "open_wide_camera"

            def after_primary(primary_ok: bool, primary_result: Any) -> None:
                if token != self._preview_token:
                    return
                if not primary_ok:
                    after_cameras(False, primary_result)
                    return

                def after_secondary(secondary_ok: bool, secondary_result: Any) -> None:
                    if token != self._preview_token:
                        return
                    if not secondary_ok:
                        self.add_log(
                            "warning",
                            f"Second camera did not open for picture-in-picture: {secondary_result}",
                            device_id,
                        )
                    after_cameras(True, primary_result)

                worker.send(secondary_op, callback=after_secondary)

            worker.send(primary_op, callback=after_primary)

        def after_live(ok: bool, result: Any) -> None:
            if token != self._preview_token:
                return
            if not ok:
                self.add_log("warning", f"Could not close previous capture: {result}", device_id)
            worker.send("photo_mode", callback=after_photo)

        worker.send("go_live", callback=after_live)

    def _arm_preview_ui(self, status: str) -> int:
        self._clear_preview_result()
        if self._preview_active or self._preview_playing:
            self._closePreviewStreams.emit()
        self._preview_token += 1
        self._preview_active = True
        self._preview_playing = False
        self._preview_tele_playing = False
        self._preview_wide_playing = False
        self.live_images.clear()
        self._raw_preview_images = {"tele": QImage(), "wide": QImage()}
        self._enhance_job_token = {"tele": self._enhance_job_token.get("tele", 0) + 1, "wide": self._enhance_job_token.get("wide", 0) + 1}
        self._last_preview_ui.clear()
        self._preview_tele_url = ""
        self._preview_wide_url = ""
        self._set_preview_stack_mode(self._preview_stacking(self._selected_device_id))
        self._set_preview_status(status)
        self.previewActiveChanged.emit()
        self.previewPlayingChanged.emit()
        self.previewTelePlayingChanged.emit()
        self.previewWidePlayingChanged.emit()
        return self._preview_token

    def _begin_stream_wait(
        self,
        token: int,
        tele_url: str,
        wide_url: str,
        host: str,
        port: int,
        timeout: float = 12,
        status: str | None = None,
    ) -> None:
        if wide_url:
            self.add_log("info", f"Opening {tele_url} and {wide_url} in the background")
        else:
            self.add_log("info", f"Opening {tele_url} in the background")
        self._set_preview_status(status or ("Waiting for stream " + tele_url))
        self._preview_tele_url = tele_url
        self._preview_wide_url = wide_url
        threading.Thread(
            target=self._wait_for_stream,
            args=(token, tele_url, wide_url, host, port, timeout),
            daemon=True,
            name="preview-wait",
        ).start()

    def _wait_for_stream(
        self,
        token: int,
        tele_url: str,
        wide_url: str,
        host: str,
        port: int,
        timeout: float = 12,
    ) -> None:
        deadline = time.monotonic() + timeout
        while token == self._preview_token and time.monotonic() < deadline:
            if port_is_open(host, port, timeout=0.8):
                break
            time.sleep(0.35)
        if token != self._preview_token:
            return
        self._previewReady.emit(token, tele_url, wide_url)

    def _open_ready_stream(self, token: int, tele_url: str, wide_url: str) -> None:
        if token != self._preview_token:
            return
        self._preview_tele_url = tele_url
        self._preview_wide_url = wide_url
        if tele_url:
            self._set_preview_status(tele_url)
        if not wide_url:
            self._openTeleStream.emit(tele_url)
            self._closeWideStream.emit()
            if self._preview_wide_playing:
                self._preview_wide_playing = False
                self.previewWidePlayingChanged.emit()
            return
        device = self._device_by_id(self._selected_device_id)
        primary_wide = device.camera == Camera.WIDE
        if primary_wide:
            self._openWideStream.emit(wide_url)
            QTimer.singleShot(400, lambda: self._open_secondary_stream(token, "tele", tele_url))
        else:
            self._openTeleStream.emit(tele_url)
            QTimer.singleShot(400, lambda: self._open_secondary_stream(token, "wide", wide_url))

    def _open_secondary_stream(self, token: int, camera: str, url: str) -> None:
        if token != self._preview_token or not self._preview_active or not url:
            return
        if camera == "wide":
            self._openWideStream.emit(url)
        else:
            self._openTeleStream.emit(url)

    @Slot()
    def stopPreview(self) -> None:
        self._clear_preview_hold()
        self._clear_preview_result()
        self._stop_preview_streams()

    def _stop_preview_streams(self) -> None:
        self._preview_token += 1
        self._pending_retarget = None
        self._retarget_timer.stop()
        if self._preview_active or self._preview_playing:
            self._closePreviewStreams.emit()
        self._preview_active = False
        self._preview_playing = False
        self._preview_tele_playing = False
        self._preview_wide_playing = False
        self.live_images.clear()
        self._raw_preview_images = {"tele": QImage(), "wide": QImage()}
        self._enhance_job_token = {"tele": self._enhance_job_token.get("tele", 0) + 1, "wide": self._enhance_job_token.get("wide", 0) + 1}
        self._last_preview_ui.clear()
        self._preview_tele_url = ""
        self._preview_wide_url = ""
        self._set_preview_stack_mode(False)
        self._set_preview_status("")
        self.previewActiveChanged.emit()
        self.previewPlayingChanged.emit()
        self.previewTelePlayingChanged.emit()
        self.previewWidePlayingChanged.emit()

    def _clear_preview_hold(self) -> None:
        if not self._preview_hold_device_id and not self._preview_hold_target:
            return
        self._preview_hold_device_id = ""
        self._preview_hold_target = ""
        self.previewHoldChanged.emit()

    def _refresh_preview_hold(self) -> None:
        if not self._preview_hold_device_id:
            return
        self.previewHoldChanged.emit()
        if self.previewHeld:
            self._set_preview_status(self.previewHoldMessage)

    def _hold_preview_for_session(self, device_id: str, target_name: str) -> None:
        """Keep RTSP live view up until stacking; `_sync_preview_for_capture` switches it."""

    def _device_is_stopping(self, device_id: str) -> bool:
        return self._pending_actions.get(device_id) in _STOP_ACTIONS

    def _telemetry_capturing(self, device_id: str) -> bool:
        telemetry = self._device_telemetry.get(device_id) or {}
        return bool(telemetry.get("capture_active") or telemetry.get("capture_state") == "running")

    def _session_is_capturing(self, device_id: str) -> bool:
        if self._device_is_stopping(device_id):
            return False
        if self._telemetry_capturing(device_id):
            return True
        session_id = self._active_sessions.get(device_id)
        session = self.store.sessions.get(session_id) if session_id else None
        step = str(session.current_step or "").split(" · ")[0].strip() if session else ""
        return bool(session and step in _CAPTURE_PREVIEW_STEPS)

    def _sync_media_lock(self) -> None:
        locked = self._session_is_capturing(self._selected_device_id)
        if locked == self._media_locked:
            if locked and self._media_source != "local" and self._media_status != _MEDIA_LOCKED_STATUS:
                self._clear_media(_MEDIA_LOCKED_STATUS)
            return
        self._media_locked = locked
        if locked and self._media_source != "local":
            self._clear_media(_MEDIA_LOCKED_STATUS)
            return
        if self._media_status == _MEDIA_LOCKED_STATUS:
            self._set_media_status("")
            return
        self._emit_media()

    def _set_preview_stack_mode(self, stacking: bool) -> None:
        stacking = bool(stacking)
        if self._preview_stack_mode == stacking:
            return
        self._preview_stack_mode = stacking
        self.previewStackingChanged.emit()

    def _preview_has_frame(self) -> bool:
        for camera in ("tele", "wide"):
            image = self.live_images.peek(camera)
            if image is not None and not image.isNull():
                return True
        return False

    def _clear_preview_result(self) -> None:
        self._cancel_stack_result_fetch()
        if not self._preview_result and not self._preview_result_title and not self._preview_result_detail:
            return
        self._preview_result = False
        self._preview_result_title = ""
        self._preview_result_detail = ""
        self.previewResultChanged.emit()

    def _cancel_stack_result_fetch(self) -> None:
        self._stack_result_token += 1
        self._stack_result_timer.stop()
        self._stack_result_loaded = False
        self._stack_result_device_id = ""
        self._stack_result_target = ""
        self._stack_result_camera = ""
        self._stack_result_since = 0
        self._stack_result_started = 0.0
        self._stack_result_final_detail = ""

    def _preview_camera_name(self, device_id: str) -> str:
        session_id = self._active_sessions.get(device_id)
        session = self.store.sessions.get(session_id) if session_id else None
        camera = session.camera.camera if session else None
        if camera is None:
            device = next((item for item in self._devices if item.id == device_id), None)
            camera = device.camera if device else Camera.TELE
        if hasattr(camera, "value"):
            return str(camera.value)
        return str(camera or "tele")

    def _stack_result_since_for(self, device_id: str, started: datetime | None = None) -> int:
        if started is not None:
            return int(started.timestamp())
        session_id = self._active_sessions.get(device_id)
        session = self.store.sessions.get(session_id) if session_id else None
        stamp = str(session.actual_started_at or "") if session else ""
        if stamp:
            try:
                return int(datetime.fromisoformat(stamp).timestamp())
            except ValueError:
                pass
        return int(time.time())

    @staticmethod
    def _discard_stack_result_file(path: str) -> None:
        local = Path(str(path or ""))
        if not local.parts:
            return
        try:
            if local.is_file():
                local.unlink()
        except OSError:
            return
        try:
            local.parent.rmdir()
        except OSError:
            pass

    def _close_preview_streams_keep_frames(self) -> None:
        """Stop HTTP/RTSP without wiping the last painted stacked frame."""
        self._pending_retarget = None
        self._retarget_timer.stop()
        self._preview_token += 1
        was_open = self._preview_active or self._preview_playing
        self._preview_active = False
        self._preview_playing = False
        self._preview_tele_playing = False
        self._preview_wide_playing = False
        self._preview_tele_url = ""
        self._preview_wide_url = ""
        self._set_preview_stack_mode(False)
        if was_open:
            self._closePreviewStreams.emit()
        self.previewActiveChanged.emit()
        self.previewPlayingChanged.emit()
        self.previewTelePlayingChanged.emit()
        self.previewWidePlayingChanged.emit()

    def _freeze_stacking_preview_result(
        self,
        device_id: str,
        *,
        title: str = "STACK COMPLETE",
        detail: str = "",
        target: str = "",
        camera: str = "",
        since: int = 0,
    ) -> None:
        """Keep the last stacking JPEG, then swap in the album's completed stack."""
        if device_id != self._selected_device_id:
            return
        has_frame = self._preview_has_frame()
        preview_was_on = (
            self._preview_active
            or self._preview_stack_mode
            or self._preview_result
            or has_frame
        )
        if not preview_was_on:
            return
        already = self._preview_result and self._stack_result_device_id == device_id
        if not has_frame and not already:
            self._close_preview_streams_keep_frames()
            self.live_images.clear()
            self._raw_preview_images = {"tele": QImage(), "wide": QImage()}
        elif self._preview_active or self._preview_stack_mode or self._preview_tele_url:
            self._close_preview_streams_keep_frames()
        final_detail = detail or _STACK_RESULT_READY
        self._preview_result = True
        self._preview_result_title = title or "STACK COMPLETE"
        self._stack_result_final_detail = final_detail
        if self._stack_result_loaded:
            self._preview_result_detail = final_detail
        else:
            self._preview_result_detail = _STACK_RESULT_LOADING
        self._set_preview_status(self._preview_result_detail)
        self.previewResultChanged.emit()
        if already:
            if target:
                self._stack_result_target = target
            if camera:
                self._stack_result_camera = camera
            if since:
                self._stack_result_since = int(since)
            if self._stack_result_loaded:
                self.add_log("info", "Capture ended — showing the completed stack", device_id)
            return
        self.add_log("info", "Capture ended — loading the completed stack", device_id)
        self._sync_mosaic_preview(device_id)
        self._snapshot_mosaic_pane(int((self.mosaicPreview or {}).get("current_index") or 0))
        self._start_stack_result_fetch(device_id, target, camera, since)

    def _start_stack_result_fetch(
        self,
        device_id: str,
        target: str = "",
        camera: str = "",
        since: int = 0,
    ) -> None:
        self._stack_result_token += 1
        self._stack_result_timer.stop()
        self._stack_result_loaded = False
        self._stack_result_device_id = device_id
        self._stack_result_target = str(target or "").strip()
        self._stack_result_camera = str(camera or self._preview_camera_name(device_id) or "tele")
        self._stack_result_since = int(since or self._stack_result_since_for(device_id))
        self._stack_result_started = time.monotonic()
        self._fetch_stack_result_image()

    def _fetch_stack_result_image(self) -> None:
        device_id = self._stack_result_device_id
        if not self._preview_result or device_id != self._selected_device_id:
            return
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            self._finish_stack_result_fetch(False, "Telescope is not connected")
            return
        token = self._stack_result_token

        def done(ok: bool, result: Any) -> None:
            if token != self._stack_result_token:
                if ok and isinstance(result, dict):
                    self._discard_stack_result_file(str(result.get("path") or ""))
                return
            if ok and isinstance(result, dict) and result.get("path"):
                if self._apply_stack_result_image(device_id, str(result["path"])):
                    return
            elif ok and isinstance(result, dict):
                self._discard_stack_result_file(str(result.get("path") or ""))
            self._finish_stack_result_fetch(False, str(result or "Completed stack JPEG was not ready"))

        worker.send(
            "astro_stack_result_image",
            {
                "target": self._stack_result_target,
                "camera": self._stack_result_camera,
                "since": self._stack_result_since,
            },
            done,
        )

    def _apply_stack_result_image(self, device_id: str, path: str) -> bool:
        image = QImage(str(path))
        if image.isNull():
            self._discard_stack_result_file(path)
            return False
        shown = image.copy()
        self._discard_stack_result_file(path)
        self._raw_preview_images["tele"] = shown
        if self._should_enhance_preview():
            current = self.live_images.peek("tele")
            if current.isNull():
                self.live_images.update("tele", shown)
                self.live_images.notify("tele")
            self._queue_preview_enhance("tele", shown)
        else:
            self.live_images.update("tele", shown)
            self.live_images.notify("tele")
        self._stack_result_loaded = True
        self._stack_result_timer.stop()
        self._preview_result_detail = self._stack_result_final_detail or _STACK_RESULT_READY
        self._set_preview_status(self._preview_result_detail)
        self.previewResultChanged.emit()
        self._sync_mosaic_preview(device_id)
        self._store_mosaic_pane_image(int((self.mosaicPreview or {}).get("current_index") or 0), shown)
        self.add_log("info", "Showing the completed stack in live preview", device_id)
        return True

    def _finish_stack_result_fetch(self, ok: bool, result: Any) -> None:
        if ok or self._stack_result_loaded:
            return
        elapsed = time.monotonic() - (self._stack_result_started or time.monotonic())
        if elapsed < _STACK_RESULT_RETRY_S:
            if not self._stack_result_timer.isActive():
                self._stack_result_timer.start()
            return
        self._stack_result_timer.stop()
        self._preview_result_detail = self._stack_result_final_detail or _STACK_RESULT_READY
        self._set_preview_status(self._preview_result_detail)
        self.previewResultChanged.emit()
        self.add_log(
            "info",
            "Completed stack JPEG was not available yet — keeping the last stacking frame",
            self._stack_result_device_id,
        )

    def _stacking_result_copy(self, ok: bool, stopped: bool, target: str) -> tuple[str, str]:
        return stacking_preview_result_copy(ok, stopped, target, self._scheduler_enabled)

    def _sync_preview_for_capture(
        self,
        device_id: str,
        previous: dict[str, Any],
        current: dict[str, Any],
    ) -> None:
        """Move Dwarf 3/Mini live view onto the HTTP stacking JPEG during capture."""
        if device_id != self._selected_device_id:
            return
        if self._device_is_stopping(device_id):
            return
        stacking = self._preview_stacking(device_id)
        if stacking and self._preview_result and not self._preview_active:
            self._clear_preview_result()
            self._attach_preview_streams(device_id, "Capture started — reconnecting stacking preview…")
            return
        if not self._preview_active:
            return
        device = self._device_by_id(device_id)
        tele_url = self._stream_url(device, Camera.TELE, stacking=stacking)
        wide_url = self._stream_url(device, Camera.WIDE, stacking=stacking)
        mode_changed = stacking != self._preview_stack_mode
        urls_changed = tele_url != self._preview_tele_url or wide_url != self._preview_wide_url
        if not mode_changed and not self._preview_tele_url:
            return
        if mode_changed or urls_changed:
            was_stacking = self._preview_stack_mode
            if not stacking and was_stacking:
                self._freeze_stacking_preview_result(
                    device_id,
                    target=str(current.get("capture_target") or ""),
                    camera=self._preview_camera_name(device_id),
                    since=self._stack_result_since_for(device_id),
                )
                return
            self._set_preview_stack_mode(stacking)
            if stacking and not was_stacking:
                self.add_log(
                    "info",
                    "Capture started — switching live view to the stacking preview",
                    device_id,
                )
            self._retarget_preview_streams(tele_url, wide_url)

    def _retarget_preview_streams(self, tele_url: str, wide_url: str, timeout: float = 20) -> None:
        """Switch stream URLs without clearing the last frame or sending go_live."""
        self._pending_retarget = (tele_url, wide_url, timeout)
        if not self._retarget_timer.isActive():
            self._retarget_timer.start()

    def _flush_preview_retarget(self) -> None:
        pending = self._pending_retarget
        self._pending_retarget = None
        if not pending or not self._preview_active:
            return
        tele_url, wide_url, timeout = pending
        self._preview_token += 1
        token = self._preview_token
        self._preview_tele_url = tele_url
        self._preview_wide_url = wide_url
        status = (
            "Switching to stacking preview…"
            if tele_url.startswith("http://")
            else "Restoring camera stream…"
        )
        self._set_preview_status(status)
        if tele_url.startswith("http://"):
            self.add_log("info", f"Opening {tele_url} in the background")
            self._open_ready_stream(token, tele_url, wide_url)
            return
        host = urlparse(tele_url).hostname or self._device_by_id(self._selected_device_id).ip_address
        self._begin_stream_wait(
            token,
            tele_url,
            wide_url,
            host,
            stream_port(tele_url),
            timeout=timeout,
            status=status,
        )

    def _preview_should_attach_only(self, device_id: str) -> bool:
        """Avoid go_live / photo_mode while the telescope is already working."""
        if self._active_sessions.get(device_id):
            return True
        worker = self._workers.get(device_id)
        if worker and worker.busy:
            return True
        if self._session_is_capturing(device_id):
            return True
        telemetry = self._device_telemetry.get(device_id) or {}
        if telemetry.get("capture_active") or telemetry.get("capture_state") == "running":
            return True
        for item in self._ensure_sessions_view():
            if item.get("device_id") == device_id and item.get("status") == SessionStatus.RUNNING:
                return True
        return False

    def _attach_preview_streams(self, device_id: str, status: str, timeout: float = 20) -> None:
        if device_id != self._selected_device_id:
            return
        worker = self._workers.get(device_id)
        device = next((item for item in self._devices if item.id == device_id), None)
        if not worker or not worker.connected or device is None:
            return
        token = self._arm_preview_ui(status)
        tele_url = self._stream_url(device, Camera.TELE)
        wide_url = self._stream_url(device, Camera.WIDE)
        self._schedule_camera_param_refresh(device_id)
        if tele_url.startswith("http://"):
            self.add_log("info", f"Opening {tele_url} in the background")
            self._set_preview_status(status)
            self._open_ready_stream(token, tele_url, wide_url)
            return
        host = urlparse(tele_url).hostname or device.ip_address
        self._begin_stream_wait(
            token,
            tele_url,
            wide_url,
            host,
            stream_port(tele_url),
            timeout=timeout,
            status=status,
        )

    def _maybe_resume_held_preview(self, device_id: str) -> None:
        if self._preview_hold_device_id != device_id:
            return
        if not self._session_is_capturing(device_id):
            return
        self._resume_held_preview(device_id)

    def _resume_held_preview(self, device_id: str) -> None:
        if self._preview_hold_device_id != device_id:
            return
        if self._preview_active or self._preview_playing:
            self._clear_preview_hold()
            return
        self._clear_preview_hold()
        self.add_log("info", "Capture started; reconnecting live view", device_id)
        self._attach_preview_streams(device_id, "Capture started — reconnecting live view…")

    def _restore_held_preview(self, device_id: str) -> None:
        if device_id != self._selected_device_id:
            return
        worker = self._workers.get(device_id)
        if worker and worker.connected:
            QTimer.singleShot(0, lambda did=device_id: self.startPreview(did))

    def bindPreviewWindow(self, window) -> None:
        self._preview_window = window
        if window is None:
            return
        visibility_changed = getattr(window, "visibilityChanged", None)
        if visibility_changed is not None:
            visibility_changed.connect(self._on_preview_window_state)
        app = QGuiApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._on_preview_window_state)
        self._preview_window_filter = _PreviewWindowFilter(self)
        window.installEventFilter(self._preview_window_filter)

    def _on_preview_window_state(self, *_args) -> None:
        if self._preview_result:
            if preview_window_is_live(self._preview_window):
                self.live_images.notify("*")
            return
        if not self._preview_active or not preview_window_is_live(self._preview_window):
            return
        self.live_images.notify("*")

    def _should_enhance_preview(self) -> bool:
        return bool(self._enhance_images) and bool(self._preview_stack_mode or self._preview_result)

    def _preview_can_enhance(self) -> bool:
        return bool(self._preview_active or self._preview_result)

    def _preview_enhance_profile(self) -> str:
        return "deep" if self._deep_clean_images else "standard"

    def _queue_preview_enhance(self, camera: str, raw: QImage) -> None:
        self._enhance_job_token[camera] = int(self._enhance_job_token.get(camera, 0)) + 1
        token = self._enhance_job_token[camera]
        job = PreviewEnhanceJob(
            token,
            camera,
            raw.copy(),
            self._preview_enhance_profile(),
            self._preview_enhance_signals,
        )
        self._enhance_pool.start(job)

    def _on_preview_enhanced(self, token: int, camera: str, image) -> None:
        if self._shut_down or not self._preview_can_enhance():
            return
        if token != self._enhance_job_token.get(camera):
            return
        if not isinstance(image, QImage) or image.isNull() or not self._should_enhance_preview():
            return
        self.live_images.update(camera, image)
        if camera == "tele" and self._preview_result:
            self._store_mosaic_pane_image(int((self.mosaicPreview or {}).get("current_index") or 0), image)
        if preview_window_is_live(self._preview_window):
            self.live_images.notify(camera)

    def _refresh_preview_enhance(self) -> None:
        if not self._preview_can_enhance():
            return
        for camera in ("tele", "wide"):
            raw = self._raw_preview_images.get(camera) or QImage()
            if raw.isNull():
                continue
            if self._should_enhance_preview():
                self._queue_preview_enhance(camera, raw)
                continue
            self._enhance_job_token[camera] = int(self._enhance_job_token.get(camera, 0)) + 1
            self.live_images.update(camera, raw)
            self.live_images.notify(camera)

    def _on_tele_frame(self, image) -> None:
        self._on_camera_frame("tele", image)

    def _on_wide_frame(self, image) -> None:
        self._on_camera_frame("wide", image)

    def _on_camera_frame(self, camera: str, image) -> None:
        if not self._preview_active:
            return
        first_frame = (camera == "wide" and not self._preview_wide_playing) or (
            camera == "tele" and not self._preview_tele_playing
        )
        window_live = preview_window_is_live(self._preview_window)
        now = time.monotonic()
        if not first_frame and (
            not window_live or now - self._last_preview_ui.get(camera, 0.0) < 0.05
        ):
            return
        self._last_preview_ui[camera] = now
        raw = image.copy() if isinstance(image, QImage) and not image.isNull() else QImage()
        self._raw_preview_images[camera] = raw
        if self._should_enhance_preview():
            shown = self.live_images.peek(camera)
            if shown.isNull():
                self.live_images.update(camera, raw)
            self._queue_preview_enhance(camera, raw)
        else:
            self.live_images.update(camera, raw)
        if first_frame:
            if camera == "wide":
                self._preview_wide_playing = True
                self.previewWidePlayingChanged.emit()
            else:
                self._preview_tele_playing = True
                self.previewTelePlayingChanged.emit()
            if not self._preview_playing:
                self._preview_playing = True
                self._set_preview_status(self.videoUrl)
                self.previewPlayingChanged.emit()
        if window_live:
            self.live_images.notify(camera)

    def _on_tele_failed(self, message: str) -> None:
        self._on_camera_preview_failed("tele", message)

    def _on_wide_failed(self, message: str) -> None:
        self._on_camera_preview_failed("wide", message)

    def _on_camera_preview_failed(self, camera: str, message: str) -> None:
        other_playing = self._preview_wide_playing if camera == "tele" else self._preview_tele_playing
        text = message or "Video preview failed"
        url = self._stream_url(self._device_by_id(self._selected_device_id), Camera(camera))
        if not url:
            if other_playing:
                return
            self.add_log("error", text)
            self._set_preview_status(text)
            return
        if "Could not open file" in text or not text.strip():
            text = f"Could not open {url}. The control link is up, but the camera stream is not reachable yet."
        if other_playing:
            self.add_log("warning", f"{camera} preview: {text}")
            return
        self.add_log("error", text)
        self._set_preview_status(text)

    def _on_tele_status(self, message: str) -> None:
        self._on_camera_preview_status("tele", message)

    def _on_wide_status(self, message: str) -> None:
        self._on_camera_preview_status("wide", message)

    def _on_camera_preview_status(self, camera: str, message: str) -> None:
        if not self._preview_active or self._preview_playing:
            return
        device = self._device_by_id(self._selected_device_id)
        primary = "tele" if self._preview_stack_mode or device.camera != Camera.WIDE else "wide"
        if camera == primary:
            self._set_preview_status(message)

    @Slot(str, str)
    def uiLog(self, level: str, message: str) -> None:
        self.add_log(level, message)

    @Slot(str)
    def selectDevice(self, device_id: str) -> None:
        if any(device.id == device_id for device in self._devices):
            previous = self._selected_device_id
            if previous != device_id:
                self.stopPreview()
                self._clear_mosaic_preview()
            self._selected_device_id = device_id
            if previous != device_id and self._media_source != "local":
                self._clear_media()
            self._rebuild_devices_view()
            self.selectedDeviceChanged.emit()
            self.durationSuggestionChanged.emit()
            self._refresh_selected_session_views()
            self.clockChanged.emit()
            self.previewHoldChanged.emit()
            self._sync_media_lock()
            if previous != device_id:
                self._persist_last_device_id(device_id)

    @Property(str, notify=uiBusyChanged)
    def uiBusy(self) -> str:
        return self._ui_busy

    @Property(bool, notify=locationLookupBusyChanged)
    def locationLookupBusy(self) -> bool:
        return self._location_lookup_busy

    def _set_location_lookup_busy(self, busy: bool) -> None:
        on = bool(busy)
        if on == self._location_lookup_busy:
            return
        self._location_lookup_busy = on
        self.locationLookupBusyChanged.emit()

    @Property(bool, notify=deviceDiscoveryBusyChanged)
    def deviceDiscoveryBusy(self) -> bool:
        return self._device_discovery_busy

    def _set_device_discovery_busy(self, busy: bool) -> None:
        on = bool(busy)
        if on == self._device_discovery_busy:
            return
        self._device_discovery_busy = on
        self.deviceDiscoveryBusyChanged.emit()

    def _set_ui_busy(self, operation: str) -> None:
        if self._ui_busy == operation:
            return
        self._ui_busy = operation
        self.uiBusyChanged.emit()

    def _claimed_ips(self, device_id: str) -> list[str]:
        return [
            str(item.ip_address or "").strip()
            for item in self._devices
            if item.id != device_id and str(item.ip_address or "").strip()
        ]

    def _ip_owner(self, ip_address: str, device_id: str) -> Device | None:
        ip = str(ip_address or "").strip()
        if not ip:
            return None
        return next(
            (
                item
                for item in self._devices
                if item.id != device_id and str(item.ip_address or "").strip() == ip
            ),
            None,
        )

    def _connect_failure_text(self, result: Any) -> str:
        if result is False or result is None:
            return "Could not reach the telescope. Check the IP address, or enable Bluetooth."
        text = str(result).strip()
        if not text or text.lower() in {"false", "none"}:
            return "Could not reach the telescope. Check the IP address, or enable Bluetooth."
        return text

    @Slot(str)
    def connectDevice(self, device_id: str) -> None:
        device = next((item for item in self._devices if item.id == device_id), None)
        if not device or device_id in self._connecting_ids:
            return
        if not device.location_configured:
            self._toast("Choose an observing location before connecting the telescope", "warning")
            return
        worker = self._workers.get(device_id)
        if worker is None:
            self.add_log("error", "Connection failed: telescope worker is not running", device_id)
            self._toast("Connection failed", "error", "Telescope worker is not running")
            return
        self._connecting_ids.add(device_id)
        self._notify_devices()
        self.add_log("info", "Connection requested; UI remains available", device_id)
        worker.connect_device(
            lambda ok, result: self._connection_done(device_id, ok, result),
            claimed_ips=self._claimed_ips(device_id),
        )

    @Slot(str)
    def cancelConnect(self, device_id: str) -> None:
        worker = self._workers.get(device_id)
        if not worker or device_id not in self._connecting_ids or device_id in self._cancel_connect_ids:
            return
        if device_id == self._selected_device_id:
            self.stopPreview()
        self._cancel_connect_ids.add(device_id)
        self._cancel_disconnect_done.discard(device_id)
        worker.connected = False
        self.add_log("info", "Cancelling connection", device_id)
        self._notify_devices()

        def done(_ok: bool, _result: Any) -> None:
            self._mark_cancel_disconnect_done(device_id)

        worker.disconnect_device(done)

    def _mark_cancel_disconnect_done(self, device_id: str) -> None:
        self._cancel_disconnect_done.add(device_id)
        self._finish_cancelled_connect(device_id)

    def _finish_cancelled_connect(self, device_id: str) -> None:
        if device_id not in self._cancel_connect_ids:
            return
        if device_id in self._connecting_ids:
            return
        if device_id not in self._cancel_disconnect_done:
            return
        self._cancel_connect_ids.discard(device_id)
        self._cancel_disconnect_done.discard(device_id)
        worker = self._workers.get(device_id)
        if worker:
            worker.connected = False
        self._set_activity(device_id, "")
        self._device_telemetry.pop(device_id, None)
        self._telemetry_updated.pop(device_id, None)
        self._hold_session_capture.discard(device_id)
        self._pending_session_finish.pop(device_id, None)
        self._device_lights.pop(device_id, None)
        self._device_indicators.pop(device_id, None)
        self.add_log("info", "Connection cancelled", device_id)
        self._toast("Connection cancelled", "info")
        self._disarm_scheduler_if_offline()
        self._notify_devices()

    def _persist_discovered_ip(self, device_id: str, ip_address: str) -> None:
        current = self._device_by_id(device_id)
        ip = str(ip_address or "").strip()
        if not current or not ip or current.ip_address == ip:
            return
        if self._ip_owner(ip, device_id) is not None:
            return
        updated = replace(current, ip_address=ip)
        self.store.devices.save(updated)
        self._devices = [updated if item.id == updated.id else item for item in self._devices]
        worker = self._workers.get(device_id)
        if worker:
            worker.device = updated
        self.add_log("info", f"Saved Bluetooth IP {ip}", device_id)

    def _connection_done(self, device_id: str, ok: bool, result: Any) -> None:
        cancelled = (
            device_id in self._cancel_connect_ids
            or (not ok and "connection cancelled" in str(result or "").lower())
        )
        if cancelled and device_id not in self._cancel_connect_ids:
            self._cancel_connect_ids.add(device_id)
        discovered = ""
        if ok and isinstance(result, dict):
            discovered = str(result.get("ip_address") or "").strip()
        owner = self._ip_owner(discovered, device_id) if discovered else None
        self._connecting_ids.discard(device_id)
        if cancelled:
            worker = self._workers.get(device_id)
            if worker:
                worker.connected = False
            if ok:
                self.add_log("info", "Connected, dropping the link after cancel", device_id)
                if worker and device_id in self._cancel_disconnect_done:
                    self._cancel_disconnect_done.discard(device_id)
                    worker.disconnect_device(
                        lambda _ok, _result, did=device_id: self._mark_cancel_disconnect_done(did)
                    )
                    self._notify_devices()
                    return
            self._finish_cancelled_connect(device_id)
            self._notify_devices()
            return
        if owner is not None:
            worker = self._workers.get(device_id)
            if worker:
                worker.connected = False
                worker.disconnect_device()
            message = (
                f"Bluetooth found {discovered}, but that address is already saved as {owner.name}."
            )
            self.add_log("error", f"Connection failed: {message}", device_id)
            self._toast("Connection failed", "error", message)
            self._disarm_scheduler_if_offline()
            self._notify_devices()
            return
        if discovered:
            self._persist_discovered_ip(device_id, discovered)
        fail_text = self._connect_failure_text(result)
        self.add_log("success" if ok else "error", "Connected" if ok else f"Connection failed: {fail_text}", device_id)
        if ok:
            device = self._device_by_id(device_id)
            telemetry = result.get("telemetry") if isinstance(result, dict) else None
            detail = ""
            if isinstance(telemetry, dict) and telemetry:
                parts = []
                if telemetry.get("battery_percent") is not None:
                    parts.append(f"Battery {int(telemetry['battery_percent'])}%")
                if telemetry.get("storage_total_gb"):
                    parts.append(f"{int(telemetry.get('storage_free_gb') or 0)}/{int(telemetry['storage_total_gb'])} GB free")
                detail = " · ".join(parts)
            self._toast(f"{device.name} connected", "success", detail)
            if isinstance(telemetry, dict) and telemetry:
                self._on_telemetry(device_id, telemetry)
            self._maybe_resume_interrupted_session(device_id)
            self._maybe_auto_start_preview(device_id)
            QTimer.singleShot(8000, lambda did=device_id: self._release_recovered_if_idle(did))
            delay_ms = 8000 if device and device.model == DeviceModel.DWARF_3 else 2500
            QTimer.singleShot(delay_ms, lambda did=device_id: self.refreshCameraParams(did))
        else:
            self._toast("Connection failed", "error", fail_text)
            self._disarm_scheduler_if_offline()
        self._notify_devices()

    def _maybe_auto_start_preview(self, device_id: str) -> None:
        """Start live view after a successful connect when the device setting is on."""
        device = next((item for item in self._devices if item.id == device_id), None)
        if device is None or not device.auto_start_preview:
            return
        QTimer.singleShot(0, lambda did=device_id: self._auto_start_preview_after_connect(did))

    def _auto_start_preview_after_connect(self, device_id: str) -> None:
        if self._shut_down:
            return
        device = next((item for item in self._devices if item.id == device_id), None)
        worker = self._workers.get(device_id)
        if (
            device is None
            or not device.auto_start_preview
            or device_id != self._selected_device_id
            or not worker
            or not worker.connected
            or self._preview_active
            or self._preview_playing
            or self._device_is_stopping(device_id)
        ):
            return
        self.add_log("info", "Starting live preview after connect", device_id)
        self.startPreview(device_id)

    def _abort_active_session(self, device_id: str, reason: str) -> bool:
        """Flag the running session as user-stopped.

        Returns True when a session was running. The worker aborts the session
        itself once it receives the stop/disconnect command. The fleet scheduler
        stays armed so other telescopes can still start their queues.
        """
        session_id = self._active_sessions.get(device_id)
        if not session_id:
            return False
        self._stop_requested.add(session_id)
        session = self.store.sessions.get(session_id)
        name = session.target.name if session else "session"
        if session:
            self._apply_session_step(session, "Stopping")
        self.add_log("warning", f"Stopping session · {name} ({reason})", device_id)
        return True

    @Slot(str)
    def disconnectDevice(self, device_id: str) -> None:
        if device_id in self._connecting_ids:
            self.cancelConnect(device_id)
            return
        worker = self._workers.get(device_id)
        if not worker or device_id in self._disconnecting_ids:
            return
        if device_id == self._selected_device_id:
            self.stopPreview()
        self._disconnecting_ids.add(device_id)
        if self._abort_active_session(device_id, "Disconnect"):
            # Stop what the telescope is doing before dropping the link. Both
            # commands jump the worker queue ahead of the interrupted session.
            worker.send("stop_all")
        self._notify_devices()

        def done(ok: bool, result: Any) -> None:
            self._disconnecting_ids.discard(device_id)
            self._set_activity(device_id, "")
            self._device_telemetry.pop(device_id, None)
            self._telemetry_updated.pop(device_id, None)
            self._hold_session_capture.discard(device_id)
            self._pending_session_finish.pop(device_id, None)
            self._device_lights.pop(device_id, None)
            self._device_indicators.pop(device_id, None)
            self.add_log("info" if ok else "error", "Disconnected" if ok else str(result), device_id)
            self._toast("Telescope disconnected" if ok else "Disconnect failed", "info" if ok else "error", "" if ok else str(result))
            self._disarm_scheduler_if_offline()
            self._notify_devices()

        worker.disconnect_device(done)

    @Slot(str, str)
    def deviceAction(self, device_id: str, operation: str) -> None:
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        device = self._device_by_id(device_id)
        if operation in {"track", "sky_track"} and (not device or not device.location_configured):
            message = "Set an observing location in Settings before starting tracking"
            self.add_log("warning", message, device_id)
            self._toast("Tracking needs an observing location", "warning", message)
            return
        camera = device.camera.value if device and hasattr(device.camera, "value") else str(device.camera if device else "")
        if operation in {"autofocus", "infinity"} and camera == Camera.WIDE.value:
            self._toast("Focus is only available on the tele camera", "warning")
            return
        shooting_mode = self._device_telemetry.get(device_id, {}).get("shooting_mode")
        required_mode = (
            1 if operation in {"photo", "burst_start", "record_start", "timelapse_start"}
            else 2 if operation in {"calibrate", "polar", "track", "sky_track", "stack", "infinity"}
            else None
        )
        if required_mode is not None and shooting_mode != required_mode:
            mode_name = "PHOTO" if required_mode == 1 else "DSO"
            self._toast(f"Select {mode_name} mode before running this command", "warning")
            return
        if operation == "autofocus" and shooting_mode not in {1, 2}:
            self._toast("Select PHOTO or DSO mode before focusing", "warning")
            return
        if operation == "sky_track":
            sky = self._sky_target
            if sky is None or sky.ra_hours is None or sky.dec_degrees is None:
                self._toast("Select a sky-map target first", "warning")
                return
        photo_focus = operation == "autofocus" and shooting_mode == 1
        self._begin_activity(device_id, operation)

        label = _ACTION_LABELS.get(operation, operation.replace("_", " ").title())
        dropping = operation in {"reboot", "power_down"}
        if dropping:
            self._abort_active_session(device_id, label)

        def done(ok: bool, result: Any) -> None:
            self._complete_activity(device_id, operation, ok)
            if ok and operation == "photo_mode":
                self._on_telemetry(device_id, {"shooting_mode": 1, "shooting_tech": 1})
                self._schedule_camera_param_refresh(device_id)
            elif ok and operation in {"photo", "wide_photo"}:
                self._on_telemetry(device_id, {"shooting_mode": 1, "shooting_tech": 1, "photo_primed": True})
            elif ok and operation in {"burst_start", "record_start", "timelapse_start"}:
                tech = {"burst_start": 3, "record_start": 4, "timelapse_start": 5}[operation]
                self._on_telemetry(device_id, {"shooting_mode": 1, "shooting_tech": tech, "photo_primed": False})
            elif ok and (
                operation in {"astro_mode", "calibrate", "polar", "track", "sky_track", "stack", "infinity"}
                or (operation == "autofocus" and not photo_focus)
            ):
                self._on_telemetry(device_id, {"shooting_mode": 2, "shooting_tech": 0, "photo_primed": False})
                if operation == "astro_mode":
                    self._schedule_camera_param_refresh(device_id)
            elif ok and operation == "stop_goto":
                self._on_telemetry(device_id, {"tracking_state": "idle", "goto_state": "idle"})
            if ok and operation in {"lights_on", "lights_off"}:
                self._device_lights[device_id] = operation == "lights_on"
                self._notify_devices()
            if ok and operation in {"indicator_on", "indicator_off"}:
                self._device_indicators[device_id] = operation == "indicator_on"
                self._notify_devices()
            self.commandFeedback.emit(device_id, operation, bool(ok))
            if ok:
                self.add_log("success", f"{label} acknowledged", device_id)
                self._toast(label, "success", _ACTION_DETAILS.get(operation, ""))
            else:
                self.add_log("error", f"{label} failed: {result}", device_id)
                self._toast(f"{label} failed", "error", str(result))

        payload: dict[str, Any] = {}
        if operation == "track":
            session = self._current_session_view or {}
            name = ""
            if session.get("device_id") == device_id:
                name = str(session.get("target_name") or "")
            payload = {"args": [name or "Live tap"]}
        elif operation == "sky_track":
            sky = self._sky_target
            if sky is None or sky.ra_hours is None or sky.dec_degrees is None:
                self._toast("Select a sky-map target first", "warning")
                return
            payload = {
                "args": [float(sky.ra_hours), float(sky.dec_degrees), str(sky.name or "Sky map target")],
            }
        elif operation == "stack":
            camera = device.camera.value if device and hasattr(device.camera, "value") else "tele"
            payload = {"args": [camera]}
        worker_operation = operation
        if photo_focus:
            worker_operation = "normal_autofocus"
        elif operation == "photo":
            camera = device.camera.value if device and hasattr(device.camera, "value") else "tele"
            worker_operation = "wide_photo" if str(camera).lower() == "wide" else "photo"
            self._sync_worker_camera(device_id, str(camera))
        worker.send(worker_operation, payload, callback=self._with_pending(device_id, operation, done))
        if dropping:
            self._drop_device_link(device_id)

    @Slot("QVariant")
    def trackSkyTarget(self, web_raw: Any) -> None:
        device_id = str(self._selected_device_id or "")
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            self._toast("Connect a telescope before tracking a sky-map target", "warning")
            return
        if self._active_sessions.get(device_id):
            self._toast("A session is already running on this telescope", "warning")
            return
        telemetry = self._device_telemetry.get(device_id) or {}
        if self._pending_actions.get(device_id):
            self._toast("Telescope is busy", "warning")
            return
        if telemetry.get("goto_state") in ("running", "solving", "stopping"):
            self._toast("Telescope is already slewing", "warning")
            return
        if telemetry.get("capture_active") or telemetry.get("capture_state") == "running":
            self._toast("Telescope is capturing", "warning")
            return
        activity = self._device_activity.get(device_id) or ""
        if activity and activity != "goto":
            self._toast("Telescope is busy", "warning")
            return
        try:
            target = parse_sky_web_target(self._snapshot_web_raw(web_raw))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            message = str(exc) or "Select a target in the sky map"
            self._toast("Select a sky-map target first", "warning", message)
            return
        self._set_sky_target(target)
        self.deviceAction(device_id, "sky_track")

    @Slot(str, float, float)
    def joystick(self, device_id: str, angle: float, speed: float) -> None:
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        vector = (float(angle), max(0.0, min(1.0, float(speed))))
        if device_id in self._joystick_inflight:
            self._joystick_pending[device_id] = vector
            return
        self._send_joystick(device_id, vector)

    def _send_joystick(self, device_id: str, vector: tuple[float, float]) -> None:
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        self._joystick_inflight.add(device_id)

        def done(_ok: bool, _result: Any) -> None:
            self._joystick_inflight.discard(device_id)
            pending = self._joystick_pending.pop(device_id, None)
            if pending is not None:
                self._send_joystick(device_id, pending)

        worker.send("joystick", {"args": list(vector)}, done)

    @Slot(str)
    def stopMotors(self, device_id: str) -> None:
        self._joystick_pending.pop(device_id, None)
        worker = self._workers.get(device_id)
        if worker and worker.connected:
            worker.send("stop_motors")

    @Slot(str, float, float)
    def joystickNudge(self, device_id: str, angle: float, speed: float) -> None:
        self._joystick_pending.pop(device_id, None)
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        vector = (float(angle), max(0.0, min(1.0, float(speed))))
        worker.send("joystick_nudge", {"args": list(vector)})

    @Slot(str, float, float)
    @Slot(str, float, float, str)
    def centerOnTap(self, device_id: str, nx: float, ny: float, diag: str = "") -> None:
        """Slew so the tapped wide-view pixel is sent as Dual Lenses Locating.

        Cmd 14009 uses 1920×1080 wide-camera pixels and puts that point on the
        tele camera. PictureMatching must not be added on top; live taps showed
        that shift turning a left-side click into a near-centre command.
        """
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        if device_id != self._selected_device_id or not self._preview_playing:
            return
        if not self._preview_wide_playing:
            self._toast(
                "Double-click centering needs the wide camera",
                "warning",
                "Wait for the wide stream, then double-click the target on the wide view",
            )
            return
        nx = max(0.0, min(1.0, float(nx)))
        ny = max(0.0, min(1.0, float(ny)))
        if device_id in self._center_tap_inflight:
            self._center_tap_pending[device_id] = (nx, ny, diag)
            return
        fov_h, fov_v, _camera = self._device_fov(device_id, Camera.WIDE)
        if diag:
            self.add_log("debug", f"Center tap map {diag}", device_id)

        self._center_tap_inflight.add(device_id)
        token = self._center_tap_token.get(device_id, 0) + 1
        self._center_tap_token[device_id] = token
        QTimer.singleShot(8000, lambda did=device_id, current=token: self._finish_center_tap(did, current, False))

        def done(ok: bool, result: Any) -> None:
            if not ok:
                self.add_log("error", f"Center on tap failed: {result}", device_id)
                self._finish_center_tap(device_id, token, False)
                return
            detail = result if isinstance(result, dict) else {}
            if detail.get("ok") is False:
                self.add_log("error", "Center on tap failed", device_id)
                self._finish_center_tap(device_id, token, False)

        worker.send("center_tap", {"args": [nx, ny, fov_h, fov_v]}, done)

    def _finish_center_tap(self, device_id: str, token: int | None = None, confirmed: bool = True) -> None:
        if token is not None and token != self._center_tap_token.get(device_id):
            return
        if device_id not in self._center_tap_inflight:
            return
        self._center_tap_inflight.discard(device_id)
        self._center_tap_token[device_id] = self._center_tap_token.get(device_id, 0) + 1
        pending = self._center_tap_pending.pop(device_id, None)
        if pending is None:
            if confirmed:
                self._toast("Target centered", "success", "Press TRACK to start sidereal tracking, then STACK")
            return
        nx, ny, diag = pending
        QTimer.singleShot(0, lambda: self.centerOnTap(device_id, nx, ny, diag))

    @Slot(str, int)
    def manualFocus(self, device_id: str, direction: int) -> None:
        device = self._device_by_id(device_id)
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        camera = device.camera.value if device and hasattr(device.camera, "value") else str(device.camera if device else "")
        if camera == Camera.WIDE.value:
            self._toast("Focus is only available on the tele camera", "warning")
            return
        action = "focus_near" if direction else "focus_far"
        worker.send("manual_focus", {"args": [direction]}, self._with_pending(device_id, action))

    @Slot(str)
    def stopDevice(self, device_id: str) -> None:
        self._request_device_stop(device_id, "STOP ALL", "stop_all")

    @Slot(str)
    def stopSession(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            return
        if session.status != SessionStatus.RUNNING:
            self._toast("This session is not running", "warning")
            return
        if self._active_sessions.get(session.device_id) != session.id:
            self._toast("This session is not the active run on that telescope", "warning")
            return
        if self._pending_actions.get(session.device_id) in _STOP_ACTIONS:
            return
        self._request_device_stop(session.device_id, "STOP SESSION", "stop_session")

    def _request_device_stop(self, device_id: str, reason: str, action: str) -> None:
        worker = self._workers.get(device_id)
        if not worker:
            return
        detail = self._initial_stop_detail(device_id)
        self._abort_active_session(device_id, reason)
        if not worker.connected:
            if device_id == self._selected_device_id:
                self.stopPreview()
            self.add_log("warning", "Stop skipped; telescope is not connected", device_id)
            return
        self._begin_activity(device_id, action)
        self._set_pending_detail(device_id, detail)

        def done(ok: bool, result: Any) -> None:
            self._complete_activity(device_id, action, ok)
            pending_finish = self._pending_session_finish.pop(device_id, None)
            if pending_finish:
                self._finalize_session(*pending_finish)
            if worker and device_id not in self._active_sessions:
                worker.busy = False
                worker.availabilityChanged.emit()
            self.add_log(
                "warning" if ok else "error", "Stop commands sent" if ok else str(result), device_id
            )
            if ok and self._telemetry_capturing(device_id):
                self.add_log("warning", "Telescope is still stacking after the stop command", device_id)
                self._toast("Capture may still be running", "warning", "Use STOP ALL if stacking continues")

        worker.send("stop_all", callback=self._with_pending(device_id, action, done))

    @Slot(str)
    def copyText(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self._toast("Copied to clipboard", "success")

    def bindWindowFrame(self, hook) -> None:
        self._window_frame_hook = hook
        self._flush_window_frame()

    @Slot(str, str, str)
    def applyWindowFrame(self, caption: str, border: str, text: str) -> None:
        self._pending_window_frame = (caption, border, text)
        self._flush_window_frame()

    def _flush_window_frame(self) -> None:
        hook = self._window_frame_hook
        colors = self._pending_window_frame
        if hook is None or not colors:
            return
        try:
            hook(*colors)
        except Exception:
            pass

    @Slot(result=str)
    def suggestedDeviceName(self) -> str:
        count = 0 if self._needs_first_device() else len(self._devices)
        return default_device_name(count)

    @Slot(str, result=bool)
    def addDevice(self, payload: str) -> bool:
        current = next((item for item in self._devices if item.id == self._selected_device_id), None)
        claim_first = self._needs_first_device()
        try:
            values = json.loads(payload or "{}")
            timezone_name, latitude, longitude = self._resolved_location(
                values.get("timezone_name", current.timezone_name if current else "UTC"),
                values.get("latitude", current.latitude if current else 0),
                values.get("longitude", current.longitude if current else 0),
            )
            if not timezone_name:
                raise ValueError("A timezone is required")
            if not has_site_coordinates(latitude, longitude):
                raise ValueError("Choose a timezone from the list, or press Enter to look up a city")
            model = current.model if current else DeviceModel.DWARF_3
            if values.get("model"):
                model = DeviceModel(values["model"])
            try:
                wifi_mode = WifiMode(str(values.get("wifi_mode") or WifiMode.AUTO).lower())
            except ValueError:
                wifi_mode = WifiMode.AUTO
            ssid = str(values.get("wifi_ssid") or "").strip()
            if wifi_mode == WifiMode.AP:
                ssid = ""
            requested_color = str(values.get("color") or "").strip()
            color = (
                normalize_device_color(requested_color)
                if requested_color
                else next_device_color([] if claim_first else (item.color for item in self._devices))
            )
            name = str(values.get("name") or "").strip()
            if not name:
                raise ValueError("A telescope name is required")
            if claim_first:
                placeholder = current or self._devices[0]
                updated = replace(
                    placeholder,
                    name=name,
                    color=color,
                    model=model,
                    ip_address=str(values.get("ip_address") or "").strip(),
                    timezone_name=timezone_name,
                    latitude=latitude,
                    longitude=longitude,
                    location_configured=has_site_coordinates(latitude, longitude),
                    observing_day_cutoff_hour=self._cutoff_hour(),
                    stellarium_url=self._settings.stellarium_url,
                    wifi_mode=wifi_mode,
                    wifi_ssid=ssid,
                    ble_password=str(values.get("ble_password") or "DWARF_12345678"),
                )
                if not self._commit_device(placeholder, updated):
                    return False
                self._selected_device_id = updated.id
                self._persist_last_device_id(updated.id)
                self._notify_devices()
                self.durationSuggestionChanged.emit()
                self.clockChanged.emit()
                self._toast("Device added", "success")
                return True
            device = Device(
                name=name,
                color=color,
                model=model,
                ip_address=str(values.get("ip_address") or "").strip(),
                timezone_name=timezone_name,
                latitude=latitude,
                longitude=longitude,
                location_configured=has_site_coordinates(latitude, longitude),
                observing_day_cutoff_hour=self._cutoff_hour(),
                stellarium_url=self._settings.stellarium_url,
                wifi_mode=wifi_mode,
                wifi_ssid=ssid,
                ble_password=str(values.get("ble_password") or "DWARF_12345678"),
            )
            self.store.devices.save(device)
            self._devices.append(device)
            self._create_worker(device)
            self._selected_device_id = device.id
            self._persist_last_device_id(device.id)
            self._notify_devices()
            self.durationSuggestionChanged.emit()
            self.clockChanged.emit()
            self._toast("Device added", "success")
            return True
        except Exception as exc:
            self._toast(f"Could not add device: {exc}", "error")
            return False

    @Slot(str)
    def deleteDevice(self, device_id: str) -> None:
        if len(self._devices) <= 1:
            self._toast("Keep at least one telescope profile", "warning")
            return
        if device_id in self._active_sessions:
            self._toast("Stop the running session before removing this telescope", "warning")
            return
        worker = self._workers.pop(device_id, None)
        self._release_worker(worker)
        session_ids = [item.id for item in self.store.sessions.all() if item.device_id == device_id]
        history_ids = [item.id for item in self.store.history.all() if item.device_id == device_id]
        for session_id in session_ids:
            self.store.sessions.delete(session_id)
        for record_id in history_ids:
            self.store.history.delete(record_id)
        self.store.devices.delete(device_id)
        old_ids = [item.id for item in self._devices]
        self._devices = [item for item in self._devices if item.id != device_id]
        self._active_sessions.pop(device_id, None)
        self._pending_actions.pop(device_id, None)
        self._pending_details.pop(device_id, None)
        self._device_activity.pop(device_id, None)
        self._device_telemetry.pop(device_id, None)
        self._telemetry_updated.pop(device_id, None)
        self._hold_session_capture.discard(device_id)
        self._pending_session_finish.pop(device_id, None)
        self._device_lights.pop(device_id, None)
        self._device_indicators.pop(device_id, None)
        if self._selected_device_id == device_id:
            idx = old_ids.index(device_id)
            neighbor = old_ids[idx - 1] if idx > 0 else (old_ids[idx + 1] if idx + 1 < len(old_ids) else "")
            remaining = {item.id for item in self._devices}
            self._selected_device_id = neighbor if neighbor in remaining else self._devices[0].id
            self._persist_last_device_id(self._selected_device_id)
        self._notify_devices()
        self.durationSuggestionChanged.emit()
        self._emit_sessions_changed()
        if history_ids:
            self.historyChanged.emit()
        extra = []
        if session_ids:
            extra.append(f"{len(session_ids)} session{'s' if len(session_ids) != 1 else ''}")
        if history_ids:
            extra.append(f"{len(history_ids)} history record{'s' if len(history_ids) != 1 else ''}")
        detail = "Removed " + " and ".join(extra) if extra else ""
        self._toast("Device removed", "success", detail)

    def _normalize_ids(self, ids: Any) -> list[str]:
        if ids is None:
            return []
        if isinstance(ids, str):
            return [ids] if ids else []
        values: list[str] = []
        seen: set[str] = set()
        for item in ids:
            value = str(item or "").strip()
            if value and value not in seen:
                seen.add(value)
                values.append(value)
        return values

    @Slot(list)
    @Slot("QVariantList")
    def deleteTemplates(self, template_ids: list) -> None:
        to_delete: set[str] = set()
        for template_id in self._normalize_ids(template_ids):
            template = self.store.templates.get(template_id)
            if not template:
                continue
            group_id = template.mosaic.group_id
            if group_id:
                for item in self.store.templates.all():
                    if item.mosaic.group_id == group_id:
                        to_delete.add(item.id)
            else:
                to_delete.add(template_id)
        if not to_delete:
            return
        for item_id in to_delete:
            self.store.templates.delete(item_id)
        self.templatesChanged.emit()
        count = len(to_delete)
        self._toast(f"Deleted {count} template{'s' if count != 1 else ''}", "success")

    @Slot(str)
    def skipSession(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session or session.status != SessionStatus.PLANNED:
            self._toast("Only planned sessions can be skipped", "warning")
            return
        self.store.transition(session_id, SessionStatus.SKIPPED, current_step="Skipped")
        self._emit_sessions_changed()

    @Slot(str)
    def resetSession(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            return
        if session.status == SessionStatus.RUNNING:
            self._toast("Stop the running session first", "warning")
            return
        if session.status == SessionStatus.PLANNED:
            self._toast("This session is already planned", "info")
            return
        saved = self._save_session(replace(
            session,
            status=SessionStatus.PLANNED,
            current_step="Waiting",
            actual_started_at=None,
            actual_ended_at=None,
            outcome="",
        ))
        self._sequence_mosaic_group(saved, notify=True)
        self._toast("Session reset", "success")

    @Slot(str, str)
    def setLiveCamera(self, device_id: str, camera: str) -> None:
        current = self._device_by_id(device_id)
        choice = str(camera or "tele").strip().lower()
        if choice not in {"tele", "wide"}:
            choice = "tele"
        if current.model == DeviceModel.DWARF_MINI:
            choice = "tele"
        if current.camera != Camera(choice):
            updated = replace(current, camera=Camera(choice))
            self.store.devices.save(updated)
            self._devices = [updated if item.id == updated.id else item for item in self._devices]
            self._notify_devices()
        self._sync_worker_camera(device_id, choice)
        self.refreshCameraParams(device_id)

    def _sync_worker_camera(self, device_id: str, camera: str) -> None:
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        choice = str(camera or "tele").strip().lower()
        if choice not in {"tele", "wide"}:
            return
        worker.send("set_camera", {"args": [choice]})

    @Slot(str, str, str)
    def setCameraParam(self, device_id: str, name: str, value: str) -> None:
        device = self._device_by_id(device_id)
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        camera = device.camera.value if hasattr(device.camera, "value") else str(device.camera)
        if name == "focus" and camera == Camera.WIDE.value:
            self._toast("Focus is only available on the tele camera", "warning")
            return
        shooting_mode = self._device_telemetry.get(device_id, {}).get("shooting_mode")
        if name in {"exposure", "gain", "count", "stack_format"} and shooting_mode not in {1, 2}:
            self._toast("Select PHOTO or DSO mode before changing camera settings", "warning")
            return
        if name in {"burst_count", "burst_interval", "timelapse_interval", "timelapse_duration"} and shooting_mode != 1:
            self._toast("Select PHOTO mode before changing burst or timelapse settings", "warning")
            return
        model_id = {DeviceModel.DWARF_II: "2", DeviceModel.DWARF_3: "3", DeviceModel.DWARF_MINI: "5"}.get(device.model, "3")
        if name == "exposure":
            operation = "set_photo_exposure" if shooting_mode == 1 else "set_exposure"
            args = [firmware_exposure_name(value), model_id, camera]
        elif name == "focus":
            try:
                operation, args = "set_focus", [int(round(float(value)))]
            except (TypeError, ValueError):
                self._toast("Focus must be a number", "error")
                return
        elif name == "gain":
            operation = "set_photo_gain" if shooting_mode == 1 else "set_gain"
            args = [int(value), model_id, camera] if shooting_mode == 1 else [int(value), camera]
        elif name == "ir":
            if camera == Camera.WIDE.value:
                return
            operation, args = "set_ir", [value]
        elif name == "wb_preset":
            operation, args = "set_wb_preset", [value]
        elif name == "wb":
            operation, args = "set_wb", [int(value), 0]
        elif name in {"brightness", "contrast", "saturation", "hue", "sharpness"}:
            operation, args = f"set_{name}", [int(value)]
        elif name == "burst_count":
            operation, args = "set_burst_count", [int(value)]
        elif name == "burst_interval":
            operation, args = "set_burst_interval", [value]
        elif name == "timelapse_interval":
            operation, args = "set_timelapse_interval", [value]
        elif name == "timelapse_duration":
            operation, args = "set_timelapse_duration", [value]
        elif name == "stack_format":
            operation, args = "set_stack_format", [int(value)]
        elif name == "count":
            operation, args = "set_count", [int(value), camera]
        elif name == "auto_calibration":
            operation, args = "set_auto_calibration", [value.strip().lower() in {"1", "true", "yes", "on"}]
        else:
            return

        def done(ok: bool, result: Any) -> None:
            self._toast(
                f"{name.replace('_', ' ').title()} set" if ok else str(result),
                "success" if ok else "error",
            )
            if ok:
                QTimer.singleShot(150, lambda did=device_id: self.refreshCameraParams(did))

        worker.send(
            operation,
            {"args": args},
            self._with_pending(device_id, "set_focus", done) if name == "focus" else done,
        )

    def _album_dir(self) -> Path:
        folder = self.store.root / "album"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _emit_media(self, items: bool = False) -> None:
        self.mediaChanged.emit()
        if items:
            self.mediaItemsChanged.emit()

    def _set_media_busy(self, busy: str) -> None:
        if self._album_busy == busy:
            return
        self._album_busy = busy
        self._emit_media()

    def _set_media_status(self, status: str) -> None:
        text = str(status or "")
        if self._media_status == text:
            return
        self._media_status = text
        self._emit_media()

    def _media_signature(self, items: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...]:
        return tuple(
            (
                item.get("id"),
                item.get("thumbnail_url"),
                item.get("image_url"),
                item.get("downloaded"),
                item.get("kind"),
            )
            for item in items
        )

    def _media_file_url(self, path: str) -> str:
        if not path:
            return ""
        return QUrl.fromLocalFile(str(Path(path).resolve())).toString(QUrl.ComponentFormattingOption.FullyEncoded)

    def _is_device_media_path(self, path: str) -> bool:
        text = str(path or "").replace("\\", "/").strip()
        return text.startswith("/") or text.startswith("sdcard") or "/" in text.strip("/")

    def _local_name_for_remote(self, file_path: str) -> str:
        parts = [part for part in Path(str(file_path).replace("\\", "/")).parts if part not in {"/", "\\"}]
        if len(parts) >= 2:
            return f"{parts[-2]}_{parts[-1]}"
        return parts[-1] if parts else "stacked.jpg"

    def _astro_details(self, entry: dict[str, Any]) -> dict[str, Any]:
        for key in ("astroImageDetails", "astroMosaicImageDetails", "astroMultiImageDetails"):
            details = entry.get(key)
            if isinstance(details, dict) and details:
                return details
        return {}

    def _format_media_time(self, unix_ts: Any) -> str:
        try:
            value = int(unix_ts)
        except (TypeError, ValueError):
            return ""
        if value <= 0:
            return ""
        try:
            return datetime.fromtimestamp(value).strftime("%d/%m/%Y %H:%M")
        except (OSError, OverflowError, ValueError):
            return ""

    def _local_album_paths(self) -> dict[str, Path]:
        found: dict[str, Path] = {}
        for path in self._album_dir().iterdir():
            if path.is_file() and path.suffix.lower() in LOCAL_ALBUM_SUFFIXES:
                found[path.name] = path
        return found

    def _match_local_album_file(
        self,
        name: str,
        remote: str,
        local_files: dict[str, Path],
    ) -> Path | None:
        candidates = [
            str(name or "").strip(),
            Path(str(remote or "").replace("\\", "/")).name,
            self._local_name_for_remote(remote or name),
        ]
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            local = local_files.get(candidate)
            if local:
                return local
        return None

    def _normalize_remote_item(
        self,
        entry: dict[str, Any],
        ip: str,
        local_files: dict[str, Path],
        source: str,
    ) -> dict[str, Any] | None:
        thumb = str(entry.get("thumbnailPath") or "").strip()
        remote = str(entry.get("filePath") or "").strip()
        name = str(entry.get("fileName") or "").strip()
        if not thumb and not remote and not name:
            return None
        details = self._astro_details(entry) if (
            source == "astro"
            or album_is_astro_media(remote or thumb, name, entry.get("mediaType"))
        ) else {}
        params = details.get("params") if isinstance(details.get("params"), dict) else {}
        kind = album_media_kind(remote or thumb, name, entry.get("mediaType"))
        is_video = kind == "video" or album_is_video_name(remote or thumb, name)
        target = str(
            details.get("target")
            or name
            or Path(str(remote or thumb).replace("\\", "/")).name
            or "Untitled"
        )
        local = self._match_local_album_file(name, remote or thumb, local_files)
        local_url = self._media_file_url(str(local)) if local else ""
        file_available = entry.get("fileAvailable", True) is not False
        thumb_url = album_http_url(ip, thumb) if thumb and ip else ""
        image_url = album_http_url(ip, remote) if remote and ip and file_available else ""
        if not image_url:
            image_url = thumb_url
        if local_url and not is_video:
            thumb_url = local_url
            image_url = local_url
        elif local_url:
            image_url = local_url
        try:
            media_type = int(entry.get("mediaType"))
        except (TypeError, ValueError):
            media_type = 0
        try:
            sub_type = int(entry.get("astroSubType") or entry.get("subType") or 0)
        except (TypeError, ValueError):
            sub_type = 0
        try:
            cam_id = int(entry.get("camId"))
        except (TypeError, ValueError):
            cam_id = -1
        try:
            modified = int(entry.get("modificationTime") or 0)
        except (TypeError, ValueError):
            modified = 0
        return {
            "id": remote or thumb or name,
            "source": source,
            "kind": kind,
            "target": target,
            "file_name": name or Path(str(remote or thumb).replace("\\", "/")).name,
            "file_path": remote or name,
            "thumbnail_path": thumb,
            "thumbnail_url": thumb_url or (image_url if not is_video else ""),
            "image_url": image_url or thumb_url,
            "date": self._format_media_time(entry.get("modificationTime")),
            "modification_time": modified,
            "exposure": str(params.get("exp") or ""),
            "gain": str(params.get("gain") or ""),
            "ir_filter": str(params.get("filter") or ""),
            "camera": "wide" if cam_id == 1 else ("tele" if cam_id == 0 else ""),
            "local_path": str(local) if local else "",
            "downloaded": bool(local),
            "media_type": media_type,
            "sub_type": sub_type,
        }

    def _normalize_astro_item(self, entry: dict[str, Any], ip: str, local_files: dict[str, Path]) -> dict[str, Any] | None:
        return self._normalize_remote_item(entry, ip, local_files, "astro")

    def _normalize_still_item(
        self,
        name: str,
        local_files: dict[str, Path],
        ip: str = "",
        directory: str = "",
    ) -> dict[str, Any]:
        remote = str(name or "")
        thumb = ""
        if directory and name:
            folder = str(directory).rstrip("/").replace("\\", "/")
            remote = f"{folder}/{name}"
            thumb = f"{folder}/Thumbnail/{name}"
        item = self._normalize_remote_item(
            {
                "fileName": name,
                "filePath": remote,
                "thumbnailPath": thumb,
                "mediaType": 0,
            },
            ip,
            local_files,
            "stills",
        )
        return item or {
            "id": name,
            "source": "stills",
            "kind": album_media_kind(remote, name),
            "target": name,
            "file_name": name,
            "file_path": name,
            "thumbnail_path": "",
            "thumbnail_url": "",
            "image_url": "",
            "date": "",
            "modification_time": 0,
            "exposure": "",
            "gain": "",
            "ir_filter": "",
            "camera": "",
            "local_path": "",
            "downloaded": False,
            "media_type": 0,
            "sub_type": 0,
        }

    def _normalize_local_item(self, path: Path) -> dict[str, Any]:
        url = self._media_file_url(str(path))
        kind = album_media_kind(str(path), path.name)
        is_video = kind == "video" or album_is_video_name(str(path), path.name)
        try:
            mtime = int(path.stat().st_mtime)
        except OSError:
            mtime = 0
        return {
            "id": str(path),
            "source": "local",
            "kind": kind,
            "target": path.stem,
            "file_name": path.name,
            "file_path": str(path),
            "thumbnail_path": "",
            "thumbnail_url": "" if is_video else url,
            "image_url": url,
            "date": self._format_media_time(mtime),
            "modification_time": mtime,
            "exposure": "",
            "gain": "",
            "ir_filter": "",
            "camera": "",
            "local_path": str(path),
            "downloaded": True,
            "media_type": 0,
            "sub_type": 0,
        }

    def _select_media_id(self, item_id: str) -> None:
        if item_id and any(item.get("id") == item_id for item in self._media_items):
            self._media_selected_id = item_id
            local = next((item.get("local_path") for item in self._media_items if item.get("id") == item_id), "")
            if local:
                self._album_path = str(local)
        elif self._media_items:
            self._media_selected_id = str(self._media_items[0].get("id") or "")
        else:
            self._media_selected_id = ""

    def _replace_media_items(self, items: list[dict[str, Any]], keep_id: str = "") -> None:
        items = [item for item in items if item]
        items.sort(key=lambda item: int(item.get("modification_time") or 0), reverse=True)
        changed = self._media_signature(items) != self._media_signature(self._media_items)
        self._media_items = items
        self._select_media_id(keep_id or self._media_selected_id)
        if changed:
            self._media_status = ""
        self._emit_media(items=changed)

    def _clear_media(self, status: str = "") -> None:
        self._media_request_id += 1
        self._media_items = []
        self._media_selected_id = ""
        self._album_items = []
        self._album_busy = ""
        self._media_download_queue = []
        self._media_download_batch = 0
        self._media_download_ok = 0
        self._media_download_failed = 0
        self._media_status = str(status or "")
        self._emit_media(items=True)

    def _begin_media_request(self, device_id: str, source: str) -> int:
        self._media_request_id += 1
        self._media_download_queue = []
        self._media_download_batch = 0
        self._media_download_ok = 0
        self._media_download_failed = 0
        self._media_device_id = device_id
        self._media_source = source
        return self._media_request_id

    def _media_request_current(self, request_id: int, device_id: str, source: str) -> bool:
        return (
            request_id == self._media_request_id
            and self._media_device_id == device_id
            and self._media_source == source
        )

    def _media_can_list(self, device_id: str) -> bool:
        worker = self._workers.get(device_id)
        return bool(worker and worker.connected)

    def _media_offline_status(self, device_id: str) -> str:
        device = next((item for item in self._devices if item.id == device_id), None)
        ip = str(getattr(device, "ip_address", "") or "").strip()
        if not ip:
            return "Set the telescope IP in Settings, then refresh to browse sessions on the device."
        return "Connect this telescope to browse its album."

    def _camera_mode_id(self, device_id: str) -> int:
        mode = self._device_telemetry.get(device_id, {}).get("shooting_mode")
        try:
            return int(mode) if mode is not None else 1
        except (TypeError, ValueError):
            return 1

    def _camera_model_id(self, device_id: str) -> str:
        device = next((item for item in self._devices if item.id == device_id), None)
        return {DeviceModel.DWARF_II: "2", DeviceModel.DWARF_3: "3", DeviceModel.DWARF_MINI: "5"}.get(
            getattr(device, "model", None),
            "3",
        )

    def _schedule_camera_param_refresh(self, device_id: str, delay_ms: int = 150) -> None:
        QTimer.singleShot(delay_ms, lambda did=device_id: self.refreshCameraParams(did))

    @Slot(str)
    def refreshCameraParams(self, device_id: str) -> None:
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        mode_id = self._camera_mode_id(device_id)
        model_id = self._camera_model_id(device_id)

        def done(ok: bool, result: Any) -> None:
            if not ok:
                return
            changes = camera_params_to_telemetry(result, model_id)
            if changes:
                self._on_telemetry(device_id, changes)

        worker.send("read_camera", {"args": [mode_id]}, done)

    @Slot(str)
    def setMediaSource(self, source: str) -> None:
        choice = str(source or "astro").strip().lower()
        if choice not in {"astro", "stills", "local"}:
            choice = "astro"
        if self._media_source == choice:
            return
        self._media_source = choice
        self._media_selected_id = ""
        self._media_items = []
        self._media_status = ""
        self._emit_media(items=True)
        self.refreshMedia(self._selected_device_id, True)

    @Slot(str)
    def selectMedia(self, item_id: str) -> None:
        previous = self._media_selected_id
        self._select_media_id(str(item_id or ""))
        if previous != self._media_selected_id:
            self._emit_media()

    @Slot(str)
    @Slot(str, bool)
    def refreshMedia(self, device_id: str, quiet: bool = False) -> None:
        if self._media_source == "local":
            self.listLocalAlbum()
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._clear_media(_MEDIA_LOCKED_STATUS)
            if not quiet:
                self._toast("Can't browse the album while the telescope is capturing", "warning")
            return
        if not self._media_can_list(device_id):
            self._clear_media(self._media_offline_status(device_id))
            if not quiet:
                self._toast("Connect the telescope before listing media", "warning")
            return
        if self._media_source == "stills":
            self.listAlbum(device_id, quiet)
            return
        self.listAstroSessions(device_id, quiet)

    @Slot()
    def listLocalAlbum(self) -> None:
        self._media_request_id += 1
        self._media_download_queue = []
        self._media_download_batch = 0
        self._media_download_ok = 0
        self._media_download_failed = 0
        self._media_source = "local"
        self._media_device_id = ""
        self._set_media_busy("")
        items = [self._normalize_local_item(path) for path in self._local_album_paths().values()]
        self._replace_media_items(items, self._media_selected_id)
        self._set_media_status("" if items else "No downloaded files in the local album yet.")

    @Slot(str)
    @Slot(str, bool)
    def listAstroSessions(self, device_id: str, quiet: bool = False) -> None:
        worker = self._workers.get(device_id)
        device = next((item for item in self._devices if item.id == device_id), None)
        if not worker or not worker.connected or not device or not str(device.ip_address or "").strip():
            self._clear_media(self._media_offline_status(device_id))
            if not quiet:
                self._toast("Connect the telescope before listing sessions", "warning")
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._clear_media(_MEDIA_LOCKED_STATUS)
            if not quiet:
                self._toast("Can't browse the album while the telescope is capturing", "warning")
            return
        request_id = self._begin_media_request(device_id, "astro")
        self._set_media_busy("list")

        def done(ok: bool, result: Any) -> None:
            if not self._media_request_current(request_id, device_id, "astro"):
                return
            self._set_media_busy("")
            if ok and isinstance(result, dict):
                ip = str(result.get("ip") or device.ip_address)
                local_files = self._local_album_paths()
                items = [
                    self._normalize_astro_item(entry, ip, local_files)
                    for entry in (result.get("sessions") or [])
                    if isinstance(entry, dict) and album_path_matches_model(
                        str(entry.get("filePath") or entry.get("thumbnailPath") or ""),
                        device.model,
                    )
                ]
                self._replace_media_items([item for item in items if item], self._media_selected_id)
                if not self._media_items:
                    self._set_media_status("No astro sessions found on this telescope. Finished DSO and manual stacks show up here.")
                elif not quiet:
                    self._toast(f"{len(self._media_items)} astro sessions on telescope", "success")
                return
            self._replace_media_items([])
            self._set_media_status(str(result) if result else "Could not reach the telescope album. Connect it, then tap Refresh.")
            if not quiet:
                self._toast("Astro session list failed", "error", str(result))

        worker.send("astro_sessions_list", {}, done)

    @Slot(str)
    @Slot(str, bool)
    def listAlbum(self, device_id: str, quiet: bool = False) -> None:
        worker = self._workers.get(device_id)
        device = next((item for item in self._devices if item.id == device_id), None)
        if not worker or not worker.connected or not device or not str(device.ip_address or "").strip():
            self._clear_media(self._media_offline_status(device_id))
            if not quiet:
                self._toast("Connect the telescope before listing stills", "warning")
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._clear_media(_MEDIA_LOCKED_STATUS)
            if not quiet:
                self._toast("Can't browse the album while the telescope is capturing", "warning")
            return
        request_id = self._begin_media_request(device_id, "stills")
        self._set_media_busy("list")

        def done(ok: bool, result: Any) -> None:
            if not self._media_request_current(request_id, device_id, "stills"):
                return
            self._set_media_busy("")
            if ok and isinstance(result, dict):
                ip = str(result.get("ip") or device.ip_address)
                local_files = self._local_album_paths()
                entries = [entry for entry in (result.get("sessions") or []) if isinstance(entry, dict)]
                items = [
                    item
                    for entry in entries
                    for item in [self._normalize_remote_item(entry, ip, local_files, "stills")]
                    if item
                ]
                if not items and result.get("files"):
                    directory = str(result.get("directory") or "")
                    items = [
                        self._normalize_still_item(str(name), local_files, ip, directory)
                        for name in (result.get("files") or [])
                    ]
                self._album_items = [{"file": item.get("file_name")} for item in items]
                self._replace_media_items(items, self._media_selected_id)
                if not self._media_items:
                    self._set_media_status("No photos, videos, or bursts found on this telescope.")
                elif not quiet:
                    self._toast(f"{len(self._media_items)} files on telescope", "success")
                return
            self._replace_media_items([])
            self._set_media_status(str(result) if result else "Could not reach the telescope album. Connect it, then tap Refresh.")
            if not quiet:
                self._toast("Album list failed", "error", str(result))

        worker.send("album_camera_list", {}, done)

    @Slot(str, "QVariantList")
    def downloadMediaItems(self, device_id: str, item_ids: list) -> None:
        self._start_media_downloads(device_id, item_ids)

    def _start_media_downloads(self, device_id: str, item_ids: Any) -> None:
        ids = self._normalize_ids(item_ids)
        if not ids:
            return
        if self._album_busy:
            self._toast("Wait for the current media action to finish", "warning")
            return
        if self._media_source == "local":
            self._select_media_id(ids[0])
            self._emit_media()
            return
        if self._media_device_id and self._media_device_id != device_id:
            self._toast("Switch back to the telescope that listed this file before downloading", "warning")
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._toast("Can't download while the telescope is capturing", "warning")
            return
        self._media_download_queue = ids[1:]
        self._media_download_batch = len(ids)
        self._media_download_ok = 0
        self._media_download_failed = 0
        self._download_media_item(device_id, ids[0])

    def _continue_media_download(self, device_id: str) -> None:
        if self._media_download_queue:
            nxt = self._media_download_queue.pop(0)
            self._download_media_item(device_id, nxt)
            return
        batch = self._media_download_batch
        ok = self._media_download_ok
        failed = self._media_download_failed
        self._media_download_batch = 0
        self._media_download_ok = 0
        self._media_download_failed = 0
        self._set_media_busy("")
        if batch > 1:
            if failed and ok:
                self._toast(
                    f"Downloaded {ok} file{'s' if ok != 1 else ''}, {failed} failed",
                    "warning",
                )
            elif ok:
                self._toast(f"Downloaded {ok} file{'s' if ok != 1 else ''}", "success")
            elif failed:
                self._toast("Download failed", "error")

    def _note_media_download(self, ok: bool, success_text: str, detail: str = "") -> None:
        if ok:
            self._media_download_ok += 1
            if self._media_download_batch <= 1:
                self._toast(success_text, "success", detail)
            return
        self._media_download_failed += 1
        if self._media_download_batch <= 1:
            self._toast("Download failed", "error", detail)

    def _download_media_item(self, device_id: str, item_id: str) -> None:
        chosen = str(item_id or "").strip()
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._media_download_queue = []
            self._toast("Can't download while the telescope is capturing", "warning")
            self._continue_media_download(device_id)
            return
        item = next((entry for entry in self._media_items if entry.get("id") == chosen), None)
        remote = str((item or {}).get("file_path") or chosen)
        if self._media_source == "stills" and not self._is_device_media_path(remote):
            self.downloadAlbumPhoto(device_id, str((item or {}).get("file_name") or chosen))
            return
        worker = self._workers.get(device_id)
        if not worker or not remote:
            self._media_download_failed += 1
            if self._media_download_batch <= 1:
                self._toast("Nothing to download", "warning")
            self._continue_media_download(device_id)
            return
        dest = str(self._album_dir())
        request_id = self._media_request_id
        source = self._media_source
        self._set_media_busy("download")

        def done(ok: bool, result: Any) -> None:
            if not self._media_request_current(request_id, device_id, source):
                return
            if ok and isinstance(result, dict) and result.get("path"):
                self._album_path = str(result["path"])
                local_url = self._media_file_url(self._album_path)
                local_files = self._local_album_paths()
                updated = []
                for entry in self._media_items:
                    if entry.get("id") == chosen or entry.get("file_path") == remote:
                        entry = dict(entry)
                        entry["local_path"] = self._album_path
                        entry["downloaded"] = True
                        entry["image_url"] = local_url
                        if entry.get("kind") != "video":
                            entry["thumbnail_url"] = local_url
                    elif entry.get("file_name") in local_files:
                        local = local_files[str(entry.get("file_name"))]
                        entry = dict(entry)
                        entry["local_path"] = str(local)
                        entry["downloaded"] = True
                    updated.append(entry)
                self._media_items = updated
                self._select_media_id(chosen)
                self._note_media_download(True, "Downloaded", Path(self._album_path).name)
                self._emit_media(items=True)
            else:
                self._note_media_download(False, "", str(result))
            self._continue_media_download(device_id)

        worker.send("astro_session_download", {"args": [remote, dest]}, done)

    @Slot(str, str)
    def downloadAlbumPhoto(self, device_id: str, name: str = "") -> None:
        worker = self._workers.get(device_id)
        if not worker:
            self._media_download_failed += 1
            if self._media_download_batch <= 1:
                self._toast("Nothing to download", "warning")
            self._continue_media_download(device_id)
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._media_download_queue = []
            self._toast("Can't download while the telescope is capturing", "warning")
            self._continue_media_download(device_id)
            return
        device = self._device_by_id(device_id)
        camera = device.camera.value if device and hasattr(device.camera, "value") else "tele"
        dest = str(self._album_dir())
        request_id = self._media_request_id
        source = self._media_source
        self._set_media_busy("download")

        def done(ok: bool, result: Any) -> None:
            if not self._media_request_current(request_id, device_id, source):
                return
            if ok and isinstance(result, dict) and result.get("path"):
                self._album_path = str(result["path"])
                chosen = str(result.get("file") or Path(self._album_path).name)
                if not any(item.get("file") == chosen for item in self._album_items):
                    self._album_items = [{"file": chosen}, *self._album_items]
                local_files = self._local_album_paths()
                updated = []
                found = False
                for entry in self._media_items:
                    if entry.get("id") == name or entry.get("file_name") == chosen:
                        entry = dict(entry)
                        entry["local_path"] = self._album_path
                        entry["downloaded"] = True
                        local_url = self._media_file_url(self._album_path)
                        entry["image_url"] = local_url
                        if entry.get("kind") != "video":
                            entry["thumbnail_url"] = local_url
                        found = True
                    updated.append(entry)
                if not found:
                    updated.insert(0, self._normalize_still_item(chosen, local_files))
                self._media_items = updated
                self._select_media_id(chosen)
                self._note_media_download(True, "Photo downloaded", chosen)
                self._emit_media(items=True)
            else:
                self._note_media_download(False, "", str(result))
            self._continue_media_download(device_id)

        worker.send("album_download", {"args": [name, dest, camera]}, done)

    @Slot(list)
    @Slot("QVariantList")
    def deleteMedia(self, item_ids: list) -> None:
        ids = self._normalize_ids(item_ids)
        if not ids:
            return
        if self._album_busy:
            self._toast("Wait for the current media action to finish", "warning")
            return
        if self._media_source == "local":
            self._delete_local_media(ids)
            return
        self._delete_device_media(ids)

    def _delete_local_media(self, item_ids: list[str]) -> None:
        album_dir = self._album_dir()
        wanted = set(item_ids)
        targets: list[Path] = []
        remaining: list[dict[str, Any]] = []
        for item in self._media_items:
            item_id = str(item.get("id") or "")
            if item_id not in wanted:
                remaining.append(item)
                continue
            candidate = str(item.get("local_path") or item.get("file_path") or item_id)
            target = album_local_file_in_dir(album_dir, candidate)
            if target is None:
                remaining.append(item)
                continue
            targets.append(target)
        if not targets:
            self._toast("Nothing to delete from the local album", "warning")
            return
        keep_id = self._media_selected_id if self._media_selected_id not in wanted else ""
        self._replace_media_items(remaining, keep_id)
        self._set_media_status("" if remaining else "No downloaded files in the local album yet.")
        QTimer.singleShot(50, lambda files=list(targets): self._finish_local_album_delete(files))

    def _finish_local_album_delete(self, paths: list[Path]) -> None:
        deleted = 0
        for target in paths:
            if album_local_file_in_dir(self._album_dir(), str(target)) is None:
                continue
            try:
                target.unlink()
            except OSError as exc:
                self._toast("Could not delete file", "error", str(exc))
                continue
            deleted += 1
        if self._media_source == "local":
            self.listLocalAlbum()
        if deleted:
            self._toast(f"Deleted {deleted} file{'s' if deleted != 1 else ''}", "success")

    def _delete_device_media(self, item_ids: list[str]) -> None:
        device_id = self._media_device_id or self._selected_device_id
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._toast("Can't delete from the telescope while it's capturing", "warning")
            return
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            self._toast("Connect the telescope before deleting on-device files", "warning")
            return
        wanted = set(item_ids)
        entries: list[dict[str, Any]] = []
        for item in self._media_items:
            item_id = str(item.get("id") or "")
            if item_id not in wanted:
                continue
            remote = str(item.get("file_path") or item_id)
            if not self._is_device_media_path(remote):
                continue
            entries.append({
                "filePath": remote,
                "fileName": str(item.get("file_name") or ""),
                "mediaType": item.get("media_type") or 0,
                "subType": item.get("sub_type") or 0,
            })
        if not entries:
            self._toast("Those files can't be deleted from the telescope", "warning")
            return
        request_id = self._media_request_id
        source = self._media_source
        self._set_media_busy("delete")

        def done(ok: bool, result: Any) -> None:
            if not self._media_request_current(request_id, device_id, source):
                return
            self._set_media_busy("")
            if ok and isinstance(result, dict):
                deleted = len(result.get("deleted") or [])
                failed = int(result.get("failed") or 0)
                self.refreshMedia(device_id, True)
                if failed and deleted:
                    self._toast(
                        f"Deleted {deleted} file{'s' if deleted != 1 else ''}, {failed} failed",
                        "warning",
                    )
                elif deleted:
                    self._toast(f"Deleted {deleted} file{'s' if deleted != 1 else ''} from telescope", "success")
                return
            self._toast("Album delete failed", "error", str(result))

        worker.send("album_delete", {"args": [entries]}, done)

    @Slot()
    def openAlbumFolder(self) -> None:
        folder = self._album_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder.resolve())))

    @Slot(str)
    def revealMediaFile(self, path: str) -> None:
        target = Path(str(path or self._album_path or "")).expanduser()
        if not target.exists():
            self.openAlbumFolder()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))

    def _resolved_location(self, timezone_name: Any, latitude: Any, longitude: Any) -> tuple[str, float, float]:
        name = str(timezone_name or "").strip()
        try:
            lat = float(latitude)
        except (TypeError, ValueError):
            lat = 0.0
        try:
            lon = float(longitude)
        except (TypeError, ValueError):
            lon = 0.0
        if lat != lat:
            lat = 0.0
        if lon != lon:
            lon = 0.0
        matched = match_timezone(name)
        if matched:
            name = matched["name"]
            if abs(lat) < 1e-9 and abs(lon) < 1e-9 and matched["name"] not in {"UTC", "Etc/UTC"}:
                lat = float(matched["latitude"])
                lon = float(matched["longitude"])
        return name, lat, lon

    @Slot(str, result=bool)
    def saveDevice(self, payload: str) -> bool:
        try:
            values = json.loads(payload)
            current = self._device_by_id(values["id"])
            if "latitude" in values and values["latitude"] is None:
                raise ValueError("Latitude must be a number")
            if "longitude" in values and values["longitude"] is None:
                raise ValueError("Longitude must be a number")
            name = str(values.get("name") or "").strip()
            if not name:
                raise ValueError("A telescope name is required")
            hardware = replace(current.hardware, **{
                key: float(values.get(key, getattr(current.hardware, key)))
                for key in current.hardware.__dataclass_fields__
            })
            timezone_name, latitude, longitude = self._resolved_location(
                values.get("timezone_name", current.timezone_name),
                values.get("latitude", current.latitude),
                values.get("longitude", current.longitude),
            )
            if "observing_day_cutoff_hour" in values or "stellarium_url" in values:
                self._settings = replace(
                    self._settings,
                    observing_day_cutoff_hour=clamp_cutoff_hour(
                        values.get("observing_day_cutoff_hour", self._settings.observing_day_cutoff_hour)
                    ),
                    stellarium_url=normalized_stellarium_url(
                        values.get("stellarium_url", self._settings.stellarium_url)
                    ),
                )
                self.store.save_app_settings(self._settings)
            model = DeviceModel(values["model"])
            camera = Camera(values.get("camera", current.camera))
            if model == DeviceModel.DWARF_MINI:
                camera = Camera.TELE
            updated = replace(
                current,
                name=name,
                model=model,
                ip_address=values["ip_address"].strip(),
                camera=camera,
                color=normalize_device_color(values.get("color", current.color), current.color),
                latitude=latitude,
                longitude=longitude,
                timezone_name=timezone_name,
                location_configured=has_site_coordinates(latitude, longitude),
                stellarium_url=self._settings.stellarium_url,
                wifi_ssid=values.get("wifi_ssid", current.wifi_ssid),
                wifi_password=values.get("wifi_password", current.wifi_password),
                wifi_mode=WifiMode(str(values.get("wifi_mode", current.wifi_mode) or WifiMode.AUTO).lower()),
                ble_password=str(values.get("ble_password", current.ble_password) or "DWARF_12345678"),
                ble_enabled=bool(values.get("ble_enabled", current.ble_enabled)),
                auto_start_preview=bool(values.get("auto_start_preview", current.auto_start_preview)),
                mosaic_pa=parse_mosaic_pa(values["mosaic_pa"]) if "mosaic_pa" in values else current.mosaic_pa,
                observing_day_cutoff_hour=self._cutoff_hour(),
                hardware=hardware,
                capture_defaults=self._capture_defaults_from_payload(values, current.capture_defaults),
            )
            if not self._commit_device(current, updated):
                return False
            for session in self.store.upcoming(updated.id):
                self._save_session(replace(session, planned_duration_seconds=DurationEngine.calculate(session, updated.hardware)))
            self._sequence_colliding_mosaics()
            self._notify_devices()
            self.durationSuggestionChanged.emit()
            self.clockChanged.emit()
            self.appSettingsChanged.emit()
            self._toast("Device saved", "success")
            return True
        except Exception as exc:
            self._toast(f"Could not save device: {exc}", "error")
            return False

    @Slot(str, result=bool)
    def saveObservingLocation(self, payload: str) -> bool:
        try:
            values = json.loads(payload)
            current = self._device_by_id(values.get("id") or self._selected_device_id)
            timezone_name, latitude, longitude = self._resolved_location(
                values.get("timezone_name"),
                values.get("latitude"),
                values.get("longitude"),
            )
            if not timezone_name:
                raise ValueError("A timezone is required")
            if not has_site_coordinates(latitude, longitude):
                raise ValueError("Choose a timezone from the list, or press Enter to look up a city")
            model = current.model
            if values.get("model"):
                model = DeviceModel(values["model"])
            updated = replace(
                current,
                model=model,
                latitude=latitude,
                longitude=longitude,
                timezone_name=timezone_name,
                location_configured=has_site_coordinates(latitude, longitude),
            )
            if not self._commit_device(current, updated):
                return False
            self._notify_devices()
            self.clockChanged.emit()
            self._toast("Observing location saved", "success")
            return True
        except Exception as exc:
            self._toast(f"Could not save location: {exc}", "error")
            return False

    @Slot(str)
    def discoverNearbyDevice(self, payload: str) -> None:
        if self._device_discovery_busy:
            self._toast("Bluetooth discovery is still running", "warning")
            return
        try:
            values = json.loads(payload or "{}")
        except Exception:
            values = {}
        if not isinstance(values, dict):
            values = {}
        ble_password = str(values.get("ble_password") or "DWARF_12345678")
        model = str(values.get("model") or "")
        self._device_discovery_token += 1
        token = self._device_discovery_token
        self._set_device_discovery_busy(True)

        def on_log(message: str, level: str = "info") -> None:
            self._asyncResult.emit(
                "deviceDiscoverLog",
                (True, {"token": token, "level": level, "message": message}),
            )

        def work() -> None:
            try:
                from .device_worker import discover_nearby_dwarfs

                found = discover_nearby_dwarfs(ble_password=ble_password, model=model, on_log=on_log)
                self._asyncResult.emit("deviceDiscover", (True, {"token": token, "devices": found}))
            except InterruptedError:
                self._asyncResult.emit("deviceDiscover", (True, {"token": token, "cancelled": True, "devices": []}))
            except Exception as exc:
                self._asyncResult.emit("deviceDiscover", (False, {"token": token, "error": str(exc)}))

        threading.Thread(target=work, daemon=True, name="dwarf-discover").start()

    @Slot()
    def cancelNearbyDiscovery(self) -> None:
        if not self._device_discovery_busy:
            return
        self._device_discovery_token += 1
        from .device_worker import cancel_nearby_discovery

        cancel_nearby_discovery()
        self._set_device_discovery_busy(False)

    @Slot(str)
    def lookupLocation(self, query: str) -> None:
        text = query.strip()
        if not text:
            self._toast("Enter a city or timezone to search", "warning")
            return
        if self._location_lookup_busy:
            self._toast("Location search is still running", "warning")
            return
        self._set_location_lookup_busy(True)

        def work() -> None:
            try:
                result = resolve_location(text)
            except Exception as exc:
                self._asyncResult.emit("locationLookup", (False, str(exc)))
                return
            if not result:
                self._asyncResult.emit("locationLookup", (False, f"No location match for '{text}'"))
                return
            self._asyncResult.emit("locationLookup", (True, result))

        threading.Thread(target=work, daemon=True).start()

    def _capture_defaults_from_payload(self, values: dict[str, Any], current: CaptureDefaults) -> CaptureDefaults:
        raw = values.get("capture_defaults")
        if not isinstance(raw, dict):
            return current
        return capture_defaults_from_dict({**to_dict(current), **raw})

    def _capture_defaults_for(self, device: Device | None = None) -> CaptureDefaults:
        item = device or self._schedule_device()
        return item.capture_defaults if item is not None else CaptureDefaults()

    def _camera_settings_for(self, device: Device | None = None) -> CameraSettings:
        return camera_settings_from_capture(self._capture_defaults_for(device))

    def _fields_from_payload(
        self,
        values: dict[str, Any],
        existing_mosaic: Mosaic | None = None,
        device: Device | None = None,
    ) -> tuple[Target, CameraSettings, Workflow, Mosaic]:
        target_kind = TargetKind(values.get("target_kind", "equatorial"))
        capture = self._capture_defaults_for(device)
        return (
            Target(
                name=values["target"],
                kind=target_kind,
                ra_hours=float(values["ra"]) if values.get("ra") and target_kind == TargetKind.EQUATORIAL else None,
                dec_degrees=float(values["dec"]) if values.get("dec") and target_kind == TargetKind.EQUATORIAL else None,
                solar_name=values["target"] if target_kind == TargetKind.SOLAR else None,
            ),
            CameraSettings(
                camera=Camera(values.get("camera", "tele")),
                exposure_seconds=float(values.get("exposure", capture.exposure_seconds)),
                gain=int(values.get("gain", capture.gain)),
                frame_count=int(values.get("frame_count", capture.frame_count)),
                binning=int(values.get("binning", 1)),
                ir_filter=values.get("ir_filter", "VIS"),
            ),
            Workflow(
                calibrate=bool(values.get("calibrate", True)),
                autofocus=bool(values.get("autofocus", True)),
                infinite_focus=bool(values.get("infinite_focus", False)),
                polar_align=bool(values.get("polar_align", False)),
                goto=bool(values.get("goto", True)),
                wait_before_seconds=float(values.get("wait_before", 0)),
                wait_after_seconds=float(values.get("wait_after", 10)),
            ),
            Mosaic(
                rows=1 if (existing_mosaic and existing_mosaic.imported_plan) else int(values.get("rows", 1)),
                columns=1 if (existing_mosaic and existing_mosaic.imported_plan) else int(values.get("columns", 1)),
                rotation_degrees=float(values.get("rotation", 0)),
                horizontal_scale=int(values.get("horizontal_scale", 150)),
                vertical_scale=int(values.get("vertical_scale", 150)),
                group_id=existing_mosaic.group_id if existing_mosaic else None,
                grid_rows=existing_mosaic.grid_rows if existing_mosaic else 0,
                grid_columns=existing_mosaic.grid_columns if existing_mosaic else 0,
                row=existing_mosaic.row if existing_mosaic else 0,
                column=existing_mosaic.column if existing_mosaic else 0,
            ),
        )

    def _patch_camera(self, camera: CameraSettings, values: dict[str, Any]) -> CameraSettings:
        kwargs: dict[str, Any] = {}
        if "camera" in values:
            kwargs["camera"] = Camera(values.get("camera") or Camera.TELE)
        if "exposure" in values:
            kwargs["exposure_seconds"] = float(values["exposure"])
        if "gain" in values:
            kwargs["gain"] = int(values["gain"])
        if "frame_count" in values:
            kwargs["frame_count"] = int(values["frame_count"])
        if "binning" in values:
            kwargs["binning"] = int(values["binning"])
        if "ir_filter" in values:
            kwargs["ir_filter"] = values.get("ir_filter") or "VIS"
        return replace(camera, **kwargs) if kwargs else camera

    def _patch_workflow(self, workflow: Workflow, values: dict[str, Any]) -> Workflow:
        kwargs: dict[str, Any] = {}
        flags = {
            "calibrate": "calibrate",
            "autofocus": "autofocus",
            "infinite_focus": "infinite_focus",
            "polar_align": "polar_align",
            "goto": "goto",
        }
        for src, dest in flags.items():
            if src in values:
                kwargs[dest] = bool(values[src])
        if "wait_before" in values:
            kwargs["wait_before_seconds"] = float(values["wait_before"])
        if "wait_after" in values:
            kwargs["wait_after_seconds"] = float(values["wait_after"])
        return replace(workflow, **kwargs) if kwargs else workflow

    def _template_ids_for_shared_update(self, ids: list[str]) -> list[str]:
        wanted: list[str] = []
        seen: set[str] = set()
        groups: set[str] = set()
        for template_id in ids:
            template = self.store.templates.get(template_id)
            if not template:
                continue
            group_id = template.mosaic.group_id
            if group_id:
                groups.add(group_id)
                continue
            if template.id not in seen:
                seen.add(template.id)
                wanted.append(template.id)
        if groups:
            for item in self.store.templates.all():
                if item.mosaic.group_id in groups and item.id not in seen:
                    seen.add(item.id)
                    wanted.append(item.id)
        return wanted

    @Slot(str)
    def updateSharedSettings(self, payload: str) -> None:
        try:
            values = json.loads(payload)
            ids = self._normalize_ids(values.get("ids"))
            patch = {key: value for key, value in values.items() if key not in {"ids", "templates"}}
            if not ids:
                raise ValueError("No items selected")
            if not patch:
                self._toast("No common fields changed", "warning")
                return
            if values.get("templates"):
                updated = 0
                for template_id in self._template_ids_for_shared_update(ids):
                    template = self.store.templates.get(template_id)
                    if not template:
                        continue
                    camera = self._patch_camera(template.camera, patch)
                    workflow = self._patch_workflow(template.workflow, patch)
                    if camera is template.camera and workflow is template.workflow:
                        continue
                    self.store.templates.save(replace(template, camera=camera, workflow=workflow))
                    updated += 1
                if not updated:
                    self._toast("No templates to update", "warning")
                    return
                self.templatesChanged.emit()
                self._toast(f"Updated {updated} template{'s' if updated != 1 else ''}", "success")
                return
            updated = 0
            skipped_running = 0
            saved: list[Session] = []
            for session_id in ids:
                session = self.store.sessions.get(session_id)
                if not session:
                    continue
                if session.status == SessionStatus.RUNNING:
                    skipped_running += 1
                    continue
                camera = self._patch_camera(session.camera, patch)
                workflow = self._patch_workflow(session.workflow, patch)
                if camera is session.camera and workflow is session.workflow:
                    continue
                saved.append(self._save_session(replace(session, camera=camera, workflow=workflow), notify=False))
                updated += 1
            grouped: set[str] = set()
            for session in saved:
                group_id = session.mosaic.group_id
                if group_id and group_id not in grouped:
                    grouped.add(group_id)
                    self._sequence_mosaic_group(session, notify=False)
            for device_id in {session.device_id for session in saved}:
                self._pack_device_schedule(device_id, notify=False)
            if updated:
                self._emit_sessions_changed()
            if skipped_running and not updated:
                self._toast("Stop running sessions before editing them", "warning")
            elif skipped_running:
                self._toast(
                    f"Updated {updated}; skipped {skipped_running} running",
                    "warning",
                )
            elif updated:
                self._toast(f"Updated {updated} session{'s' if updated != 1 else ''}", "success")
            else:
                self._toast("No sessions to update", "warning")
        except Exception as exc:
            self._toast(f"Could not update settings: {exc}", "error")

    def _session_from_payload(self, values: dict[str, Any], existing: Session | None) -> Session:
        if existing and existing.status == SessionStatus.RUNNING:
            raise ValueError("A running session cannot be edited")
        device = self._device_by_id(values["device_id"])
        target, camera, workflow, mosaic = self._fields_from_payload(
            values, existing.mosaic if existing else None, device
        )
        resetting = existing is not None and existing.status != SessionStatus.PLANNED
        return Session(
            id=existing.id if existing else uuid4().hex,
            name=values.get("name") or values["target"],
            target=target,
            device_id=values["device_id"],
            scheduled_start=self._store_session_time(values["scheduled_start"], device),
            camera=camera,
            workflow=workflow,
            mosaic=mosaic,
            notes=values.get("notes", existing.notes if existing else ""),
            status=SessionStatus.PLANNED,
            current_step="Waiting" if (existing is None or resetting) else existing.current_step,
            actual_started_at=None,
            actual_ended_at=None,
            outcome="",
            template_id=existing.template_id if existing else None,
            created_at=existing.created_at if existing else datetime.now(timezone.utc).isoformat(),
        )

    @Slot(str)
    def saveSession(self, payload: str) -> None:
        try:
            values = json.loads(payload)
            panes = values.get("members")
            if isinstance(panes, list) and len(panes) > 1:
                self._save_session_panes(values, panes)
                return
            existing = self.store.sessions.get(values.get("id", "")) if values.get("id") else None
            session = self._session_from_payload(values, existing)
            device = self._device_by_id(session.device_id)
            proposed: dict[str, Session] = {session.id: session}
            if existing:
                family = self._mosaic_siblings(existing)
                if existing.device_id != device.id and any(item.status == SessionStatus.RUNNING for item in family):
                    raise ValueError("Stop the running mosaic before moving it to another telescope")
                old_tz = self._zone_for_id(existing.device_id)
                new_tz = self._zone_for(device)
                delta = parse_in_zone(session.scheduled_start, new_tz) - parse_in_zone(existing.scheduled_start, old_tz)
                for sibling in self._session_group(existing):
                    if sibling.id == existing.id:
                        continue
                    if existing.device_id != device.id or delta:
                        sib_start = parse_in_zone(sibling.scheduled_start, old_tz) + delta
                        proposed[sibling.id] = replace(
                            sibling,
                            device_id=device.id,
                            scheduled_start=store_local_iso(sib_start, new_tz),
                        )
                    else:
                        proposed[sibling.id] = sibling
            self._commit_device_sessions(list(proposed.values()), device)
            if values.get("save_template"):
                template = SessionTemplate(
                    name=session.name,
                    target=session.target,
                    camera=session.camera,
                    workflow=session.workflow,
                    mosaic=session.mosaic,
                )
                self.store.templates.save(template)
                self.templatesChanged.emit()
                self._toast_templates("Session saved as a template", [template.id])
            else:
                self._toast("Session saved", "success")
        except Exception as exc:
            self._toast(f"Could not save session: {exc}", "error")

    def _save_session_panes(self, values: dict[str, Any], panes: list) -> None:
        shared = {key: value for key, value in values.items() if key != "members"}
        anchor_id = str(shared.get("anchor_id") or shared.get("id") or "")
        existing_anchor = self.store.sessions.get(anchor_id) if anchor_id else None
        if existing_anchor and existing_anchor.status == SessionStatus.RUNNING:
            raise ValueError("A running session cannot be edited")
        device = self._device_by_id(shared["device_id"])
        family = self._mosaic_siblings(existing_anchor) if existing_anchor else []
        if existing_anchor and existing_anchor.device_id != device.id and any(
            item.status == SessionStatus.RUNNING for item in family
        ):
            raise ValueError("Stop the running mosaic before moving it to another telescope")
        new_tz = self._zone_for(device)
        old_tz = self._zone_for_id(existing_anchor.device_id) if existing_anchor else new_tz
        new_anchor_start = self._store_session_time(shared["scheduled_start"], device)
        delta = (
            parse_in_zone(new_anchor_start, new_tz) - parse_in_zone(existing_anchor.scheduled_start, old_tz)
            if existing_anchor else timedelta(0)
        )
        drafts: list[Session] = []
        for pane in panes:
            if not isinstance(pane, dict):
                continue
            existing = self.store.sessions.get(pane.get("id", "")) if pane.get("id") else None
            merged = {**shared, **pane, "device_id": device.id}
            if existing:
                start = parse_in_zone(existing.scheduled_start, old_tz) + delta
                merged["scheduled_start"] = store_local_iso(start, new_tz)
            drafts.append(self._session_from_payload(merged, existing))
        if not drafts:
            raise ValueError("No panes to save")
        saved = self._commit_device_sessions(drafts, device)
        anchor = next((item for item in saved if item.id == anchor_id), saved[0])
        if values.get("save_template"):
            template = SessionTemplate(
                name=anchor.name,
                target=anchor.target,
                camera=anchor.camera,
                workflow=anchor.workflow,
                mosaic=anchor.mosaic,
            )
            self.store.templates.save(template)
            self.templatesChanged.emit()
            self._toast_templates("Session saved as a template", [template.id])
        else:
            self._toast("Session saved", "success")

    def _save_one_template(self, values: dict[str, Any]) -> SessionTemplate:
        existing = self.store.templates.get(values.get("id", "")) if values.get("id") else None
        device = self._schedule_device(str(values.get("device_id") or ""))
        target, camera, workflow, mosaic = self._fields_from_payload(
            values, existing.mosaic if existing else None, device
        )
        name = values.get("name") or values["target"]
        notes = values.get("notes", existing.notes if existing else "")
        if existing:
            template = replace(
                existing,
                name=name,
                target=target,
                camera=camera,
                workflow=workflow,
                mosaic=mosaic,
                notes=notes,
            )
        else:
            template = SessionTemplate(
                name=name,
                target=target,
                camera=camera,
                workflow=workflow,
                mosaic=mosaic,
                notes=notes,
            )
        self.store.templates.save(template)
        return template

    @Slot(str)
    def saveTemplate(self, payload: str) -> None:
        try:
            values = json.loads(payload)
            saved_ids: list[str] = []
            panes = values.get("members")
            if isinstance(panes, list) and panes:
                shared = {key: value for key, value in values.items() if key != "members"}
                for pane in panes:
                    merged = {**shared, **pane}
                    saved_ids.append(self._save_one_template(merged).id)
            else:
                saved = self._save_one_template(values)
                saved_ids.append(saved.id)
                group_id = saved.mosaic.group_id
                if group_id:
                    for item in self.store.templates.all():
                        if item.id != saved.id and item.mosaic.group_id == group_id:
                            self.store.templates.save(replace(item, camera=saved.camera, workflow=saved.workflow))
            self.templatesChanged.emit()
            self._toast_templates("Saved session template", saved_ids)
        except Exception as exc:
            self._toast(f"Could not save template: {exc}", "error")

    def _save_session(self, session: Session, *, notify: bool = True) -> Session:
        device = self._device_by_id(session.device_id)
        session = replace(session, planned_duration_seconds=DurationEngine.calculate(session, device.hardware))
        self.store.sessions.save(session)
        if notify:
            self._emit_sessions_changed()
        return session

    @Slot(str)
    def deleteSession(self, session_id: str) -> None:
        self.deleteSessions([session_id])

    @Slot(list)
    @Slot("QVariantList")
    def deleteSessions(self, session_ids: list) -> None:
        deleted = 0
        skipped_running = 0
        for session_id in self._normalize_ids(session_ids):
            session = self.store.sessions.get(session_id)
            if not session:
                continue
            if session.status == SessionStatus.RUNNING:
                skipped_running += 1
                continue
            self.store.sessions.delete(session_id)
            deleted += 1
        if deleted:
            self._emit_sessions_changed()
        if skipped_running and not deleted:
            self._toast("Stop running sessions before deleting them", "warning")
        elif skipped_running:
            self._toast(
                f"Deleted {deleted}; skipped {skipped_running} running",
                "warning",
            )
        elif deleted:
            self._toast(f"Deleted {deleted} session{'s' if deleted != 1 else ''}", "success")

    @Slot()
    def clearHistory(self) -> None:
        self.store.history.clear()
        self.historyChanged.emit()
        self._toast("History cleared", "success")

    @Slot(str)
    def clearHistoryForDevice(self, device_id: str) -> None:
        target = str(device_id or "").strip() or self._selected_device_id
        if not target:
            return
        deleted = 0
        for record in list(self.store.history.all()):
            if record.device_id == target and self.store.history.delete(record.id):
                deleted += 1
        if deleted:
            self.historyChanged.emit()
            self._toast(
                f"Cleared {deleted} recorded run{'s' if deleted != 1 else ''}",
                "success",
            )

    @Slot(list)
    @Slot("QVariantList")
    def deleteHistoryRecords(self, record_ids: list) -> None:
        deleted = 0
        for record_id in self._normalize_ids(record_ids):
            if self.store.history.delete(record_id):
                deleted += 1
        if deleted:
            self.historyChanged.emit()
            self._toast(f"Deleted {deleted} recorded run{'s' if deleted != 1 else ''}", "success")

    @Slot(str)
    def duplicateSession(self, session_id: str) -> None:
        source = self.store.sessions.get(session_id)
        if not source:
            return
        device = self._device_by_id(source.device_id)
        tz = self._zone_for(device)
        copy = self._with_duration(replace(
            source,
            id=uuid4().hex,
            name=f"{source.name} copy",
            scheduled_start=source.scheduled_start,
            status=SessionStatus.PLANNED,
            actual_started_at=None,
            actual_ended_at=None,
        ))
        start = parse_in_zone(copy.scheduled_start, tz)
        if source.mosaic.group_id:
            family = [
                item for item in self._mosaic_siblings(source)
                if item.status == SessionStatus.PLANNED
            ]
            if family:
                start = max(self._session_window(item, tz)[1] for item in family)
        span_start, span_end = self._session_window(copy, tz)
        free = next_free_start(self._occupied_windows(device.id, set()), start, span_end - span_start)
        self._save_session(replace(copy, scheduled_start=store_local_iso(free, tz)))

    @Slot(str)
    def runNow(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            self._toast("This session is no longer on the calendar", "warning")
            return
        if session.status == SessionStatus.RUNNING:
            self._toast("This session is already running", "warning")
            return
        device = next((item for item in self._devices if item.id == session.device_id), None)
        worker = self._workers.get(session.device_id)
        if not device or not worker:
            self._toast("This telescope is not available", "warning")
            return
        if not device.location_configured:
            self._toast("Choose an observing location before running a session", "warning")
            return
        if not worker.connected:
            self._toast("Connect the telescope before running a session", "warning")
            return
        if session.device_id in self._disconnecting_ids:
            self._toast("Wait for the telescope to finish disconnecting", "warning")
            return
        if session.device_id in self._active_sessions or worker.busy:
            self._toast("Another session is running on this telescope", "warning")
            return
        if session.device_id != self._selected_device_id:
            self._toast(f"Starting on {device.name}", "info")
        # Keep the planned slot on the calendar. Actual start/end live on
        # actual_* so a short failed run does not shrink or relocate the block.
        self._save_session(replace(
            session,
            status=SessionStatus.PLANNED,
            current_step="Waiting",
            actual_started_at=None,
            actual_ended_at=None,
            outcome="",
        ))
        # RUN is an explicit request: start now even when the scheduler is disarmed.
        started = self.store.sessions.get(session.id)
        if started is None:
            self._toast("This session is no longer on the calendar", "warning")
            return
        self._start_session(worker, started)

    @Slot(str, str)
    def moveSessionDate(self, session_id: str, day: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            return
        if session.status == SessionStatus.RUNNING:
            self._toast("Stop the running session before moving it", "warning")
            return
        try:
            target_day = date.fromisoformat(day)
        except ValueError:
            return
        old_night = date.fromisoformat(observing_date(
            session.scheduled_start,
            self._cutoff_hour(),
            self._zone_for_id(session.device_id),
        ))
        delta = target_day - old_night
        if delta.days == 0:
            return
        members = [session]
        group_id = session.mosaic.group_id
        if group_id:
            members = [
                item for item in self.store.sessions.all()
                if item.mosaic.group_id == group_id
                and item.device_id == session.device_id
                and item.status != SessionStatus.RUNNING
            ]
        device = self._device_by_id(session.device_id)
        proposed = []
        for item in members:
            tz = self._zone_for_id(item.device_id)
            start = parse_in_zone(item.scheduled_start, tz) + timedelta(days=delta.days)
            proposed.append(replace(item, scheduled_start=store_local_iso(start, tz)))
        try:
            self._commit_device_sessions(proposed, device)
        except ValueError as exc:
            self._toast(str(exc), "warning")

    def _mosaic_siblings(self, session: Session) -> list[Session]:
        group_id = session.mosaic.group_id
        if not group_id:
            return [session]
        return [
            item for item in self.store.sessions.all()
            if item.mosaic.group_id == group_id and item.device_id == session.device_id
        ]

    def _session_group(self, session: Session) -> list[Session]:
        return sorted(
            (item for item in self._mosaic_siblings(session) if item.status != SessionStatus.RUNNING),
            key=lambda item: (item.scheduled_start, pane_sort_key(item.name), item.name),
        )

    def _reassign_session(self, session: Session, device: Device) -> Session:
        if session.device_id == device.id:
            return session
        return replace(
            session,
            device_id=device.id,
            scheduled_start=self._store_session_time(session.scheduled_start, device),
        )

    def _sessions_to_reassign(self, session_ids: list[str]) -> tuple[list[Session], int]:
        skipped = 0
        seen: set[str] = set()
        moving: list[Session] = []
        for session_id in self._normalize_ids(session_ids):
            session = self.store.sessions.get(session_id)
            if not session or session.id in seen:
                continue
            family = self._mosaic_siblings(session)
            if any(item.status == SessionStatus.RUNNING for item in family):
                skipped += 1
                seen.update(item.id for item in family)
                continue
            for item in family:
                if item.id in seen:
                    continue
                seen.add(item.id)
                moving.append(item)
        return moving, skipped

    @Slot(list, str)
    @Slot("QVariantList", str)
    def assignSessionsDevice(self, session_ids: list, device_id: str) -> None:
        device = next((item for item in self._devices if item.id == device_id), None)
        if not device:
            self._toast("That telescope was not found", "error")
            return
        moving, skipped = self._sessions_to_reassign(session_ids)
        proposed = [
            self._reassign_session(session, device)
            for session in moving
            if session.device_id != device.id
        ]
        changed_ids = {item.id for item in proposed}
        if proposed:
            try:
                self._commit_device_sessions(proposed, device)
            except ValueError as exc:
                self._toast(str(exc), "warning")
                return
        if skipped and not changed_ids:
            self._toast("Stop running sessions before moving them", "warning")
        elif skipped:
            self._toast(
                f"Moved {len(changed_ids)}; skipped {skipped} running group{'s' if skipped != 1 else ''}",
                "warning",
            )
        elif changed_ids:
            label = "session" if len(changed_ids) == 1 else "sessions"
            self._toast(f"Moved {len(changed_ids)} {label} to {device.name}", "success")
        else:
            self._toast("Those sessions are already on this telescope", "info")

    def _with_duration(self, session: Session) -> Session:
        device = self._device_by_id(session.device_id)
        return replace(session, planned_duration_seconds=DurationEngine.calculate(session, device.hardware))

    def _session_window(self, session: Session, tz) -> tuple[datetime, datetime]:
        return session_window(session, tz)

    def _mosaic_members_overlap(self, members: list[Session], tz) -> bool:
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                if sessions_overlap(left, right, tz):
                    return True
        return False

    def _schedule_blocks(self, sessions: list[Session]) -> list[list[Session]]:
        grouped: dict[str, list[Session]] = {}
        blocks: list[list[Session]] = []
        for item in sessions:
            key = item.mosaic.group_id
            if key:
                grouped.setdefault(key, []).append(item)
            else:
                blocks.append([item])
        blocks.extend(grouped.values())

        def sort_key(block: list[Session]):
            first = min(
                block,
                key=lambda item: (item.scheduled_start, pane_sort_key(item.name), item.name, item.id),
            )
            return (
                first.scheduled_start,
                pane_sort_key(first.name),
                first.mosaic.group_id or first.id,
                first.name,
            )

        return sorted(blocks, key=sort_key)

    def _stagger_if_overlapping(self, members: list[Session], device: Device) -> list[Session]:
        tz = self._zone_for(device)
        result: list[Session] = []
        for block in self._schedule_blocks(members):
            timed = [self._with_duration(item) for item in block]
            if len(timed) >= 2 and self._mosaic_members_overlap(timed, tz):
                start = min(parse_in_zone(item.scheduled_start, tz) for item in timed)
                result.extend(stagger_mosaic_sessions(timed, start, device.hardware))
            else:
                result.extend(timed)
        return result

    def _occupied_windows(self, device_id: str, exclude_ids: set[str]) -> list[tuple[datetime, datetime]]:
        tz = self._zone_for_id(device_id)
        windows: list[tuple[datetime, datetime]] = []
        for item in self.store.sessions.all():
            if item.device_id != device_id or item.id in exclude_ids:
                continue
            if item.status not in (SessionStatus.PLANNED, SessionStatus.RUNNING):
                continue
            windows.append(self._session_window(item, tz))
        return windows

    def _device_busy_error(self, device: Device, other: Session) -> ValueError:
        tz = self._zone_for(device)
        start, end = self._session_window(other, tz)
        label = other.name or other.target.name
        return ValueError(
            f"{device.name} already has {label} at {start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
        )

    def _first_device_overlap(
        self,
        proposed: list[Session],
        device_id: str,
        exclude_ids: set[str],
    ) -> Session | None:
        tz = self._zone_for_id(device_id)
        others = [
            item for item in self.store.sessions.all()
            if item.device_id == device_id
            and item.id not in exclude_ids
            and item.status in (SessionStatus.PLANNED, SessionStatus.RUNNING)
        ]
        for index, left in enumerate(proposed):
            left_group = left.mosaic.group_id or left.id
            for right in proposed[index + 1:]:
                right_group = right.mosaic.group_id or right.id
                if left_group == right_group:
                    continue
                if sessions_overlap(left, right, tz):
                    return right
            for right in others:
                if sessions_overlap(left, right, tz):
                    return right
        return None

    def _commit_device_sessions(self, sessions: list[Session], device: Device) -> list[Session]:
        proposed = self._stagger_if_overlapping(sessions, device)
        conflict = self._first_device_overlap(proposed, device.id, {item.id for item in proposed})
        if conflict:
            raise self._device_busy_error(device, conflict)
        saved = [self._save_session(item, notify=False) for item in proposed]
        self._emit_sessions_changed()
        return saved

    def _pack_device_schedule(self, device_id: str, *, notify: bool = False) -> bool:
        device = self._device_by_id(device_id)
        tz = self._zone_for(device)
        planned = [
            self._with_duration(item)
            for item in self.store.sessions.all()
            if item.device_id == device_id and item.status == SessionStatus.PLANNED
        ]
        if not planned:
            return False
        occupied = [
            self._session_window(item, tz)
            for item in self.store.sessions.all()
            if item.device_id == device_id and item.status == SessionStatus.RUNNING
        ]
        originals = {item.id: item for item in planned}
        changed = False
        for block in self._schedule_blocks(planned):
            members = self._stagger_if_overlapping(block, device)
            span_start = min(parse_in_zone(item.scheduled_start, tz) for item in members)
            span_end = max(self._session_window(item, tz)[1] for item in members)
            free = next_free_start(occupied, span_start, span_end - span_start)
            delta = free - span_start
            for item in members:
                updated = item
                if delta:
                    start = parse_in_zone(item.scheduled_start, tz) + delta
                    updated = replace(item, scheduled_start=store_local_iso(start, tz))
                prev = originals.get(item.id)
                start_changed = (
                    not prev
                    or parse_in_zone(prev.scheduled_start, tz) != parse_in_zone(updated.scheduled_start, tz)
                )
                if (
                    start_changed
                    or not prev
                    or abs((prev.planned_duration_seconds or 0) - (updated.planned_duration_seconds or 0)) > 0.05
                    or prev.workflow != updated.workflow
                ):
                    self.store.sessions.save(self._with_duration(updated))
                    changed = True
                occupied.append(self._session_window(updated, tz))
        if changed and notify:
            self._emit_sessions_changed()
        return changed

    def _sequence_mosaic_group(self, session: Session, *, notify: bool = False) -> bool:
        group_id = session.mosaic.group_id
        if not group_id:
            return False
        members = [
            item for item in self.store.sessions.all()
            if item.mosaic.group_id == group_id
            and item.device_id == session.device_id
            and item.status == SessionStatus.PLANNED
        ]
        if len(members) < 2:
            return False
        device = self._device_by_id(session.device_id)
        tz = self._zone_for(device)
        if not self._mosaic_members_overlap(members, tz):
            return False
        start = min(parse_in_zone(item.scheduled_start, tz) for item in members)
        for item in stagger_mosaic_sessions(members, start, device.hardware):
            self.store.sessions.save(item)
        if notify:
            self._emit_sessions_changed()
        return True

    @Slot(str, str)
    def moveSessionStart(self, session_id: str, iso_datetime: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            return
        if session.status == SessionStatus.RUNNING:
            self._toast("Stop the running session before moving it", "warning")
            return
        try:
            tz = self._zone_for_id(session.device_id)
            target = parse_in_zone(iso_datetime, tz).replace(second=0, microsecond=0)
            current = parse_in_zone(session.scheduled_start, tz)
        except ValueError:
            self._toast("That schedule time is not valid", "error")
            return
        delta = target - current
        if not delta:
            return
        device = self._device_by_id(session.device_id)
        proposed = []
        for item in self._session_group(session):
            item_tz = self._zone_for_id(item.device_id)
            start = parse_in_zone(item.scheduled_start, item_tz) + delta
            proposed.append(replace(item, scheduled_start=store_local_iso(start, item_tz)))
        try:
            self._commit_device_sessions(proposed, device)
        except ValueError as exc:
            self._toast(str(exc), "warning")

    @Slot(str, str)
    @Slot(str, str, str)
    def reorderPlanned(self, session_id: str, before_session_id: str, night: str = "") -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            return
        if session.status != SessionStatus.PLANNED:
            self._toast("Only planned sessions can be reordered", "warning")
            return
        moving = [session]
        moving_ids = {session.id}
        before = self.store.sessions.get(before_session_id) if before_session_id else None
        if before and (before.device_id != session.device_id or before.status != SessionStatus.PLANNED):
            before = None
            before_session_id = ""
        device = self._device_by_id(session.device_id)
        tz = self._zone_for(device)
        cutoff = self._cutoff_hour()
        if before:
            target_night = observing_date(before.scheduled_start, cutoff, tz)
        else:
            wanted = str(night or "").strip()
            try:
                date.fromisoformat(wanted)
                target_night = wanted
            except ValueError:
                target_night = observing_date(session.scheduled_start, cutoff, tz)
        old_night = date.fromisoformat(observing_date(session.scheduled_start, cutoff, tz))
        try:
            target_day = date.fromisoformat(target_night)
        except ValueError:
            target_day = old_night
        if target_day != old_night:
            start = parse_in_zone(session.scheduled_start, tz) + timedelta(days=(target_day - old_night).days)
            session = replace(session, scheduled_start=store_local_iso(start, tz))
            moving = [session]
        queue = sorted(
            (
                item for item in self.store.sessions.all()
                if item.device_id == session.device_id
                and item.status == SessionStatus.PLANNED
                and item.id not in moving_ids
                and observing_date(item.scheduled_start, cutoff, tz) == target_night
            ),
            key=lambda item: (item.scheduled_start, pane_sort_key(item.name), item.name),
        )
        insert_at = len(queue)
        if before_session_id:
            insert_at = next(
                (index for index, item in enumerate(queue) if item.id == before_session_id),
                len(queue),
            )
        ordered = queue[:insert_at] + moving + queue[insert_at:]
        if not ordered:
            return
        starts = [parse_in_zone(item.scheduled_start, tz) for item in queue]
        if not starts:
            starts = [parse_in_zone(item.scheduled_start, tz) for item in moving]
        cursor = min(starts)
        occupied = [
            self._session_window(item, tz)
            for item in self.store.sessions.all()
            if item.device_id == device.id and item.status == SessionStatus.RUNNING
        ]
        for item in ordered:
            span = timedelta(seconds=max(60, float(item.planned_duration_seconds or 0)))
            free = next_free_start(occupied, cursor, span)
            self.store.sessions.save(replace(item, scheduled_start=store_local_iso(free, tz)))
            occupied.append((free, free + span))
            cursor = free + span
        self._emit_sessions_changed()

    def _schedule_device(self, device_id: str = "") -> Device | None:
        wanted = device_id or self._selected_device_id
        return next((item for item in self._devices if item.id == wanted), None) or (
            next((item for item in self._devices if item.id == self._selected_device_id), None)
        )

    @Slot(result=str)
    @Slot(str, result=str)
    def deviceNowStamp(self, device_id: str = "") -> str:
        device = self._schedule_device(device_id)
        now = datetime.now(self._zone_for(device)).replace(second=0, microsecond=0)
        return now.strftime("%Y-%m-%dT%H:%M")

    @Slot(str, str, float, result="QVariantMap")
    def scheduleWindow(self, device_id: str, scheduled_start: str, duration_seconds: float) -> dict[str, Any]:
        device = self._schedule_device(device_id)
        if not device:
            return {"ok": False}
        tz = self._zone_for(device)
        raw = str(scheduled_start or "").strip()
        if not raw:
            return {"ok": False, "device_name": device.name, "timezone": device.timezone_name}
        try:
            start = parse_in_zone(raw, tz).replace(second=0, microsecond=0)
        except ValueError:
            return {"ok": False, "device_name": device.name, "timezone": device.timezone_name}
        seconds = max(60.0, float(duration_seconds or 0))
        span = timedelta(seconds=seconds)
        end = start + span
        occupied = self._occupied_windows(device.id, set())
        conflict = ""
        for item in self.store.sessions.all():
            if item.device_id != device.id or item.status not in (SessionStatus.PLANNED, SessionStatus.RUNNING):
                continue
            other_start, other_end = self._session_window(item, tz)
            if start < other_end and other_start < end:
                label = item.name or item.target.name
                conflict = f"{label} {other_start.strftime('%H:%M')}–{other_end.strftime('%H:%M')}"
                break
        free = next_free_start(occupied, start, span)
        snapped = free != start
        return {
            "ok": True,
            "device_name": device.name,
            "timezone": device.timezone_name,
            "start": start.strftime("%Y-%m-%dT%H:%M"),
            "end": end.strftime("%H:%M"),
            "end_stamp": end.strftime("%Y-%m-%dT%H:%M"),
            "duration_text": self._duration_text(seconds),
            "conflict": conflict,
            "next_free": free.strftime("%Y-%m-%dT%H:%M") if snapped else "",
            "next_free_time": free.strftime("%H:%M") if snapped else "",
        }

    @Slot(str, str, str, float, int, result="QVariantMap")
    def templateScheduleWindow(
        self,
        template_id: str,
        device_id: str,
        scheduled_start: str,
        exposure_seconds: float,
        frame_count: int,
    ) -> dict[str, Any]:
        template = self.store.templates.get(template_id)
        device = self._schedule_device(device_id)
        if not template or not device or exposure_seconds <= 0 or frame_count < 1:
            return {"ok": False}
        try:
            start = parse_in_zone(str(scheduled_start).strip(), self._zone_for(device)).replace(second=0, microsecond=0)
        except ValueError:
            return {"ok": False}
        group_id = template.mosaic.group_id
        templates = (
            [item for item in self.store.templates.all() if item.mosaic.group_id == group_id]
            if group_id else [template]
        )
        sessions = []
        for item in templates:
            session = self.store.clone_template(item, device.id, start)
            camera = replace(session.camera, exposure_seconds=exposure_seconds, frame_count=frame_count)
            sessions.append(replace(session, camera=camera))
        timed = stagger_mosaic_sessions(sessions, start, device.hardware)
        last = max(timed, key=lambda item: item.scheduled_start)
        end = parse_in_zone(last.scheduled_start, self._zone_for(device)) + timedelta(
            seconds=last.planned_duration_seconds
        )
        return self.scheduleWindow(device.id, scheduled_start, (end - start).total_seconds())

    @Slot(str, str, result=bool)
    @Slot(str, str, str, result=bool)
    @Slot(str, str, str, float, int, result=bool)
    def scheduleTemplate(
        self,
        template_id: str,
        scheduled_start: str,
        device_id: str = "",
        exposure_seconds: float | None = None,
        frame_count: int | None = None,
    ) -> bool:
        template = self.store.templates.get(template_id)
        if not template:
            return False
        if exposure_seconds is not None and exposure_seconds <= 0:
            self._toast("Exposure must be greater than zero", "error")
            return False
        if frame_count is not None and frame_count < 1:
            self._toast("Frames must be at least one", "error")
            return False
        group_id = template.mosaic.group_id
        templates = (
            [item for item in self.store.templates.all() if item.mosaic.group_id == group_id]
            if group_id else [template]
        )
        device = self._schedule_device(device_id)
        if not device:
            self._toast("Select a telescope first", "error")
            return False
        tz = self._zone_for(device)
        try:
            start = parse_in_zone(str(scheduled_start).strip(), tz).replace(second=0, microsecond=0)
        except ValueError:
            self._toast("Enter a start time like 2026-09-10T22:00", "error")
            return False
        sessions = []
        for item in templates:
            session = self.store.clone_template(item, device.id, start)
            camera = replace(
                session.camera,
                exposure_seconds=exposure_seconds if exposure_seconds is not None else session.camera.exposure_seconds,
                frame_count=frame_count if frame_count is not None else session.camera.frame_count,
            )
            sessions.append(replace(session, camera=camera))
        staggered = stagger_mosaic_sessions(sessions, start, device.hardware)
        try:
            self._commit_device_sessions(staggered, device)
        except ValueError as exc:
            self._toast(str(exc), "warning")
            return False
        count = len(sessions)
        self._toast(f"Scheduled {count} pane{'s' if count != 1 else ''} on {device.name}", "success")
        return True

    @Slot(str)
    def importTelescopius(self, raw_path: str) -> None:
        path = self._local_path(raw_path)
        self._run_async("telescopius", lambda: import_telescopius(path))

    @Slot("QVariant")
    def importStellariumSmart(self, web_raw: Any) -> None:
        payload = self._snapshot_web_raw(web_raw)

        def work() -> dict[str, Any]:
            target = self._resolve_stellarium_target(payload)
            return {"target": target, "notes": sky_web_template_notes(payload)}

        self._run_async("stellarium", work)

    @Slot()
    def importStellarium(self) -> None:
        self.importStellariumSmart("")

    def _snapshot_web_raw(self, raw: Any) -> Any:
        if raw is None:
            return ""
        if isinstance(raw, dict):
            return dict(raw)
        text = str(raw).strip()
        if text in {"", "undefined", "null"}:
            return ""
        return text

    def _resolve_stellarium_target(self, web_raw: Any) -> Target:
        """Prefer the SKY tab selection; use desktop Stellarium only if the map has none."""
        try:
            return parse_sky_web_target(web_raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        try:
            return StellariumClient(self._settings.stellarium_url).current_target()
        except Exception as desktop_exc:
            if self._sky_target is not None:
                return self._sky_target
            raise ValueError(
                "Select a target in the sky map, or open Stellarium with Remote Control"
            ) from desktop_exc

    @Slot("QVariant")
    def lockStellariumSmart(self, web_raw: Any) -> None:
        payload = self._snapshot_web_raw(web_raw)
        self._run_async("stellariumLock", lambda: self._resolve_stellarium_target(payload))

    @Slot()
    def lockStellariumTarget(self) -> None:
        self.lockStellariumSmart("")

    @Slot("QVariant", int, int, float, float)
    def generateStellariumMosaic(
        self, web_raw: Any, columns: int, rows: int, overlap: float, position_angle: float = 0.0
    ) -> None:
        payload = self._snapshot_web_raw(web_raw)
        pa = float(position_angle) % 360.0

        def work() -> dict[str, Any]:
            target = self._resolve_stellarium_target(payload)
            fov_h, fov_v, _camera = self._mosaic_fov()
            extra = sky_web_template_notes(payload)
            templates = generate_mosaic_plan(
                target,
                columns,
                rows,
                fov_h,
                fov_v,
                overlap,
                south_up=self._mosaic_south_up(),
                position_angle=pa,
            )
            if extra:
                templates = [
                    replace(item, notes="  ·  ".join(part for part in (extra, item.notes) if part))
                    for item in templates
                ]
            return {
                "target": target,
                "fetched": True,
                "templates": templates,
            }

        self._run_async("stellariumMosaic", work)

    @Slot(str)
    def importLegacy(self, raw_path: str) -> None:
        path = self._local_path(raw_path)
        device = self._schedule_device(self._selected_device_id)
        count, failed = self.store.import_old_sessions(
            path.rglob("*.json"),
            self._selected_device_id,
            device.capture_defaults if device else None,
        )
        for session in self.store.sessions.all():
            if session.planned_duration_seconds == 0:
                self._save_session(session)
        self._sequence_colliding_mosaics()
        self._toast(f"Imported {count}; skipped {failed}", "success" if count else "warning")

    def _run_async(self, operation: str, function: Callable[[], Any]) -> None:
        if self._ui_busy:
            self._toast("Another import is still running", "warning")
            return
        self._set_ui_busy(operation)

        def run() -> None:
            try:
                self._asyncResult.emit(operation, (True, function()))
            except Exception as exc:
                self._asyncResult.emit(operation, (False, str(exc)))

        threading.Thread(target=run, daemon=True).start()

    def _push_sky_to_desktop(self, target: Target) -> None:
        device = self._schedule_device()
        fov_h, fov_v, _camera = self._mosaic_fov()
        latitude = longitude = None
        name = ""
        if device is not None and has_site_coordinates(device.latitude, device.longitude):
            latitude = float(device.latitude)
            longitude = float(device.longitude)
            name = device.name
        StellariumClient(self._settings.stellarium_url).push_view(
            target,
            latitude,
            longitude,
            name,
            max(fov_h, fov_v),
        )

    def _maybe_push_sky_to_desktop(self, target: Target | None) -> None:
        if not self._stellarium_rc_live or not isinstance(target, Target):
            return

        def work() -> None:
            try:
                self._push_sky_to_desktop(target)
            except Exception:
                return

        threading.Thread(target=work, daemon=True).start()

    @Slot(str, object)
    def _handle_async_result(self, operation: str, result: tuple[bool, Any]) -> None:
        ok, value = result
        if operation == "stellariumRcPing":
            self._stellarium_rc_inflight = False
            self._set_stellarium_rc_live(bool(value) if ok else False)
            return
        if operation == "locationLookup":
            self._set_location_lookup_busy(False)
            if not ok:
                self._toast(str(value), "warning")
                return
            self.locationLookupReady.emit(value)
            return
        if operation == "deviceDiscoverLog":
            payload = value if isinstance(value, dict) else {}
            if payload.get("token") != self._device_discovery_token:
                return
            self.add_log(str(payload.get("level") or "info"), str(payload.get("message") or ""))
            return
        if operation == "deviceDiscover":
            payload = value if isinstance(value, dict) else {"error": str(value), "devices": []}
            if payload.get("token") != self._device_discovery_token:
                return
            self._set_device_discovery_busy(False)
            if payload.get("cancelled"):
                return
            if not ok:
                self._toast(str(payload.get("error") or "Bluetooth discovery failed"), "error")
                return
            devices = payload.get("devices") or []
            self.deviceDiscoveryReady.emit(devices)
            if not devices:
                self._toast("No Dwarf found over Bluetooth", "warning")
            else:
                count = len(devices)
                self._toast(f"Found {count} telescope{'s' if count != 1 else ''}", "success")
            return
        self._set_ui_busy("")
        if not ok:
            labels = {
                "stellarium": "Stellarium",
                "stellariumLock": "Stellarium",
                "stellariumMosaic": "Mosaic",
                "stellariumPush": "Stellarium",
                "telescopius": "Telescopius",
            }
            self._toast(f"{labels.get(operation, operation.title())}: {value}", "error")
            return
        if operation == "telescopius":
            camera = self._camera_settings_for()
            saved_ids: list[str] = []
            for template in value:
                saved = replace(template, camera=camera)
                self.store.templates.save(saved)
                saved_ids.append(saved.id)
            self.templatesChanged.emit()
            count = len(saved_ids)
            self._toast_templates(
                f"Imported {count} session template{'s' if count != 1 else ''}",
                saved_ids,
            )
        elif operation == "stellarium":
            if isinstance(value, dict):
                target = value.get("target")
                notes = str(value.get("notes") or "")
            else:
                target = value
                notes = ""
            if not isinstance(target, Target):
                self._toast("Stellarium: Select a target in the sky map", "error")
                return
            saved = SessionTemplate(
                name=target.name,
                target=target,
                camera=self._camera_settings_for(),
                notes=notes,
            )
            self.store.templates.save(saved)
            self.templatesChanged.emit()
            self._toast_templates(f"Imported {target.name} as a session template", [saved.id])
            self._maybe_push_sky_to_desktop(target)
        elif operation == "stellariumLock":
            self._set_sky_target(value)
            self._toast(f"Locked {value.name}", "success")
        elif operation == "stellariumPush":
            self._toast(f"Pushed {value} to desktop Stellarium", "success")
        elif operation == "stellariumMosaic":
            payload = value if isinstance(value, dict) else {}
            templates = payload.get("templates") or []
            if payload.get("fetched") and payload.get("target") is not None:
                self._set_sky_target(payload["target"])
            camera = self._camera_settings_for()
            saved_ids: list[str] = []
            for template in templates:
                saved = replace(template, camera=camera)
                self.store.templates.save(saved)
                saved_ids.append(saved.id)
            self.templatesChanged.emit()
            count = len(saved_ids)
            self._toast_templates(
                f"Generated {count} mosaic pane template{'s' if count != 1 else ''}",
                saved_ids,
            )
            self._maybe_push_sky_to_desktop(payload.get("target"))

    def _scheduler_tick(self) -> None:
        if not self._scheduler_enabled:
            return
        for device in self._devices:
            if device.id in self._active_sessions or not device.location_configured:
                continue
            if (
                device.id in self._disconnecting_ids
                or device.id in self._connecting_ids
                or device.id in self._cancel_connect_ids
            ):
                continue
            worker = self._workers[device.id]
            if worker.busy or not worker.connected:
                continue
            sessions = self.store.upcoming(device.id)
            if not sessions:
                continue
            session = sessions[0]
            tz = self._zone_for(device)
            due = parse_in_zone(session.scheduled_start, tz)
            if due > datetime.now(tz):
                continue
            if session.id in self._recovered_sessions:
                self._maybe_resume_interrupted_session(device.id)
                continue
            self._start_session(worker, session)

    def _recovered_session_for(self, device_id: str, telemetry: dict[str, Any]) -> Session | None:
        candidates = [
            session
            for session_id, owner in self._recovered_sessions.items()
            if owner == device_id
            for session in [self.store.sessions.get(session_id)]
            if session is not None and session.status == SessionStatus.PLANNED
        ]
        if not candidates:
            return None
        target = str(telemetry.get("capture_target") or telemetry.get("tracking_target") or "").strip().lower()
        if target:
            matched = [
                session
                for session in candidates
                if target == session.target.name.strip().lower()
                or target in session.target.name.strip().lower()
                or session.target.name.strip().lower() in target
            ]
            if matched:
                candidates = matched
            elif any(session.target.name.strip() for session in candidates):
                return None
        return sorted(candidates, key=lambda item: item.scheduled_start)[-1]

    def _maybe_resume_interrupted_session(self, device_id: str) -> None:
        if device_id in self._resume_attempted or self._active_sessions.get(device_id):
            return
        worker = self._workers.get(device_id)
        if not worker or not worker.connected or worker.busy:
            return
        telemetry = self._device_telemetry.get(device_id) or {}
        if not (telemetry.get("capture_active") or telemetry.get("capture_state") == "running"):
            return
        session = self._recovered_session_for(device_id, telemetry)
        if not session:
            return
        self._resume_attempted.add(device_id)
        self._start_session(worker, session)

    def _release_recovered_if_idle(self, device_id: str) -> None:
        """If reconnect did not find a live stack, let the scheduler own the recovered session."""
        if self._shut_down or self._active_sessions.get(device_id):
            return
        telemetry = self._device_telemetry.get(device_id) or {}
        if telemetry.get("capture_active") or telemetry.get("capture_state") == "running":
            self._maybe_resume_interrupted_session(device_id)
            return
        stale = [session_id for session_id, owner in self._recovered_sessions.items() if owner == device_id]
        for session_id in stale:
            self._recovered_sessions.pop(session_id, None)

    def _start_session(self, worker: TelescopeProcess, session: Session) -> None:
        resuming = (
            session.id in self._recovered_sessions
            or str(session.current_step or "") == "Recovered after restart"
        )
        started = (
            session.actual_started_at
            if resuming and session.actual_started_at
            else datetime.now(timezone.utc).isoformat()
        )
        session = self.store.transition(
            session.id,
            SessionStatus.RUNNING,
            actual_started_at=started,
            current_step="Joining capture" if resuming else "Starting worker",
        )
        self._recovered_sessions.pop(session.id, None)
        self._active_sessions[session.device_id] = session.id
        self._session_timing[session.id] = {
            "started": time.monotonic(),
            "steps": [],
            "step_started_at": time.time(),
            "step_wait_seconds": 0.0,
        }
        if resuming:
            self._session_capture_base[session.id] = 0
            self._session_capture_peak[session.id] = self._telemetry_frame_count(session.device_id)
            telemetry = dict(self._device_telemetry.get(session.device_id) or {})
            if not telemetry.get("capture_total") and session.camera.frame_count:
                telemetry["capture_total"] = int(session.camera.frame_count)
                self._device_telemetry[session.device_id] = telemetry
        else:
            telemetry = self._device_telemetry.get(session.device_id) or {}
            capturing = bool(telemetry.get("capture_active") or telemetry.get("capture_state") == "running")
            # History baseline uses leftover counts in case the firmware does
            # not reset; wipe the HUD unless we are about to join that stack.
            self._session_capture_base[session.id] = self._telemetry_frame_count(session.device_id)
            self._session_capture_peak[session.id] = 0
            if not capturing:
                self._hold_session_capture.add(session.device_id)
                self._reset_device_capture_progress(
                    session.device_id,
                    total=int(session.camera.frame_count or 0),
                    target=session.target.name,
                )
        self._set_activity(session.device_id, "")
        self._hold_preview_for_session(session.device_id, session.target.name)
        self._sync_mosaic_preview(session.device_id)
        self._emit_sessions_changed()
        if not resuming:
            self._notify_devices()
        if resuming:
            self.add_log("notice", f"Session resumed · {session.target.name}", session.device_id)
            self._toast(f"Session resumed · {session.target.name}", "info", "Joining the capture already running on the telescope")
        else:
            self.add_log("notice", f"Session started · {session.target.name}", session.device_id)
            self._toast(f"Session started · {session.target.name}", "info", f"{session.camera.frame_count} × {session.camera.exposure_seconds:g}s")
        worker.run_session(session, lambda ok, result: self._session_finished(session.id, ok, result))

    @Slot(str, str, float)
    def _session_progress(self, session_id: str, step: str, wait_seconds: float = 0.0) -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            return
        timing = self._session_timing.setdefault(
            session_id,
            {"started": time.monotonic(), "steps": [], "step_started_at": time.time(), "step_wait_seconds": 0.0},
        )
        base = str(step).split(" · ")[0].strip() or str(step)
        last = timing["steps"][-1][0] if timing["steps"] else ""
        last_base = str(last).split(" · ")[0].strip() or str(last)
        if base != last_base:
            timing["steps"].append((base, time.monotonic()))
            timing["step_started_at"] = time.time()
        try:
            timing["step_wait_seconds"] = max(0.0, float(wait_seconds or 0))
        except (TypeError, ValueError):
            timing["step_wait_seconds"] = 0.0
        self._apply_session_step(session, step)
        if self._preview_hold_device_id == session.device_id:
            self._refresh_preview_hold()
            self._maybe_resume_held_preview(session.device_id)
        self._sync_preview_for_capture(
            session.device_id,
            dict(self._device_telemetry.get(session.device_id) or {}),
            dict(self._device_telemetry.get(session.device_id) or {}),
        )
        self._sync_media_lock()

    def _session_finished(self, session_id: str, ok: bool, result: Any) -> None:
        session = self.store.sessions.get(session_id)
        device_id = next(
            (item_id for item_id, active_id in self._active_sessions.items() if active_id == session_id),
            session.device_id if session else "",
        )
        if (
            device_id
            and session_id in self._stop_requested
            and self._pending_actions.get(device_id) in _STOP_ACTIONS
        ):
            # The worker has left the session, but stop_astro may still be in
            # flight. Keep the HUD on Stopping until that command finishes.
            self._pending_session_finish[device_id] = (session_id, ok, result)
            worker = self._workers.get(device_id)
            if worker:
                worker.busy = True
                worker.availabilityChanged.emit()
            return
        self._finalize_session(session_id, ok, result)

    def _finalize_session(self, session_id: str, ok: bool, result: Any) -> None:
        active_device = next(
            (device_id for device_id, active_id in self._active_sessions.items() if active_id == session_id),
            None,
        )
        session = self.store.sessions.get(session_id)
        device_id = active_device or (session.device_id if session else "")
        restore_preview = bool(
            device_id
            and self._preview_hold_device_id == device_id
            and not self._preview_active
            and not self._preview_playing
        )
        self._clear_preview_hold()
        if active_device:
            self._active_sessions.pop(active_device, None)
            self._sync_session_activity(active_device, "")
        stopped = session_id in self._stop_requested
        self._stop_requested.discard(session_id)
        if not session:
            self._session_timing.pop(session_id, None)
            self._emit_sessions_changed()
            if restore_preview:
                self._restore_held_preview(device_id)
            return
        if session.status != SessionStatus.RUNNING:
            # Already finalised (for example the worker died and reported it first).
            self._session_timing.pop(session_id, None)
            self._emit_sessions_changed()
            if restore_preview:
                self._restore_held_preview(device_id)
            return
        ended = datetime.now(timezone.utc)
        started = datetime.fromisoformat(session.actual_started_at) if session.actual_started_at else ended
        if ok:
            outcome = "Completed"
        elif stopped:
            outcome = "Stopped by user"
        else:
            outcome = str(result)
        final = self.store.transition(
            session.id,
            SessionStatus.DONE if ok else SessionStatus.ERROR,
            actual_ended_at=ended.isoformat(),
            current_step=outcome,
            outcome=outcome,
        )
        captured = self._captured_frames_for(session.id, final.camera.frame_count, ok)
        self._hold_session_capture.discard(final.device_id)
        was_stack_preview = bool(
            final.device_id == self._selected_device_id
            and (
                self._preview_stack_mode
                or str(self._preview_tele_url or "").startswith("http://")
            )
        )
        self._reset_device_capture_progress(final.device_id)
        device = next((item for item in self._devices if item.id == final.device_id), None)
        self.store.history.save(history_record_for_run(
            final,
            actual_duration_seconds=(ended - started).total_seconds(),
            captured_frame_count=captured,
            hardware=device.hardware if device else None,
            step_seconds=self._finish_session_timing(session.id),
        ))
        elapsed = self._duration_text((ended - started).total_seconds())
        if ok:
            self.add_log("success", f"Session complete · {final.target.name} in {elapsed}", final.device_id)
            self._toast(f"Session complete · {final.target.name}", "success", f"Ran {elapsed}")
        elif stopped:
            self.add_log("warning", f"Session stopped · {final.target.name} after {elapsed}", final.device_id)
            self._toast(f"Session stopped · {final.target.name}", "warning", f"Ran {elapsed}")
        else:
            self.add_log("error", f"Session failed · {final.target.name}: {outcome}", final.device_id)
            self._toast(f"Session failed · {final.target.name}", "error", outcome)
        self._emit_sessions_changed()
        self.historyChanged.emit()
        if was_stack_preview or (
            final.device_id == self._selected_device_id and self._preview_result
        ):
            title, detail = self._stacking_result_copy(ok, stopped, final.target.name)
            camera = final.camera.camera
            camera_name = camera.value if hasattr(camera, "value") else str(camera or "")
            self._freeze_stacking_preview_result(
                final.device_id,
                title=title,
                detail=detail,
                target=final.target.name,
                camera=camera_name,
                since=int(started.timestamp()),
            )
        else:
            telemetry = dict(self._device_telemetry.get(final.device_id) or {})
            self._sync_preview_for_capture(final.device_id, telemetry, telemetry)
        self._sync_mosaic_preview(final.device_id)
        self._notify_devices()
        self._sync_media_lock()
        if restore_preview and not self._preview_result:
            self._restore_held_preview(final.device_id)

    def shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        try:
            self._screen_color.cancel()
        except RuntimeError:
            pass
        try:
            self.timer.stop()
        except RuntimeError:
            pass
        self._devices_notify_timer.stop()
        self._retarget_timer.stop()
        self._stack_result_timer.stop()
        self._stellarium_rc_timer.stop()
        self.stopPreview()
        self._enhance_pool.waitForDone(1500)
        self._enhance_cache_pool.waitForDone(1500)
        self._tele_player.abort()
        self._wide_player.abort()
        set_live_frames(None)
        for worker in list(self._workers.values()):
            worker.shutdown(wait=False)
        if self._preview_thread.isRunning():
            self._preview_thread.quit()
            self._preview_thread.wait(500)

    def _sequence_colliding_mosaics(self) -> None:
        changed = False
        for device in self._devices:
            if self._pack_device_schedule(device.id, notify=False):
                changed = True
        if changed:
            self._emit_sessions_changed()

    def _reset_device_capture_progress(self, device_id: str, total: int = 0, target: str = "") -> None:
        """Clear leftover stacking counts on the HUD after a session starts or ends."""
        telemetry = dict(self._device_telemetry.get(device_id) or {})
        telemetry.update({
            "capture_current": 0,
            "capture_stacked": 0,
            "capture_total": int(total or 0),
            "capture_active": False,
            "capture_state": "idle",
            "mosaic_active": False,
            "mosaic_index": 0,
            "capture_target": target or "",
            "capture_shooting_s": 0,
            "capture_stacked_s": 0,
            "exposure_elapsed_s": 0,
        })
        self._device_telemetry[device_id] = telemetry
        self._telemetry_updated[device_id] = time.time()

    def _telemetry_frame_count(self, device_id: str) -> int:
        raw = self._device_telemetry.get(device_id) or {}
        peak = 0
        for key in ("capture_stacked", "capture_current"):
            try:
                peak = max(peak, int(raw.get(key) or 0))
            except (TypeError, ValueError):
                continue
        return peak

    def _track_session_capture(self, device_id: str, telemetry: dict[str, Any]) -> None:
        session_id = self._active_sessions.get(device_id)
        if not session_id:
            return
        observed = 0
        for key in ("capture_stacked", "capture_current"):
            try:
                observed = max(observed, int(telemetry.get(key) or 0))
            except (TypeError, ValueError):
                continue
        base = self._session_capture_base.get(session_id, 0)
        gained = observed if observed < base else max(0, observed - base)
        self._session_capture_peak[session_id] = max(self._session_capture_peak.get(session_id, 0), gained)

    def _captured_frames_for(self, session_id: str, planned: int, ok: bool) -> int:
        captured = self._session_capture_peak.pop(session_id, 0)
        self._session_capture_base.pop(session_id, None)
        planned = max(0, int(planned or 0))
        if captured <= 0:
            return planned if ok else 0
        return min(planned, captured)

    def _device_by_id(self, device_id: str) -> Device:
        return next(item for item in self._devices if item.id == device_id)

    def _cutoff_hour(self) -> int:
        return clamp_cutoff_hour(self._settings.observing_day_cutoff_hour)

    def _persist_app_settings(self) -> None:
        self.store.save_app_settings(self._settings)
        self._sync_shared_device_fields()
        self.appSettingsChanged.emit()
        self.clockChanged.emit()
        self._emit_sessions_changed()
        self._notify_devices()

    def _persist_last_device_id(self, device_id: str) -> None:
        wanted = str(device_id or "")
        if wanted == self._settings.last_device_id:
            return
        self._settings = replace(self._settings, last_device_id=wanted)
        self.store.save_app_settings(self._settings)

    def _sync_shared_device_fields(self) -> None:
        cutoff = self._cutoff_hour()
        url = self._settings.stellarium_url
        updated: list[Device] = []
        workers = getattr(self, "_workers", {})
        for device in self._devices:
            if device.observing_day_cutoff_hour == cutoff and device.stellarium_url == url:
                updated.append(device)
                continue
            item = replace(device, observing_day_cutoff_hour=cutoff, stellarium_url=url)
            self.store.devices.save(item)
            worker = workers.get(item.id)
            if worker:
                worker.device = item
            updated.append(item)
        self._devices = updated

    _WORKER_CONFIG_FIELDS = (
        "ip_address",
        "model",
        "wifi_mode",
        "wifi_ssid",
        "wifi_password",
        "ble_password",
        "ble_enabled",
        "latitude",
        "longitude",
        "timezone_name",
    )

    def _worker_config_changed(self, previous: Device, updated: Device) -> bool:
        return any(getattr(previous, name) != getattr(updated, name) for name in self._WORKER_CONFIG_FIELDS)

    def _commit_device(self, previous: Device, updated: Device) -> bool:
        restart = self._worker_config_changed(previous, updated)
        if restart:
            if updated.id in self._active_sessions:
                self._toast("Stop the running session before changing connection settings", "warning")
                return False
            if (
                updated.id in self._connecting_ids
                or updated.id in self._disconnecting_ids
                or updated.id in self._cancel_connect_ids
            ):
                self._toast("Wait for the connection to finish before changing those settings", "warning")
                return False
        self.store.devices.save(updated)
        self._devices = [updated if item.id == updated.id else item for item in self._devices]
        worker = self._workers.get(updated.id)
        if restart:
            was_connected = bool(worker and worker.connected)
            self._create_worker(updated, reconnect=was_connected)
        elif worker:
            worker.device = updated
        return True

    def _night_start(self, day: str, device: Device | None = None) -> datetime:
        item = device or self._device_by_id(self._selected_device_id)
        tz = self._zone_for(item)
        cutoff = self._cutoff_hour()
        start_date = date.fromisoformat(day)
        return datetime(start_date.year, start_date.month, start_date.day, cutoff, 0, tzinfo=tz)

    def _device_or_selected(self, device_id: str = "") -> Device | None:
        wanted = str(device_id or "").strip()
        if wanted:
            match = next((item for item in self._devices if item.id == wanted), None)
            if match:
                return match
        return self._device_by_id(self._selected_device_id)

    @Slot(str, result=float)
    @Slot(str, str, result=float)
    def nightStartEpochMs(self, day: str, device_id: str = "") -> float:
        try:
            return self._night_start(day, self._device_or_selected(device_id)).timestamp() * 1000
        except (ValueError, StopIteration):
            return 0.0

    @Slot(str, int, result=str)
    @Slot(str, int, str, result=str)
    def nightTimelineIso(self, day: str, minutes: int, device_id: str = "") -> str:
        try:
            device = self._device_or_selected(device_id)
            start = self._night_start(day, device)
        except (ValueError, StopIteration):
            return ""
        value = start + timedelta(minutes=max(0, min(1435, int(minutes))))
        return store_local_iso(value, self._zone_for(device))

    def _zone_for(self, device: Device | None = None):
        item = device or self._device_by_id(self._selected_device_id)
        return zoneinfo_from_name(item.timezone_name if item else "UTC")

    def _zone_for_id(self, device_id: str):
        return self._zone_for(self._device_by_id(device_id))

    def _now_local(self, device: Device | None = None) -> datetime:
        return datetime.now(self._zone_for(device))

    def _store_session_time(self, value: datetime | str, device: Device | None = None) -> str:
        tz = self._zone_for(device)
        parsed = parse_in_zone(value, tz) if isinstance(value, str) else value
        return store_local_iso(parsed, tz)

    def _finish_session_timing(self, session_id: str) -> dict[str, float]:
        log = self._session_timing.pop(session_id, None)
        if not log:
            return {}
        started = float(log.get("started") or time.monotonic())
        steps = list(log.get("steps") or [])
        ended = time.monotonic()
        marks: list[tuple[str, float]] = [("Session start", started), *steps]
        out: dict[str, float] = {}
        for index, (name, stamp) in enumerate(marks):
            finish = marks[index + 1][1] if index + 1 < len(marks) else ended
            elapsed = max(0.0, float(finish) - float(stamp))
            if elapsed < 0.05:
                continue
            key = str(name)
            out[key] = round(out.get(key, 0.0) + elapsed, 1)
        return out

    @staticmethod
    def _duration_text(seconds: float) -> str:
        hours, remainder = divmod(max(0, int(seconds)), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"

    def _history_date(self, value: str | None, device: Device | None) -> str:
        if not value:
            return ""
        try:
            tz = self._zone_for(device) if device is not None else zoneinfo_from_name("UTC")
            return parse_in_zone(value, tz).date().isoformat()
        except (ValueError, TypeError, OSError):
            return str(value)[:10]

    def _stamp_text(self, value: str | None, device: Device | None = None) -> str:
        if not value:
            return "—"
        try:
            tz = self._zone_for(device) if device is not None else zoneinfo_from_name("UTC")
            return parse_in_zone(value, tz).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, OSError):
            text = str(value).replace("T", " ")
            return text[:16] if len(text) >= 16 else text

    @staticmethod
    def _local_path(raw_path: str) -> Path:
        url = QUrl(raw_path)
        return Path(url.toLocalFile() if url.isLocalFile() else raw_path)
