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

from .version import __version__
from .domain import (
    Camera,
    CameraSettings,
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
    album_http_url,
    album_path_matches_model,
    clamp_cutoff_hour,
    device_from_dict,
    firmware_exposure_name,
    history_record_for_run,
    normalized_stellarium_url,
    session_from_dict,
    to_dict,
)
from .services import (
    DurationEngine,
    StellariumClient,
    import_telescopius,
    mosaic_group_title,
    mosaic_pane_workflow,
    next_free_start,
    observing_date,
    pane_sort_key,
    parse_in_zone,
    session_window,
    sessions_overlap,
    stagger_mosaic_sessions,
    store_local_iso,
    zoneinfo_from_name,
)
from .duration_suggest import suggest_hardware_profile
from .location import has_site_coordinates, match_timezone, resolve_location, suggested_timezone, timezone_locations
from .runtime import PROCESS_CREATION_FLAGS, kill_pid_tree, prepare_worker_environment, worker_command
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
    set_model_dir,
)
from .stream_preview import LiveFrames, StreamPlayer, port_is_open, preview_window_is_live, set_live_frames, stream_port
from .telemetry_view import AlertEngine, derive_activity, format_telemetry


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

    def connect_device(self, callback: Callable[[bool, Any], None]) -> None:
        self.send("connect", callback=lambda ok, result: self._connected(ok, result, callback))

    def _connected(self, ok: bool, result: Any, callback: Callable[[bool, Any], None]) -> None:
        self.connected = bool(ok and result)
        self.availabilityChanged.emit()
        callback(self.connected, result)

    def disconnect_device(self, callback: Callable[[bool, Any], None] | None = None) -> None:
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
                if not self.connected:
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
    "go_live": "Live view",
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

    def append(self, entry: dict[str, Any]) -> None:
        last = self._all[-1] if self._all else None
        if (
            last is not None
            and last["message"] == entry["message"]
            and last["level"] == entry["level"]
            and last["device"] == entry["device"]
        ):
            last["count"] = int(last.get("count", 1)) + 1
            last["time"] = entry["time"]
            self._note_unread(last["level"])
            if self._visible and self._visible[-1] is last:
                row = len(self._visible) - 1
                self.dataChanged.emit(self.index(row), self.index(row), [self.TimeRole, self.CountRole])
            return
        entry.setdefault("count", 1)
        self._all.append(entry)
        level = entry["level"]
        if level in self._counts:
            self._counts[level] += 1
            self._note_unread(level)
        if self._is_visible(entry):
            row = len(self._visible)
            self.beginInsertRows(QModelIndex(), row, row)
            self._visible.append(entry)
            self.endInsertRows()
        if len(self._all) > _LOG_LIMIT:
            self._trim(_LOG_TRIM_BATCH + len(self._all) - _LOG_LIMIT)

    def _trim(self, count: int) -> None:
        removed = self._all[:count]
        removed_ids = {id(entry) for entry in removed}
        del self._all[:count]
        for entry in removed:
            if entry["level"] in self._counts:
                self._counts[entry["level"]] = max(0, self._counts[entry["level"]] - 1)
        for level in self._unread:
            self._unread[level] = min(self._unread[level], self._counts[level])
        drop = 0
        while drop < len(self._visible) and id(self._visible[drop]) in removed_ids:
            drop += 1
        if drop:
            self.beginRemoveRows(QModelIndex(), 0, drop - 1)
            del self._visible[:drop]
            self.endRemoveRows()
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
        self._visible = [entry for entry in self._all if self._is_visible(entry)]
        self.endResetModel()

    def set_show_debug(self, enabled: bool, force: bool = False) -> None:
        self.set_filter("debug" if enabled else "all")

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
    showDebugLogsChanged = Signal()
    selectedDeviceChanged = Signal()
    statusChanged = Signal()
    schedulerEnabledChanged = Signal()
    clockChanged = Signal()
    sessionProgressChanged = Signal()
    toast = Signal(str, str, str)
    commandFeedback = Signal(str, str, bool)
    logFilterChanged = Signal()
    logCountsChanged = Signal()
    locationLookupReady = Signal("QVariantMap")
    _asyncResult = Signal(str, object)
    uiBusyChanged = Signal()
    previewActiveChanged = Signal()
    previewPlayingChanged = Signal()
    previewStatusChanged = Signal()
    previewGenerationChanged = Signal()
    previewTelePlayingChanged = Signal()
    previewWidePlayingChanged = Signal()
    previewTeleGenerationChanged = Signal()
    previewWideGenerationChanged = Signal()
    previewHoldChanged = Signal()
    previewStackingChanged = Signal()
    enhanceImagesChanged = Signal()
    deepCleanImagesChanged = Signal()
    enhanceCacheChanged = Signal()
    albumChanged = Signal()
    mediaChanged = Signal()
    mediaItemsChanged = Signal()
    appSettingsChanged = Signal()
    _openTeleStream = Signal(str)
    _openWideStream = Signal(str)
    _closeWideStream = Signal()
    _closePreviewStreams = Signal()
    _previewReady = Signal(int, str, str)

    def __init__(self, data_root: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.store = SessionStore(data_root)
        set_model_dir(Path(data_root) / "models")
        self._devices = self.store.devices.all()
        if not self._devices:
            self._devices = [self.store.seed_device()]
        self._settings = self.store.load_app_settings(self._devices)
        self._selected_device_id = self._devices[0].id
        self._log_model = LogListModel(self)
        self._log_model.countsChanged.connect(self.logCountsChanged)
        self._show_debug_logs = False
        self._workers: dict[str, TelescopeProcess] = {}
        self._active_sessions: dict[str, str] = {}
        self._stop_requested: set[str] = set()
        self._scheduler_enabled = False
        self._clock_text = datetime.now(self._zone_for()).strftime("%H:%M:%S")
        self._connecting_ids: set[str] = set()
        self._cancel_connect_ids: set[str] = set()
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
        self._joystick_inflight: set[str] = set()
        self._joystick_pending: dict[str, tuple[float, float]] = {}
        self._ui_busy = ""
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
        self._preview_token = 0
        self._preview_active = False
        self._preview_playing = False
        self._preview_tele_playing = False
        self._preview_wide_playing = False
        self._preview_status = ""
        self._preview_generation = 0
        self._preview_tele_generation = 0
        self._preview_wide_generation = 0
        self._last_preview_ui: dict[str, float] = {}
        self._preview_window = None
        self._preview_window_filter = None
        self._preview_hold_device_id = ""
        self._preview_hold_target = ""
        self._preview_tele_url = ""
        self._preview_wide_url = ""
        self._preview_stack_mode = False
        self._enhance_images = True
        self._deep_clean_images = False
        self._raw_preview_images = {"tele": QImage(), "wide": QImage()}
        self._enhance_job_token = {"tele": 0, "wide": 0}
        self._enhance_pool = QThreadPool(self)
        self._enhance_pool.setMaxThreadCount(1)
        self._preview_enhance_signals = PreviewEnhanceSignals(self)
        self._preview_enhance_signals.finished.connect(self._on_preview_enhanced)
        self._enhance_cache_rev = 0
        self._enhance_inflight: set[str] = set()
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
            telemetry = format_telemetry(
                self._device_telemetry.get(device.id, {}) if connected else {},
                self._telemetry_updated.get(device.id) if connected else None,
                now,
            )
            activity = telemetry["activity"] or self._device_activity.get(device.id, "")
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
            # The device now reports the real activity; drop the UI-side guess.
            self._device_activity[device_id] = activity
        elif previous and derive_activity(previous)[0]:
            self._device_activity.pop(device_id, None)
            session_id = self._active_sessions.get(device_id)
            session = self.store.sessions.get(session_id) if session_id else None
            if session:
                wanted = _activity_for_session_step(session.current_step)
                if wanted:
                    self._device_activity[device_id] = wanted
        if data.get("power_off"):
            self._drop_device_link(device_id)
            return
        self._track_session_capture(device_id, current)
        self._maybe_resume_held_preview(device_id)
        self._maybe_resume_interrupted_session(device_id)
        self._sync_preview_for_capture(device_id, previous, current)
        self._notify_devices(immediate=False)
        self._sync_media_lock()

    def _toast(self, message: str, level: str = "info", detail: str = "") -> None:
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
        self.toast.emit(text, level, str(detail or ""))

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
        device_names = {device.id: device.name for device in self._devices}
        device_colors = {device.id: device.color for device in self._devices}
        result = []
        for record in sorted(self.store.history.all(), key=lambda item: item.recorded_at, reverse=True):
            session = self.store.sessions.get(record.session_id)
            data = to_dict(record)
            data["device_name"] = device_names.get(record.device_id, "Unknown")
            data["device_color"] = device_colors.get(record.device_id, "#4DE8FF")
            data["date"] = record.scheduled_start[:10]
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
            data["scheduled_text"] = self._stamp_text(record.scheduled_start)
            data["started_text"] = self._stamp_text(record.actual_started_at)
            data["ended_text"] = self._stamp_text(record.actual_ended_at)
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

    @Property(bool, notify=showDebugLogsChanged)
    def showDebugLogs(self) -> bool:
        return self._show_debug_logs

    @Slot(bool)
    def setShowDebugLogs(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._show_debug_logs == enabled:
            return
        self._show_debug_logs = enabled
        self._log_model.set_filter("debug" if enabled else "all")
        self.showDebugLogsChanged.emit()
        self.logFilterChanged.emit()

    @Property(str, notify=logFilterChanged)
    def logFilter(self) -> str:
        return self._log_model.filter_name

    @Slot(str)
    def setLogFilter(self, name: str) -> None:
        self._log_model.set_filter(str(name or "all"))
        debug = self._log_model.filter_name == "debug"
        if debug != self._show_debug_logs:
            self._show_debug_logs = debug
            self.showDebugLogsChanged.emit()
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

    @Property(int, notify=previewGenerationChanged)
    def previewGeneration(self) -> int:
        return self._preview_generation

    @Property(bool, notify=previewTelePlayingChanged)
    def previewTelePlaying(self) -> bool:
        return self._preview_tele_playing

    @Property(bool, notify=previewWidePlayingChanged)
    def previewWidePlaying(self) -> bool:
        return self._preview_wide_playing

    @Property(int, notify=previewTeleGenerationChanged)
    def previewTeleGeneration(self) -> int:
        return self._preview_tele_generation

    @Property(int, notify=previewWideGenerationChanged)
    def previewWideGeneration(self) -> int:
        return self._preview_wide_generation

    @Property(bool, notify=previewHoldChanged)
    def previewHeld(self) -> bool:
        return bool(self._preview_hold_device_id) and self._preview_hold_device_id == self._selected_device_id

    @Property(bool, notify=previewStackingChanged)
    def previewStacking(self) -> bool:
        return bool(self._preview_stack_mode)

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
            return QUrl.fromLocalFile(str(dest.resolve())).toString()
        if key not in self._enhance_inflight:
            self._enhance_inflight.add(key)
            self._enhance_pool.start(
                CacheEnhanceJob(key, text, "deep" if kind == "deep" else "standard", dest, self._cache_enhance_signals)
            )
        return ""

    @Slot(str, result=str)
    def mediaFileUrl(self, path: str) -> str:
        return self._media_file_url(path)

    def _enhance_cache_dir(self) -> Path:
        folder = self.store.root / "enhance-cache"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _on_enhance_cache_ready(self, key: str) -> None:
        self._enhance_inflight.discard(str(key or ""))
        dest = self._enhance_cache_dir() / f"{str(key or '')}.jpg"
        if not is_enhance_cache_valid(dest):
            return
        self._enhance_cache_rev += 1
        self.enhanceCacheChanged.emit()

    @Property("QVariantList", notify=albumChanged)
    def albumItems(self) -> list[dict[str, Any]]:
        return list(self._album_items)

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

    @Property(str, notify=albumChanged)
    def lastAlbumPath(self) -> str:
        return self._album_path

    @Property(str, notify=albumChanged)
    def lastAlbumUrl(self) -> str:
        if not self._album_path:
            return ""
        return Path(self._album_path).resolve().as_uri()

    @Property(str, notify=albumChanged)
    def albumBusy(self) -> str:
        return self._album_busy

    @Property(str, notify=mediaChanged)
    def mediaBusy(self) -> str:
        return self._album_busy

    @Property(bool, notify=mediaChanged)
    def mediaLocked(self) -> bool:
        return self._session_is_capturing(self._selected_device_id)

    @Property(str, notify=mediaChanged)
    def albumFolderUrl(self) -> str:
        return self._album_dir().resolve().as_uri()

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
            self._begin_stream_wait(token, tele_url, wide_url, host, port)

        def after_photo(ok: bool, result: Any) -> None:
            if token != self._preview_token:
                return
            if not ok:
                after_cameras(False, result)
                return
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
                self.add_log("warning", f"GO LIVE: {result}", device_id)
            worker.send("photo_mode", callback=after_photo)

        worker.send("go_live", callback=after_live)

    def _arm_preview_ui(self, status: str) -> int:
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
        self.previewGenerationChanged.emit()
        self.previewTeleGenerationChanged.emit()
        self.previewWideGenerationChanged.emit()

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

    def _sync_preview_for_capture(
        self,
        device_id: str,
        previous: dict[str, Any],
        current: dict[str, Any],
    ) -> None:
        """Move Dwarf 3/Mini live view onto the HTTP stacking JPEG during capture."""
        if device_id != self._selected_device_id or not self._preview_active:
            return
        if self._device_is_stopping(device_id):
            return
        stacking = self._preview_stacking(device_id)
        device = self._device_by_id(device_id)
        tele_url = self._stream_url(device, Camera.TELE, stacking=stacking)
        wide_url = self._stream_url(device, Camera.WIDE, stacking=stacking)
        mode_changed = stacking != self._preview_stack_mode
        urls_changed = tele_url != self._preview_tele_url or wide_url != self._preview_wide_url
        if not mode_changed and not self._preview_tele_url:
            return
        if mode_changed or urls_changed:
            was_stacking = self._preview_stack_mode
            self._set_preview_stack_mode(stacking)
            if stacking and not was_stacking:
                self.add_log(
                    "info",
                    "Capture started — switching live view to the stacking preview",
                    device_id,
                )
            elif not stacking and was_stacking:
                self.add_log("info", "Capture ended — restoring RTSP live view", device_id)
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
        if not self._preview_active or not preview_window_is_live(self._preview_window):
            return
        self.live_images.notify("*")

    def _should_enhance_preview(self) -> bool:
        return bool(self._enhance_images) and bool(self._preview_stack_mode)

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
        if self._shut_down or not self._preview_active:
            return
        if token != self._enhance_job_token.get(camera):
            return
        if not isinstance(image, QImage) or image.isNull() or not self._should_enhance_preview():
            return
        self.live_images.update(camera, image)
        if preview_window_is_live(self._preview_window):
            self.live_images.notify(camera)

    def _refresh_preview_enhance(self) -> None:
        if not self._preview_active:
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
        raw = image.copy() if isinstance(image, QImage) and not image.isNull() else QImage()
        self._raw_preview_images[camera] = raw
        if self._should_enhance_preview():
            shown = self.live_images.peek(camera)
            if shown.isNull():
                self.live_images.update(camera, raw)
            self._queue_preview_enhance(camera, raw)
        else:
            self.live_images.update(camera, raw)
        first_frame = (camera == "wide" and not self._preview_wide_playing) or (
            camera == "tele" and not self._preview_tele_playing
        )
        window_live = preview_window_is_live(self._preview_window)
        now = time.monotonic()
        if not first_frame:
            if now - self._last_preview_ui.get(camera, 0.0) < 0.05:
                return
            if not window_live:
                return
        self._last_preview_ui[camera] = now
        if first_frame:
            self._preview_generation += 1
            if camera == "wide":
                self._preview_wide_generation += 1
                self._preview_wide_playing = True
                self.previewWidePlayingChanged.emit()
                self.previewWideGenerationChanged.emit()
            else:
                self._preview_tele_generation += 1
                self._preview_tele_playing = True
                self.previewTelePlayingChanged.emit()
                self.previewTeleGenerationChanged.emit()
            if not self._preview_playing:
                self._preview_playing = True
                self._set_preview_status(self.videoUrl)
                self.previewPlayingChanged.emit()
            self.previewGenerationChanged.emit()
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

    @Property(str, notify=uiBusyChanged)
    def uiBusy(self) -> str:
        return self._ui_busy

    def _set_ui_busy(self, operation: str) -> None:
        if self._ui_busy == operation:
            return
        self._ui_busy = operation
        self.uiBusyChanged.emit()

    @Slot(str)
    def connectDevice(self, device_id: str) -> None:
        device = next((item for item in self._devices if item.id == device_id), None)
        if not device or device_id in self._connecting_ids:
            return
        if not device.location_configured:
            self._toast("Choose an observing location before connecting the telescope", "warning")
            return
        worker = self._workers[device_id]
        self._connecting_ids.add(device_id)
        self._notify_devices()
        self.add_log("info", "Connection requested; UI remains available", device_id)
        worker.connect_device(lambda ok, result: self._connection_done(device_id, ok, result))

    @Slot(str)
    def cancelConnect(self, device_id: str) -> None:
        worker = self._workers.get(device_id)
        if not worker or device_id not in self._connecting_ids or device_id in self._cancel_connect_ids:
            return
        if device_id == self._selected_device_id:
            self.stopPreview()
        self._cancel_connect_ids.add(device_id)
        self.add_log("info", "Cancelling connection", device_id)
        self._notify_devices()

        def done(_ok: bool, _result: Any) -> None:
            self._cancel_connect_ids.discard(device_id)
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

        worker.disconnect_device(done)

    def _persist_discovered_ip(self, device_id: str, ip_address: str) -> None:
        current = self._device_by_id(device_id)
        if not current or not ip_address or current.ip_address == ip_address:
            return
        updated = replace(current, ip_address=ip_address)
        self.store.devices.save(updated)
        self._devices = [updated if item.id == updated.id else item for item in self._devices]
        worker = self._workers.get(device_id)
        if worker:
            worker.device = updated
        self.add_log("info", f"Saved Bluetooth IP {ip_address}", device_id)

    def _connection_done(self, device_id: str, ok: bool, result: Any) -> None:
        cancelled = (
            device_id in self._cancel_connect_ids
            or (not ok and "connection cancelled" in str(result or "").lower())
        )
        self._connecting_ids.discard(device_id)
        if ok and isinstance(result, dict) and result.get("ip_address"):
            self._persist_discovered_ip(device_id, str(result["ip_address"]))
        if cancelled:
            if ok:
                self.add_log("info", "Connected, dropping the link after cancel", device_id)
            self._notify_devices()
            return
        self.add_log("success" if ok else "error", "Connected" if ok else f"Connection failed: {result}", device_id)
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
            QTimer.singleShot(8000, lambda did=device_id: self._release_recovered_if_idle(did))
            delay_ms = 8000 if device and device.model == DeviceModel.DWARF_3 else 2500
            QTimer.singleShot(delay_ms, lambda did=device_id: self.refreshCameraParams(did))
        else:
            self._toast("Connection failed", "error", str(result))
            self._disarm_scheduler_if_offline()
        self._notify_devices()

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
        self._begin_activity(device_id, operation)

        label = _ACTION_LABELS.get(operation, operation.replace("_", " ").title())
        dropping = operation in {"reboot", "power_down"}
        if dropping:
            self._abort_active_session(device_id, label)

        def done(ok: bool, result: Any) -> None:
            self._complete_activity(device_id, operation, ok)
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
        elif operation == "stack":
            device = self._device_by_id(device_id)
            camera = device.camera.value if device and hasattr(device.camera, "value") else "tele"
            payload = {"args": [camera]}
        worker.send(operation, payload, callback=self._with_pending(device_id, operation, done))
        if dropping:
            self._drop_device_link(device_id)

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
        telemetry = self._device_telemetry.get(device_id) or {}
        try:
            fov_h = float(telemetry.get("wide_fov_h") or 0)
            fov_v = float(telemetry.get("wide_fov_v") or 0)
        except (TypeError, ValueError):
            fov_h = fov_v = 0.0
        if fov_h <= 0 or fov_v <= 0:
            fov_h, fov_v = 45.06, 25.93
        if diag:
            self.add_log("debug", f"Center tap map {diag}", device_id)

        def done(ok: bool, result: Any) -> None:
            if not ok:
                self.add_log("error", f"Center on tap failed: {result}", device_id)
                return
            detail = result if isinstance(result, dict) else {}
            if detail.get("ok") is False:
                self.add_log("error", "Center on tap failed", device_id)
                return
            self._toast("Target centered", "success", "Press TRACK to start sidereal tracking, then STACK")

        worker.send("center_tap", {"args": [nx, ny, fov_h, fov_v]}, done)

    @Slot(str, int)
    def manualFocus(self, device_id: str, direction: int) -> None:
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
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

    @Slot(str, result=bool)
    def addDevice(self, payload: str) -> bool:
        colors = ["#62A0FF", "#E879F9", "#34D399", "#FBBF24", "#FB7185"]
        current = next((item for item in self._devices if item.id == self._selected_device_id), None)
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
            device = Device(
                name=f"Dwarf {len(self._devices) + 1}",
                color=colors[len(self._devices) % len(colors)],
                model=model,
                ip_address="",
                timezone_name=timezone_name,
                latitude=latitude,
                longitude=longitude,
                location_configured=has_site_coordinates(latitude, longitude),
                observing_day_cutoff_hour=self._cutoff_hour(),
                stellarium_url=self._settings.stellarium_url,
            )
            self.store.devices.save(device)
            self._devices.append(device)
            self._create_worker(device)
            self._selected_device_id = device.id
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
            self._selected_device_id = self._devices[0].id
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

    @Slot(str)
    def deleteTemplate(self, template_id: str) -> None:
        self.deleteTemplates([template_id])

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
        if current.camera == Camera(camera):
            return
        updated = replace(current, camera=Camera(camera))
        self.store.devices.save(updated)
        self._devices = [updated if item.id == updated.id else item for item in self._devices]
        self._notify_devices()

    @Slot(str, str, str)
    def setCameraParam(self, device_id: str, name: str, value: str) -> None:
        device = self._device_by_id(device_id)
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        camera = device.camera.value if hasattr(device.camera, "value") else str(device.camera)
        model_id = {DeviceModel.DWARF_II: "2", DeviceModel.DWARF_3: "3", DeviceModel.DWARF_MINI: "5"}.get(device.model, "3")
        if name == "exposure":
            operation, args = "set_exposure", [firmware_exposure_name(value), model_id, camera]
        elif name == "focus":
            try:
                operation, args = "set_focus", [int(round(float(value)))]
            except (TypeError, ValueError):
                self._toast("Focus must be a number", "error")
                return
        elif name == "gain":
            operation, args = "set_gain", [int(value), camera]
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
        self.albumChanged.emit()
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
            (item.get("id"), item.get("thumbnail_url"), item.get("image_url"), item.get("downloaded"))
            for item in items
        )

    def _media_file_url(self, path: str) -> str:
        if not path:
            return ""
        return QUrl.fromLocalFile(str(Path(path).resolve())).toString(QUrl.ComponentFormattingOption.FullyEncoded)

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
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".fits", ".fit"}:
                found[path.name] = path
        return found

    def _normalize_astro_item(self, entry: dict[str, Any], ip: str, local_files: dict[str, Path]) -> dict[str, Any] | None:
        thumb = str(entry.get("thumbnailPath") or "").strip()
        remote = str(entry.get("filePath") or "").strip()
        if not thumb and not remote:
            return None
        details = self._astro_details(entry)
        params = details.get("params") if isinstance(details.get("params"), dict) else {}
        target = str(details.get("target") or entry.get("fileName") or "Untitled")
        local_name = self._local_name_for_remote(remote or thumb)
        local = local_files.get(local_name)
        thumb_url = album_http_url(ip, thumb) if thumb and ip else ""
        image_url = album_http_url(ip, remote) if remote and ip else thumb_url
        item_id = remote or thumb or local_name
        return {
            "id": item_id,
            "source": "astro",
            "target": target,
            "file_name": str(entry.get("fileName") or local_name),
            "file_path": remote,
            "thumbnail_path": thumb,
            "thumbnail_url": self._media_file_url(str(local)) if local else thumb_url,
            "image_url": self._media_file_url(str(local)) if local else image_url,
            "date": self._format_media_time(entry.get("modificationTime")),
            "modification_time": int(entry.get("modificationTime") or 0),
            "exposure": str(params.get("exp") or ""),
            "gain": str(params.get("gain") or ""),
            "ir_filter": str(params.get("filter") or ""),
            "local_path": str(local) if local else "",
            "downloaded": bool(local),
        }

    def _normalize_still_item(self, name: str, local_files: dict[str, Path]) -> dict[str, Any]:
        local = local_files.get(name)
        return {
            "id": name,
            "source": "stills",
            "target": name,
            "file_name": name,
            "file_path": name,
            "thumbnail_path": "",
            "thumbnail_url": self._media_file_url(str(local)) if local else "",
            "image_url": self._media_file_url(str(local)) if local else "",
            "date": "",
            "modification_time": int(local.stat().st_mtime) if local else 0,
            "exposure": "",
            "gain": "",
            "ir_filter": "",
            "local_path": str(local) if local else "",
            "downloaded": bool(local),
        }

    def _normalize_local_item(self, path: Path) -> dict[str, Any]:
        url = self._media_file_url(str(path))
        try:
            mtime = int(path.stat().st_mtime)
        except OSError:
            mtime = 0
        return {
            "id": str(path),
            "source": "local",
            "target": path.stem,
            "file_name": path.name,
            "file_path": str(path),
            "thumbnail_path": "",
            "thumbnail_url": url,
            "image_url": url,
            "date": self._format_media_time(mtime),
            "modification_time": mtime,
            "exposure": "",
            "gain": "",
            "ir_filter": "",
            "local_path": str(path),
            "downloaded": True,
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
        self._media_status = str(status or "")
        self._emit_media(items=True)

    def _begin_media_request(self, device_id: str, source: str) -> int:
        self._media_request_id += 1
        self._media_device_id = device_id
        self._media_source = source
        return self._media_request_id

    def _media_request_current(self, request_id: int, device_id: str, source: str) -> bool:
        return (
            request_id == self._media_request_id
            and self._media_device_id == device_id
            and self._media_source == source
        )

    def _media_can_auto_list(self, device_id: str) -> bool:
        worker = self._workers.get(device_id)
        if worker and worker.connected:
            return True
        device = next((item for item in self._devices if item.id == device_id), None)
        ip = str(getattr(device, "ip_address", "") or "").strip()
        if not device or not ip:
            return False
        claimants = [
            other for other in self._devices
            if str(other.ip_address or "").strip() == ip
        ]
        return len(claimants) == 1

    def _camera_mode_id(self, device_id: str) -> int:
        mode = self._device_telemetry.get(device_id, {}).get("shooting_mode")
        try:
            return int(mode) if mode is not None else 1
        except (TypeError, ValueError):
            return 1

    @Slot(str)
    def refreshCameraParams(self, device_id: str) -> None:
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        mode_id = self._camera_mode_id(device_id)

        def done(ok: bool, result: Any) -> None:
            if not ok or not isinstance(result, dict):
                return
            cameras = result.get("cameras") or {}
            camera = cameras.get(0) or cameras.get("0") or {}
            wide = cameras.get(1) or cameras.get("1") or {}
            changes: dict[str, Any] = {}
            exposure = (camera.get("exposure") or {}) if isinstance(camera, dict) else {}
            gain = (camera.get("gain") or {}) if isinstance(camera, dict) else {}
            if exposure.get("name"):
                changes["exposure_text"] = str(exposure["name"])
            if gain.get("value") is not None:
                changes["gain"] = int(gain["value"])
            wide_exposure = (wide.get("exposure") or {}) if isinstance(wide, dict) else {}
            wide_gain = (wide.get("gain") or {}) if isinstance(wide, dict) else {}
            if wide_exposure.get("name"):
                changes["wide_exposure_text"] = str(wide_exposure["name"])
            if wide_gain.get("value") is not None:
                changes["wide_gain"] = int(wide_gain["value"])
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
        if quiet and not self._media_can_auto_list(device_id):
            device = next((item for item in self._devices if item.id == device_id), None)
            ip = str(getattr(device, "ip_address", "") or "").strip()
            if not ip:
                self._clear_media("Set the telescope IP in Settings, then refresh to browse sessions on the device.")
            else:
                self._clear_media(
                    "Connect this telescope to browse its album. "
                    "Other profiles share this IP, so media is not shown until this device is connected."
                )
            return
        if self._media_source == "stills":
            self.listAlbum(device_id, quiet)
            return
        self.listAstroSessions(device_id, quiet)

    @Slot()
    def listLocalAlbum(self) -> None:
        self._media_source = "local"
        self._media_device_id = ""
        items = [self._normalize_local_item(path) for path in self._local_album_paths().values()]
        self._replace_media_items(items, self._media_selected_id)
        self._set_media_status("" if items else "No downloaded files in the local album yet.")

    @Slot(str)
    @Slot(str, bool)
    def listAstroSessions(self, device_id: str, quiet: bool = False) -> None:
        worker = self._workers.get(device_id)
        device = next((item for item in self._devices if item.id == device_id), None)
        if not worker or not device or not str(device.ip_address or "").strip():
            self._clear_media("Set the telescope IP in Settings before listing sessions.")
            if not quiet:
                self._toast("Set the telescope IP before listing sessions", "warning")
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
                    self._set_media_status("No astro sessions found on this telescope.")
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
        if not worker or not device or not str(device.ip_address or "").strip():
            self._clear_media("Set the telescope IP in Settings before listing stills.")
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._clear_media(_MEDIA_LOCKED_STATUS)
            if not quiet:
                self._toast("Can't browse the album while the telescope is capturing", "warning")
            return
        camera = device.camera.value if hasattr(device.camera, "value") else "tele"
        request_id = self._begin_media_request(device_id, "stills")
        self._set_media_busy("list")

        def done(ok: bool, result: Any) -> None:
            if not self._media_request_current(request_id, device_id, "stills"):
                return
            self._set_media_busy("")
            if ok and isinstance(result, dict):
                names = [str(name) for name in (result.get("files") or [])]
                self._album_items = [{"file": name} for name in names]
                local_files = self._local_album_paths()
                self._replace_media_items(
                    [self._normalize_still_item(name, local_files) for name in names],
                    self._media_selected_id,
                )
                if not names:
                    self._set_media_status("No still photos found on this telescope.")
                elif not quiet:
                    self._toast(f"{len(names)} stills on telescope", "success")
                return
            self._replace_media_items([])
            self._set_media_status(str(result) if result else "Could not reach the telescope album. Connect it, then tap Refresh.")
            if not quiet:
                self._toast("Album list failed", "error", str(result))

        worker.send("album_list", {"args": [80, camera]}, done)

    @Slot(str, str)
    def downloadMedia(self, device_id: str, item_id: str = "") -> None:
        chosen = str(item_id or self._media_selected_id or "").strip()
        if self._media_source == "local":
            self._select_media_id(chosen)
            self._emit_media()
            return
        if self._media_device_id and self._media_device_id != device_id:
            self._toast("Switch back to the telescope that listed this file before downloading", "warning")
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._toast("Can't download while the telescope is capturing", "warning")
            return
        if self._media_source == "stills":
            self.downloadAlbumPhoto(device_id, chosen)
            return
        item = next((entry for entry in self._media_items if entry.get("id") == chosen), None)
        remote = str((item or {}).get("file_path") or chosen)
        worker = self._workers.get(device_id)
        if not worker or not remote:
            self._toast("Nothing to download", "warning")
            return
        dest = str(self._album_dir())
        request_id = self._media_request_id
        source = self._media_source
        self._set_media_busy("download")

        def done(ok: bool, result: Any) -> None:
            if not self._media_request_current(request_id, device_id, source):
                return
            self._set_media_busy("")
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
                        entry["thumbnail_url"] = local_url
                        entry["image_url"] = local_url
                    elif entry.get("file_name") in local_files:
                        local = local_files[str(entry.get("file_name"))]
                        entry = dict(entry)
                        entry["local_path"] = str(local)
                        entry["downloaded"] = True
                    updated.append(entry)
                self._media_items = updated
                self._select_media_id(chosen)
                self._toast("Session downloaded", "success", Path(self._album_path).name)
                self._emit_media(items=True)
                return
            self._toast("Session download failed", "error", str(result))

        worker.send("astro_session_download", {"args": [remote, dest]}, done)

    @Slot(str, str)
    def downloadAlbumPhoto(self, device_id: str, name: str = "") -> None:
        worker = self._workers.get(device_id)
        if not worker:
            return
        if self._session_is_capturing(device_id):
            self._media_locked = True
            self._toast("Can't download while the telescope is capturing", "warning")
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
            self._set_media_busy("")
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
                        if not entry.get("thumbnail_url"):
                            entry["thumbnail_url"] = self._media_file_url(self._album_path)
                            entry["image_url"] = self._media_file_url(self._album_path)
                        found = True
                    updated.append(entry)
                if not found:
                    updated.insert(0, self._normalize_still_item(chosen, local_files))
                self._media_items = updated
                self._select_media_id(chosen)
                self._toast("Photo downloaded", "success", chosen)
                self._emit_media(items=True)
                return
            self._toast("Album download failed", "error", str(result))

        worker.send("album_download", {"args": [name, dest, camera]}, done)

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

    @Slot(str)
    def saveDevice(self, payload: str) -> None:
        try:
            values = json.loads(payload)
            current = self._device_by_id(values["id"])
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
            updated = replace(
                current,
                name=values["name"].strip(),
                model=DeviceModel(values["model"]),
                ip_address=values["ip_address"].strip(),
                camera=Camera(values.get("camera", current.camera)),
                color=values.get("color", current.color),
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
                observing_day_cutoff_hour=self._cutoff_hour(),
                hardware=hardware,
            )
            if not self._commit_device(current, updated):
                return
            for session in self.store.upcoming(updated.id):
                self._save_session(replace(session, planned_duration_seconds=DurationEngine.calculate(session, updated.hardware)))
            self._sequence_colliding_mosaics()
            self._notify_devices()
            self.durationSuggestionChanged.emit()
            self.clockChanged.emit()
            self.appSettingsChanged.emit()
            self._toast("Device saved", "success")
        except Exception as exc:
            self._toast(f"Could not save device: {exc}", "error")

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
    def lookupLocation(self, query: str) -> None:
        text = query.strip()
        if not text:
            self._toast("Enter a city or timezone to search", "warning")
            return

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

    def _fields_from_payload(self, values: dict[str, Any], existing_mosaic: Mosaic | None = None) -> tuple[Target, CameraSettings, Workflow, Mosaic]:
        target_kind = TargetKind(values.get("target_kind", "equatorial"))
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
                exposure_seconds=float(values.get("exposure", 15)),
                gain=int(values.get("gain", 80)),
                frame_count=int(values.get("frame_count", 120)),
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
        target, camera, workflow, mosaic = self._fields_from_payload(
            values, existing.mosaic if existing else None
        )
        resetting = existing is not None and existing.status != SessionStatus.PLANNED
        device = self._device_by_id(values["device_id"])
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
                self.store.templates.save(SessionTemplate(
                    name=session.name,
                    target=session.target,
                    camera=session.camera,
                    workflow=session.workflow,
                    mosaic=session.mosaic,
                ))
                self.templatesChanged.emit()
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
            self.store.templates.save(SessionTemplate(
                name=anchor.name,
                target=anchor.target,
                camera=anchor.camera,
                workflow=anchor.workflow,
                mosaic=anchor.mosaic,
            ))
            self.templatesChanged.emit()
        self._toast("Session saved", "success")

    def _save_one_template(self, values: dict[str, Any]) -> SessionTemplate:
        existing = self.store.templates.get(values.get("id", "")) if values.get("id") else None
        target, camera, workflow, mosaic = self._fields_from_payload(
            values, existing.mosaic if existing else None
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
            panes = values.get("members")
            if isinstance(panes, list) and panes:
                shared = {key: value for key, value in values.items() if key != "members"}
                for pane in panes:
                    merged = {**shared, **pane}
                    self._save_one_template(merged)
            else:
                saved = self._save_one_template(values)
                group_id = saved.mosaic.group_id
                if group_id:
                    for item in self.store.templates.all():
                        if item.id != saved.id and item.mosaic.group_id == group_id:
                            self.store.templates.save(replace(item, camera=saved.camera, workflow=saved.workflow))
            self.templatesChanged.emit()
            self._toast("Template saved", "success")
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
    def deleteHistoryRecord(self, record_id: str) -> None:
        self.deleteHistoryRecords([record_id])

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
            return
        if session.status == SessionStatus.RUNNING:
            self._toast("This session is already running", "warning")
            return
        device = self._device_by_id(session.device_id)
        worker = self._workers.get(session.device_id)
        if not device or not worker:
            return
        if not device.location_configured:
            self._toast("Choose an observing location before running a session", "warning")
            return
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
        if session.device_id in self._active_sessions or worker.busy:
            self._toast("Another session is running on this telescope", "warning", "It will start once that session ends if the scheduler is armed")
            return
        if session.device_id in self._disconnecting_ids:
            self._toast("Wait for the telescope to finish disconnecting", "warning")
            return
        # RUN is an explicit request: start now even when the scheduler is disarmed.
        self._start_session(worker, self.store.sessions.get(session.id))

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
            axis_tz = self._zone_for(self._device_by_id(self._selected_device_id))
            target = parse_in_zone(iso_datetime, axis_tz).replace(second=0, microsecond=0)
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
    def reorderPlanned(self, session_id: str, before_session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session or session.status != SessionStatus.PLANNED:
            return
        moving = [session]
        moving_ids = {session.id}
        before = self.store.sessions.get(before_session_id) if before_session_id else None
        if before and (before.device_id != session.device_id or before.status != SessionStatus.PLANNED):
            return
        device = self._device_by_id(session.device_id)
        cutoff = self._cutoff_hour()
        target_night = observing_date(
            before.scheduled_start if before else session.scheduled_start,
            cutoff,
            self._zone_for(device),
        )
        queue = sorted(
            (
                item for item in self.store.sessions.all()
                if item.device_id == session.device_id
                and item.status == SessionStatus.PLANNED
                and item.id not in moving_ids
                and observing_date(item.scheduled_start, cutoff, self._zone_for(device)) == target_night
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
        starts = [parse_in_zone(item.scheduled_start, self._zone_for(device)) for item in queue]
        if not starts:
            starts = [parse_in_zone(item.scheduled_start, self._zone_for(device)) for item in moving]
        cursor = min(starts)
        for item in ordered:
            self.store.sessions.save(replace(item, scheduled_start=store_local_iso(cursor, self._zone_for(device))))
            cursor += timedelta(seconds=max(60, item.planned_duration_seconds))
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

    @Slot(str, str, result=bool)
    @Slot(str, str, str, result=bool)
    def scheduleTemplate(self, template_id: str, scheduled_start: str, device_id: str = "") -> bool:
        template = self.store.templates.get(template_id)
        if not template:
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
        sessions = [
            self.store.clone_template(item, device.id, start)
            for item in templates
        ]
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

    @Slot()
    def importStellarium(self) -> None:
        self._run_async("stellarium", lambda: StellariumClient(self._settings.stellarium_url).current_target())

    @Slot(str)
    def importLegacy(self, raw_path: str) -> None:
        path = self._local_path(raw_path)
        count, failed = self.store.import_old_sessions(path.rglob("*.json"), self._selected_device_id)
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

    @Slot(str, object)
    def _handle_async_result(self, operation: str, result: tuple[bool, Any]) -> None:
        ok, value = result
        if operation == "locationLookup":
            if not ok:
                self._toast(str(value), "warning")
                return
            self.locationLookupReady.emit(value)
            return
        self._set_ui_busy("")
        if not ok:
            self._toast(f"{operation.title()}: {value}", "error")
            return
        if operation == "telescopius":
            for template in value:
                self.store.templates.save(template)
            self.templatesChanged.emit()
            self._toast(f"Imported {len(value)} session templates", "success")
        elif operation == "stellarium":
            self.store.templates.save(SessionTemplate(name=value.name, target=value))
            self.templatesChanged.emit()
            self._toast(f"Imported {value.name}", "success")

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
        if not self._telemetry_capturing(final.device_id):
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
        telemetry = dict(self._device_telemetry.get(final.device_id) or {})
        self._sync_preview_for_capture(final.device_id, telemetry, telemetry)
        self._notify_devices()
        self._sync_media_lock()
        if restore_preview:
            self._restore_held_preview(final.device_id)

    def shutdown(self) -> None:
        if self._shut_down:
            return
        self._shut_down = True
        try:
            self.timer.stop()
        except RuntimeError:
            pass
        self._devices_notify_timer.stop()
        self._retarget_timer.stop()
        self.stopPreview()
        self._enhance_pool.waitForDone(1500)
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
            "capture_target": target or "",
            "capture_shooting_s": 0,
            "capture_stacked_s": 0,
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

    @Slot(str, result=float)
    def nightStartEpochMs(self, day: str) -> float:
        try:
            return self._night_start(day).timestamp() * 1000
        except ValueError:
            return 0.0

    @Slot(str, int, result=str)
    def nightTimelineIso(self, day: str, minutes: int) -> str:
        try:
            start = self._night_start(day)
        except ValueError:
            return ""
        value = start + timedelta(minutes=max(0, min(1435, int(minutes))))
        return store_local_iso(value, self._zone_for())

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

    @staticmethod
    def _stamp_text(value: str | None) -> str:
        if not value:
            return "—"
        text = str(value).replace("T", " ")
        return text[:16] if len(text) >= 16 else text

    @staticmethod
    def _local_path(raw_path: str) -> Path:
        url = QUrl(raw_path)
        return Path(url.toLocalFile() if url.isLocalFile() else raw_path)
