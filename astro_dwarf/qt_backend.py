from __future__ import annotations

import json
import logging
import sys
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from math import ceil
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
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication

from .version import __version__
from .domain import (
    Camera,
    CameraSettings,
    Device,
    DeviceModel,
    HistoryRecord,
    Mosaic,
    Session,
    SessionStatus,
    SessionTemplate,
    Target,
    TargetKind,
    WifiMode,
    Workflow,
    device_from_dict,
    session_from_dict,
    to_dict,
)
from .services import (
    DurationEngine,
    StellariumClient,
    import_telescopius,
    mosaic_group_title,
    observing_date,
    pane_sort_key,
    parse_in_zone,
    stagger_mosaic_sessions,
    store_local_iso,
    zoneinfo_from_name,
)
from .location import match_timezone, resolve_location, timezone_locations
from .runtime import PROCESS_CREATION_FLAGS, kill_pid_tree, prepare_worker_environment, worker_command
from .storage import SessionStore
from .stream_preview import LiveFrames, StreamPlayer, port_is_open, preview_window_is_live, set_live_frames, stream_port
from .telemetry_view import AlertEngine, derive_activity, format_telemetry


class TelescopeProcess(QObject):
    logReceived = Signal(str, str)
    progressReceived = Signal(str, str)
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
                self.progressReceived.emit(message["session_id"], message["step"])
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
        self.logReceived.emit("warning" if exit_code == 0 else "error", f"Worker stopped (code {exit_code})")
        pending, self._callbacks = self._callbacks, {}
        for callback in pending.values():
            callback(False, "Telescope worker stopped")
        self.availabilityChanged.emit()

    def _process_error(self, error) -> None:
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
    "infinity": "autofocus",
}
_ACTIVITY_STOP = {
    "burst_stop": "burst",
    "record_stop": "record",
    "timelapse_stop": "timelapse",
    "stop_polar": "polar",
    "stop_calibrate": "calibrate",
    "stop_autofocus": "autofocus",
}
_ACTIVITY_CLEAR = {"stop_all", "reboot", "power_down", "go_live"}
_CAPTURE_PREVIEW_STEPS = {
    "Start capture",
    "Start wide capture",
    "Start mosaic",
    "Waiting for capture",
    "Waiting for mosaic",
    "Waiting for wide capture",
    "Waiting for stack",
    "Waiting for wide stack",
    "Imaging",
    "Imaging (wide)",
}
_ACTIVITY_TRANSIENT = {"calibrate", "autofocus"}
_ACTION_LABELS = {
    "calibrate": "Calibration started",
    "stop_calibrate": "Calibration stopped",
    "autofocus": "Live autofocus started",
    "infinity": "Infinity focus started",
    "stop_autofocus": "Autofocus stopped",
    "polar": "Polar alignment started",
    "stop_polar": "Polar alignment stopped",
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
    "stop_all": "Stop sent",
    "reboot": "Reboot requested",
    "power_down": "Power down requested",
    "open_camera": "Tele camera opened",
    "open_wide_camera": "Wide camera opened",
}
_ACTION_DETAILS = {
    "calibrate": "Device will plate-solve and report progress",
    "autofocus": "Watch the focus position in VITALS",
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
    "all": {"INFO", "NOTICE", "SUCCESS", "WARNING", "ERROR"},
    "device": {"NOTICE", "SUCCESS", "WARNING", "ERROR"},
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
        return self._counts.get("WARNING", 0)

    def error_count(self) -> int:
        return self._counts.get("ERROR", 0)

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
            if self._visible and self._visible[-1] is last:
                row = len(self._visible) - 1
                self.dataChanged.emit(self.index(row), self.index(row), [self.TimeRole, self.CountRole])
            return
        entry.setdefault("count", 1)
        self._all.append(entry)
        level = entry["level"]
        if level in self._counts:
            self._counts[level] += 1
            self.countsChanged.emit()
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
        self.endResetModel()
        self.countsChanged.emit()

    def set_filter(self, name: str) -> None:
        name = name if name in _LOG_FILTERS else "all"
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
    templatesChanged = Signal()
    historyChanged = Signal()
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
    _openTeleStream = Signal(str)
    _openWideStream = Signal(str)
    _closePreviewStreams = Signal()
    _previewReady = Signal(int, str, str)

    def __init__(self, data_root: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.store = SessionStore(data_root)
        self._devices = self.store.devices.all()
        if not self._devices:
            self._devices = [self.store.seed_device()]
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
        self._disconnecting_ids: set[str] = set()
        self._pending_actions: dict[str, str] = {}
        self._device_activity: dict[str, str] = {}
        self._device_telemetry: dict[str, dict[str, Any]] = {}
        self._session_capture_base: dict[str, int] = {}
        self._session_capture_peak: dict[str, int] = {}
        self._telemetry_updated: dict[str, float] = {}
        self._alerts = AlertEngine()
        self._last_toast: tuple[str, str, float] = ("", "", 0.0)
        self._device_lights: dict[str, bool] = {}
        self._telemetry_tick = 0
        self._joystick_inflight: set[str] = set()
        self._joystick_pending: dict[str, tuple[float, float]] = {}
        self._ui_busy = ""
        self._asyncResult.connect(self._handle_async_result)
        for device in self._devices:
            self._create_worker(device)
        recovered = self.store.recover_running()
        if recovered:
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
        self._closePreviewStreams.connect(self._tele_player.closeStream, Qt.QueuedConnection)
        self._closePreviewStreams.connect(self._wide_player.closeStream, Qt.QueuedConnection)
        self._previewReady.connect(self._open_ready_stream)
        self._preview_thread.start()
        self._window_frame_hook = None
        self._pending_window_frame = None

    def _create_worker(self, device: Device) -> TelescopeProcess:
        old = self._workers.pop(device.id, None)
        if old:
            old.shutdown()
        worker = TelescopeProcess(device, self)
        worker.logReceived.connect(lambda level, message, did=device.id: self.add_log(level, message, did))
        worker.telemetryReceived.connect(lambda data, did=device.id: self._on_telemetry(did, data))
        worker.progressReceived.connect(self._session_progress)
        worker.availabilityChanged.connect(self._worker_status_changed)
        self._workers[device.id] = worker
        worker.start()
        return worker

    def _worker_status_changed(self) -> None:
        selected_offline = False
        for device_id, worker in self._workers.items():
            if worker.connected:
                continue
            if device_id == self._selected_device_id:
                selected_offline = True
            self._pending_actions.pop(device_id, None)
            self._device_activity.pop(device_id, None)
            self._device_telemetry.pop(device_id, None)
            self._telemetry_updated.pop(device_id, None)
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

    def _notify_devices(self) -> None:
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()
        self.statusChanged.emit()

    def _on_telemetry(self, device_id: str, data: dict[str, Any]) -> None:
        """Merge a telemetry delta from the worker and raise transition alerts."""
        if not isinstance(data, dict) or not data:
            return
        previous = dict(self._device_telemetry.get(device_id, {}))
        current = dict(previous)
        current.update(data)
        self._device_telemetry[device_id] = current
        self._telemetry_updated[device_id] = time.time()
        if "lights_on" in data:
            self._device_lights[device_id] = bool(data["lights_on"])
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
        if data.get("power_off"):
            self._drop_device_link(device_id)
            return
        self._track_session_capture(device_id, current)
        self._maybe_resume_held_preview(device_id)
        self._notify_devices()

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
            if ok and self._device_activity.get(device_id) == expected:
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
        elif current:
            self._pending_actions.pop(device_id, None)
        else:
            return
        self._notify_devices()

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

    @Property("QVariantList", notify=devicesChanged)
    def devices(self) -> list[dict[str, Any]]:
        result = []
        now = time.time()
        for device in self._devices:
            worker = self._workers.get(device.id)
            data = to_dict(device)
            connecting = device.id in self._connecting_ids
            disconnecting = device.id in self._disconnecting_ids
            if connecting:
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
            raw_telemetry = self._device_telemetry.get(device.id, {})
            if not connected:
                lights_on = False
            elif "lights_on" in raw_telemetry:
                lights_on = bool(raw_telemetry["lights_on"])
            else:
                lights_on = self._device_lights.get(device.id, False)
            data.update({
                "connected": connected,
                "busy": bool(worker and worker.busy),
                "connecting": connecting,
                "disconnecting": disconnecting,
                "pending_action": self._pending_actions.get(device.id, ""),
                "activity": activity,
                "activity_detail": telemetry["activity_detail"],
                "activity_from_device": bool(telemetry["activity"]),
                "status": status,
                "lights_on": lights_on,
                "telemetry": telemetry,
            })
            result.append(data)
        return result

    @Property(str, notify=selectedDeviceChanged)
    def selectedDeviceId(self) -> str:
        return self._selected_device_id

    @Property("QVariantMap", notify=selectedDeviceChanged)
    def selectedDevice(self) -> dict[str, Any]:
        return next((item for item in self.devices if item["id"] == self._selected_device_id), self.devices[0])

    def _session_dict(self, session: Session) -> dict[str, Any]:
        device = next((item for item in self._devices if item.id == session.device_id), None)
        data = to_dict(session)
        start = parse_in_zone(session.scheduled_start, self._zone_for(device))
        finish = start + timedelta(seconds=max(0, session.planned_duration_seconds))
        data["device_name"] = device.name if device else "Unknown"
        data["device_color"] = device.color if device else "#4DE8FF"
        data["target_name"] = session.target.name
        data["scheduled_start"] = store_local_iso(start, start.tzinfo or self._zone_for(device))
        data["start_date"] = start.date().isoformat()
        data["start_time"] = start.strftime("%H:%M")
        data["end_time"] = store_local_iso(finish, start.tzinfo or self._zone_for(device))
        data["start_epoch_ms"] = int(start.timestamp() * 1000)
        data["duration_text"] = self._duration_text(session.planned_duration_seconds)
        data["summary"] = f"{session.camera.frame_count} × {session.camera.exposure_seconds:g}s"
        data["display_title"] = mosaic_group_title(session.target.name, session.mosaic.group_id or "")
        data["subtitle"] = session.name if session.name != session.target.name else data["summary"]
        data["observing_date"] = observing_date(
            session.scheduled_start,
            device.observing_day_cutoff_hour if device else 12,
            self._zone_for(device),
        )
        data["pane_index"] = pane_sort_key(session.name)[0]
        data["pane_name"] = session.name
        data["pane_position"] = session.mosaic.position_text
        return data

    @Property("QVariantList", notify=sessionsChanged)
    def sessions(self) -> list[dict[str, Any]]:
        return [
            self._session_dict(session)
            for session in sorted(
                self.store.sessions.all(),
                key=lambda item: (item.scheduled_start, pane_sort_key(item.name), item.name),
            )
        ]

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
        return data

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
            result.append(data)
        return result

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

    @Property("QVariantMap", notify=sessionsChanged)
    def currentSession(self) -> dict[str, Any]:
        session_id = self._active_sessions.get(self._selected_device_id)
        if not session_id:
            return {}
        return next((item for item in self.sessions if item["id"] == session_id), {})

    @Property(str, notify=clockChanged)
    def clockText(self) -> str:
        return self._clock_text

    @Property("QVariantMap", notify=clockChanged)
    def localNow(self) -> dict[str, Any]:
        device = self._device_by_id(self._selected_device_id)
        tz = self._zone_for(device)
        now = datetime.now(tz)
        cutoff = device.observing_day_cutoff_hour if device else 12
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

    @Property(float, notify=sessionProgressChanged)
    def sessionProgress(self) -> float:
        session = self.currentSession
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
        if not self._scheduler_enabled or self._any_device_connected():
            return
        self._scheduler_enabled = False
        self.schedulerEnabledChanged.emit()
        self.add_log("warning", "Scheduler disarmed: no telescope is connected")
        self._toast("Scheduler disarmed", "warning", "Connect a telescope and re-arm it to resume the queue")

    @Property("QVariantList", notify=sessionsChanged)
    def upcomingSessions(self) -> list[dict[str, Any]]:
        return [
            item for item in self.sessions
            if item["status"] == SessionStatus.PLANNED and item["device_id"] == self._selected_device_id
        ][:8]

    @Property(str, notify=selectedDeviceChanged)
    def videoUrl(self) -> str:
        device = next(item for item in self._devices if item.id == self._selected_device_id)
        return self._stream_url(device, device.camera)

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

    def _stream_url(self, device: Device, camera: Camera) -> str:
        if device.model in (DeviceModel.DWARF_3, DeviceModel.DWARF_MINI):
            return f"rtsp://{device.ip_address}/{'ch1' if camera == Camera.WIDE else 'ch0'}/stream0"
        return f"http://{device.ip_address}:8092/{'secondstream' if camera == Camera.WIDE else 'mainstream'}"

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
        self._last_preview_ui.clear()
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
        self.add_log("info", f"Opening {tele_url} and {wide_url} in the background")
        self._set_preview_status(status or ("Waiting for stream " + tele_url))
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
        device = self._device_by_id(self._selected_device_id)
        primary_wide = device.camera == Camera.WIDE
        if primary_wide:
            self._openWideStream.emit(wide_url)
            QTimer.singleShot(400, lambda: self._open_secondary_stream(token, "tele", tele_url))
        else:
            self._openTeleStream.emit(tele_url)
            QTimer.singleShot(400, lambda: self._open_secondary_stream(token, "wide", wide_url))

    def _open_secondary_stream(self, token: int, camera: str, url: str) -> None:
        if token != self._preview_token or not self._preview_active:
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
        if self._preview_active or self._preview_playing:
            self._closePreviewStreams.emit()
        self._preview_active = False
        self._preview_playing = False
        self._preview_tele_playing = False
        self._preview_wide_playing = False
        self.live_images.clear()
        self._last_preview_ui.clear()
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
        if device_id != self._selected_device_id:
            return
        if not (self._preview_active or self._preview_playing or self._preview_hold_device_id == device_id):
            return
        self._preview_hold_device_id = device_id
        self._preview_hold_target = target_name or "this target"
        self.previewHoldChanged.emit()
        self._stop_preview_streams()
        self._set_preview_status(self.previewHoldMessage)
        self.add_log(
            "info",
            "Live view paused while the session prepares; it will return when capture starts",
            device_id,
        )

    def _session_is_capturing(self, device_id: str) -> bool:
        telemetry = self._device_telemetry.get(device_id) or {}
        if telemetry.get("capture_active") or telemetry.get("capture_state") == "running":
            return True
        session_id = self._active_sessions.get(device_id)
        session = self.store.sessions.get(session_id) if session_id else None
        return bool(session and session.current_step in _CAPTURE_PREVIEW_STEPS)

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
        if device_id != self._selected_device_id:
            return
        worker = self._workers.get(device_id)
        device = next((item for item in self._devices if item.id == device_id), None)
        if not worker or not worker.connected or device is None:
            return
        self._clear_preview_hold()
        self.add_log("info", "Capture started; reconnecting live view", device_id)
        token = self._arm_preview_ui("Capture started — reconnecting live view…")
        tele_url = self._stream_url(device, Camera.TELE)
        wide_url = self._stream_url(device, Camera.WIDE)
        host = urlparse(tele_url).hostname or device.ip_address
        self._begin_stream_wait(
            token,
            tele_url,
            wide_url,
            host,
            stream_port(tele_url),
            timeout=20,
            status="Capture started — reconnecting live view…",
        )

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

    def _on_tele_frame(self, image) -> None:
        self._on_camera_frame("tele", image)

    def _on_wide_frame(self, image) -> None:
        self._on_camera_frame("wide", image)

    def _on_camera_frame(self, camera: str, image) -> None:
        if not self._preview_active:
            return
        self.live_images.update(camera, image)
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
        if not self._preview_active:
            return
        device = self._device_by_id(self._selected_device_id)
        primary = "wide" if device.camera == Camera.WIDE else "tele"
        if camera == primary or not self._preview_playing:
            self._set_preview_status(message)

    @Slot(str, str)
    def uiLog(self, level: str, message: str) -> None:
        self.add_log(level, message)

    @Slot(str)
    def selectDevice(self, device_id: str) -> None:
        if any(device.id == device_id for device in self._devices):
            self._selected_device_id = device_id
            self.selectedDeviceChanged.emit()
            self.sessionsChanged.emit()
            self.clockChanged.emit()
            self.previewHoldChanged.emit()

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
        self._connecting_ids.discard(device_id)
        if ok and isinstance(result, dict) and result.get("ip_address"):
            self._persist_discovered_ip(device_id, str(result["ip_address"]))
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
        self.add_log("warning", f"Stopping session · {name} ({reason})", device_id)
        return True

    @Slot(str)
    def disconnectDevice(self, device_id: str) -> None:
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
            self._device_lights.pop(device_id, None)
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
            self.commandFeedback.emit(device_id, operation, bool(ok))
            if ok:
                self.add_log("success", f"{label} acknowledged", device_id)
                self._toast(label, "success", _ACTION_DETAILS.get(operation, ""))
            else:
                self.add_log("error", f"{label} failed: {result}", device_id)
                self._toast(f"{label} failed", "error", str(result))

        worker.send(operation, callback=self._with_pending(device_id, operation, done))
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
        worker = self._workers.get(device_id)
        if not worker:
            return
        self._abort_active_session(device_id, "STOP ALL")
        if not worker.connected:
            if device_id == self._selected_device_id:
                self.stopPreview()
            self.add_log("warning", "Stop skipped; telescope is not connected", device_id)
            return
        self._begin_activity(device_id, "stop_all")

        def done(ok: bool, result: Any) -> None:
            self._complete_activity(device_id, "stop_all", ok)
            self.add_log(
                "warning" if ok else "error", "Stop commands sent" if ok else str(result), device_id
            )

        worker.send("stop_all", callback=self._with_pending(device_id, "stop_all", done))

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
            if abs(latitude) < 1e-9 and abs(longitude) < 1e-9 and timezone_name not in {"UTC", "Etc/UTC"}:
                raise ValueError("Choose a timezone from the list, or press Enter to look up a city")
            model = current.model if current else DeviceModel.DWARF_3
            if values.get("model"):
                model = DeviceModel(values["model"])
            device = Device(
                name=f"Dwarf {len(self._devices) + 1}",
                color=colors[len(self._devices) % len(colors)],
                model=model,
                timezone_name=timezone_name,
                latitude=latitude,
                longitude=longitude,
                location_configured=True,
            )
            self.store.devices.save(device)
            self._devices.append(device)
            self._create_worker(device)
            self._selected_device_id = device.id
            self.devicesChanged.emit()
            self.selectedDeviceChanged.emit()
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
        if worker:
            worker.shutdown()
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
        self._device_activity.pop(device_id, None)
        self._device_telemetry.pop(device_id, None)
        self._telemetry_updated.pop(device_id, None)
        self._device_lights.pop(device_id, None)
        if self._selected_device_id == device_id:
            self._selected_device_id = self._devices[0].id
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()
        self.sessionsChanged.emit()
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
        self.sessionsChanged.emit()

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
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()

    @Slot(str, str, str)
    def setCameraParam(self, device_id: str, name: str, value: str) -> None:
        device = self._device_by_id(device_id)
        worker = self._workers.get(device_id)
        if not worker or not worker.connected:
            return
        camera = device.camera.value if hasattr(device.camera, "value") else str(device.camera)
        model_id = {DeviceModel.DWARF_II: "2", DeviceModel.DWARF_3: "3", DeviceModel.DWARF_MINI: "5"}.get(device.model, "3")
        if name == "exposure":
            operation, args = "set_exposure", [value, model_id, camera]
        elif name == "gain":
            operation, args = "set_gain", [int(value), camera]
        elif name == "ir":
            if camera == Camera.WIDE.value:
                return
            operation, args = "set_ir", [value]
        else:
            return
        worker.send(operation, {"args": args}, lambda ok, result: self._toast(
            f"{name.title()} set" if ok else str(result), "success" if ok else "error"
        ))

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
                location_configured=True,
                stellarium_url=values.get("stellarium_url", current.stellarium_url),
                wifi_ssid=values.get("wifi_ssid", current.wifi_ssid),
                wifi_password=values.get("wifi_password", current.wifi_password),
                wifi_mode=WifiMode(str(values.get("wifi_mode", current.wifi_mode) or WifiMode.AUTO).lower()),
                ble_password=str(values.get("ble_password", current.ble_password) or "DWARF_12345678"),
                ble_enabled=bool(values.get("ble_enabled", current.ble_enabled)),
                observing_day_cutoff_hour=int(values.get("observing_day_cutoff_hour", current.observing_day_cutoff_hour)),
                hardware=hardware,
            )
            self.store.devices.save(updated)
            self._devices = [updated if item.id == updated.id else item for item in self._devices]
            self._create_worker(updated)
            for session in self.store.upcoming(updated.id):
                self._save_session(replace(session, planned_duration_seconds=DurationEngine.calculate(session, updated.hardware)))
            self._sequence_colliding_mosaics()
            self.devicesChanged.emit()
            self.selectedDeviceChanged.emit()
            self.clockChanged.emit()
            self._toast("Device saved", "success")
        except Exception as exc:
            self._toast(f"Could not save device: {exc}", "error")

    @Slot(str)
    def saveObservingLocation(self, payload: str) -> None:
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
            if abs(latitude) < 1e-9 and abs(longitude) < 1e-9 and timezone_name not in {"UTC", "Etc/UTC"}:
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
                location_configured=True,
            )
            self.store.devices.save(updated)
            self._devices = [updated if item.id == updated.id else item for item in self._devices]
            self._create_worker(updated)
            self.devicesChanged.emit()
            self.selectedDeviceChanged.emit()
            self.clockChanged.emit()
            self._toast("Observing location saved", "success")
        except Exception as exc:
            self._toast(f"Could not save location: {exc}", "error")

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
            if updated:
                self.sessionsChanged.emit()
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
            siblings: list[Session] = []
            if existing:
                family = self._mosaic_siblings(existing)
                if existing.device_id != device.id and any(item.status == SessionStatus.RUNNING for item in family):
                    raise ValueError("Stop the running mosaic before moving it to another telescope")
                old_tz = self._zone_for_id(existing.device_id)
                new_tz = self._zone_for(device)
                delta = parse_in_zone(session.scheduled_start, new_tz) - parse_in_zone(existing.scheduled_start, old_tz)
                if existing.device_id != device.id or delta:
                    siblings = [item for item in self._session_group(existing) if item.id != existing.id]
            self._save_session(session, notify=not siblings)
            if siblings and existing:
                old_tz = self._zone_for_id(existing.device_id)
                new_tz = self._zone_for(device)
                delta = parse_in_zone(session.scheduled_start, new_tz) - parse_in_zone(existing.scheduled_start, old_tz)
                for sibling in siblings:
                    sib_start = parse_in_zone(sibling.scheduled_start, old_tz) + delta
                    self._save_session(
                        replace(sibling, device_id=device.id, scheduled_start=store_local_iso(sib_start, new_tz)),
                        notify=False,
                    )
            if self._sequence_mosaic_group(session, notify=False):
                self.sessionsChanged.emit()
            elif siblings:
                self.sessionsChanged.emit()
            if siblings:
                self._warn_schedule_overlap(
                    {session.id, *(item.id for item in siblings)},
                    device.id,
                )
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
        saved: list[Session] = []
        for pane in panes:
            if not isinstance(pane, dict):
                continue
            existing = self.store.sessions.get(pane.get("id", "")) if pane.get("id") else None
            merged = {**shared, **pane, "device_id": device.id}
            if existing:
                start = parse_in_zone(existing.scheduled_start, old_tz) + delta
                merged["scheduled_start"] = store_local_iso(start, new_tz)
            session = self._session_from_payload(merged, existing)
            saved.append(self._save_session(session, notify=False))
        if not saved:
            raise ValueError("No panes to save")
        anchor = next((item for item in saved if item.id == anchor_id), saved[0])
        self._sequence_mosaic_group(anchor, notify=False)
        self.sessionsChanged.emit()
        self._warn_schedule_overlap({item.id for item in saved}, device.id)
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
            self.sessionsChanged.emit()
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
            self.sessionsChanged.emit()
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
        scheduled_start = source.scheduled_start
        if source.mosaic.group_id:
            tz = self._zone_for_id(source.device_id)
            family = [
                item for item in self._mosaic_siblings(source)
                if item.status == SessionStatus.PLANNED
            ]
            if family:
                last_end = max(self._session_window(item, tz)[1] for item in family)
                scheduled_start = store_local_iso(last_end, tz)
        self._save_session(replace(
            source,
            id=uuid4().hex,
            name=f"{source.name} copy",
            scheduled_start=scheduled_start,
            status=SessionStatus.PLANNED,
            actual_started_at=None,
            actual_ended_at=None,
        ))

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
        self._save_session(replace(
            session,
            scheduled_start=self._store_session_time(self._now_local(device), device),
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
            self._device_by_id(session.device_id).observing_day_cutoff_hour,
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
        for item in members:
            tz = self._zone_for_id(item.device_id)
            start = parse_in_zone(item.scheduled_start, tz) + timedelta(days=delta.days)
            self.store.sessions.save(replace(item, scheduled_start=store_local_iso(start, tz)))
        self.sessionsChanged.emit()

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
        changed_ids: set[str] = set()
        for session in moving:
            if session.device_id == device.id:
                continue
            self._save_session(self._reassign_session(session, device), notify=False)
            changed_ids.add(session.id)
        if changed_ids:
            seen_groups: set[tuple[str, str]] = set()
            for session_id in changed_ids:
                item = self.store.sessions.get(session_id)
                if not item or not item.mosaic.group_id:
                    continue
                key = (item.mosaic.group_id, item.device_id)
                if key in seen_groups:
                    continue
                seen_groups.add(key)
                self._sequence_mosaic_group(item, notify=False)
            self.sessionsChanged.emit()
            self._warn_schedule_overlap(changed_ids, device.id)
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

    def _session_occupied_minutes(self, session: Session) -> int:
        return max(1, int(ceil(max(0, session.planned_duration_seconds) / 60.0)))

    def _session_window(self, session: Session, tz) -> tuple[datetime, datetime]:
        start = parse_in_zone(session.scheduled_start, tz).replace(second=0, microsecond=0)
        return start, start + timedelta(minutes=self._session_occupied_minutes(session))

    def _mosaic_members_overlap(self, members: list[Session], tz) -> bool:
        windows = [self._session_window(item, tz) for item in members]
        for index, (left_start, left_end) in enumerate(windows):
            for right_start, right_end in windows[index + 1:]:
                if left_start < right_end and right_start < left_end:
                    return True
        return False

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
            self.sessionsChanged.emit()
        return True

    def _warn_schedule_overlap(self, moved_ids: set[str], device_id: str) -> None:
        tz = self._zone_for_id(device_id)
        planned = [
            item for item in self.store.sessions.all()
            if item.device_id == device_id and item.status == SessionStatus.PLANNED
        ]
        moved = [item for item in planned if item.id in moved_ids]
        others = [item for item in planned if item.id not in moved_ids]
        for left in moved:
            left_start, left_end = self._session_window(left, tz)
            for right in others:
                right_start, right_end = self._session_window(right, tz)
                if left_start < right_end and right_start < left_end:
                    self._toast("Schedule updated; this session overlaps another planned session", "warning")
                    return

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
        members = self._session_group(session)
        moved_ids = {item.id for item in members}
        for item in members:
            item_tz = self._zone_for_id(item.device_id)
            start = parse_in_zone(item.scheduled_start, item_tz) + delta
            self.store.sessions.save(replace(item, scheduled_start=store_local_iso(start, item_tz)))
        self._sequence_mosaic_group(session, notify=False)
        self.sessionsChanged.emit()
        self._warn_schedule_overlap(moved_ids, session.device_id)

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
        cutoff = device.observing_day_cutoff_hour if device else 12
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
        self.sessionsChanged.emit()

    @Slot(str)
    def scheduleTemplate(self, template_id: str) -> None:
        template = self.store.templates.get(template_id)
        if not template:
            return
        group_id = template.mosaic.group_id
        templates = (
            [item for item in self.store.templates.all() if item.mosaic.group_id == group_id]
            if group_id else [template]
        )
        device = self._device_by_id(self._selected_device_id)
        start = self._now_local(device).replace(second=0, microsecond=0)
        sessions = [
            self.store.clone_template(item, self._selected_device_id, start)
            for item in templates
        ]
        for session in stagger_mosaic_sessions(sessions, start, device.hardware):
            self.store.sessions.save(session)
        self.sessionsChanged.emit()
        count = len(sessions)
        self._toast(f"Scheduled {count} pane{'s' if count != 1 else ''}", "success")

    @Slot(str)
    def importTelescopius(self, raw_path: str) -> None:
        path = self._local_path(raw_path)
        self._run_async("telescopius", lambda: import_telescopius(path))

    @Slot()
    def importStellarium(self) -> None:
        device = self._device_by_id(self._selected_device_id)
        self._run_async("stellarium", lambda: StellariumClient(device.stellarium_url).current_target())

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
            if device.id in self._disconnecting_ids or device.id in self._connecting_ids:
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
            self._start_session(worker, session)

    def _start_session(self, worker: TelescopeProcess, session: Session) -> None:
        started = datetime.now(timezone.utc)
        session = self.store.transition(
            session.id,
            SessionStatus.RUNNING,
            actual_started_at=started.isoformat(),
            current_step="Starting worker",
        )
        self._active_sessions[session.device_id] = session.id
        self._session_capture_base[session.id] = self._telemetry_frame_count(session.device_id)
        self._session_capture_peak[session.id] = 0
        self._set_activity(session.device_id, "")
        self._hold_preview_for_session(session.device_id, session.target.name)
        self.sessionsChanged.emit()
        self.add_log("notice", f"Session started · {session.target.name}", session.device_id)
        self._toast(f"Session started · {session.target.name}", "info", f"{session.camera.frame_count} × {session.camera.exposure_seconds:g}s")
        worker.run_session(session, lambda ok, result: self._session_finished(session.id, ok, result))

    @Slot(str, str)
    def _session_progress(self, session_id: str, step: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session:
            return
        self.store.sessions.save(replace(session, current_step=step))
        self.sessionsChanged.emit()
        if self._preview_hold_device_id == session.device_id:
            self._refresh_preview_hold()
            self._maybe_resume_held_preview(session.device_id)

    def _session_finished(self, session_id: str, ok: bool, result: Any) -> None:
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
        stopped = session_id in self._stop_requested
        self._stop_requested.discard(session_id)
        if not session:
            self.sessionsChanged.emit()
            if restore_preview:
                self._restore_held_preview(device_id)
            return
        if session.status != SessionStatus.RUNNING:
            # Already finalised (for example the worker died and reported it first).
            self.sessionsChanged.emit()
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
        self.store.history.save(HistoryRecord(
            session_id=final.id,
            device_id=final.device_id,
            target_name=final.target.name,
            scheduled_start=final.scheduled_start,
            actual_started_at=final.actual_started_at,
            actual_ended_at=final.actual_ended_at,
            planned_duration_seconds=final.planned_duration_seconds,
            actual_duration_seconds=(ended - started).total_seconds(),
            frame_count=final.camera.frame_count,
            captured_frame_count=captured,
            outcome=outcome,
            summary=f"{captured}/{final.camera.frame_count} frames · {final.camera.exposure_seconds:g}s",
            notes=final.notes,
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
        self.sessionsChanged.emit()
        self.historyChanged.emit()
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
        self.stopPreview()
        self._tele_player.abort()
        self._wide_player.abort()
        set_live_frames(None)
        for worker in list(self._workers.values()):
            worker.shutdown(wait=False)
        if self._preview_thread.isRunning():
            self._preview_thread.quit()

    def _sequence_colliding_mosaics(self) -> None:
        seen: set[tuple[str, str]] = set()
        changed = False
        for session in self.store.sessions.all():
            group_id = session.mosaic.group_id
            if not group_id or session.status != SessionStatus.PLANNED:
                continue
            key = (group_id, session.device_id)
            if key in seen:
                continue
            seen.add(key)
            if self._sequence_mosaic_group(session, notify=False):
                changed = True
        if changed:
            self.sessionsChanged.emit()

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

    def _night_start(self, day: str, device: Device | None = None) -> datetime:
        item = device or self._device_by_id(self._selected_device_id)
        tz = self._zone_for(item)
        cutoff = item.observing_day_cutoff_hour if item else 12
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
