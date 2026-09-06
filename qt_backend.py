from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from PySide6.QtCore import (
    Property,
    QProcess,
    QProcessEnvironment,
    QObject,
    QTimer,
    QUrl,
    Signal,
    Slot,
)

from . import __version__
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
    stagger_mosaic_sessions,
)
from .runtime import prepare_worker_environment, worker_command
from .storage import SessionStore


class TelescopeProcess(QObject):
    logReceived = Signal(str, str)
    progressReceived = Signal(str, str)
    availabilityChanged = Signal()

    def __init__(self, device: Device, parent: QObject | None = None):
        super().__init__(parent)
        self.device = device
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
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

    def shutdown(self) -> None:
        if self.running:
            self.process.closeWriteChannel()
            self.process.terminate()
            QTimer.singleShot(1000, lambda: self.process.kill() if self.running else None)

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
            elif event == "progress":
                self.progressReceived.emit(message["session_id"], message["step"])
            elif event == "response":
                callback = self._callbacks.pop(int(message.get("id", 0)), None)
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


class AppBackend(QObject):
    devicesChanged = Signal()
    sessionsChanged = Signal()
    templatesChanged = Signal()
    historyChanged = Signal()
    logsChanged = Signal()
    selectedDeviceChanged = Signal()
    statusChanged = Signal()
    schedulerEnabledChanged = Signal()
    clockChanged = Signal()
    sessionProgressChanged = Signal()
    toast = Signal(str, str)
    _asyncResult = Signal(str, object)

    def __init__(self, data_root: Path, parent: QObject | None = None):
        super().__init__(parent)
        self.store = SessionStore(data_root)
        self._devices = self.store.devices.all()
        if not self._devices:
            self._devices = [self.store.seed_device()]
        self._selected_device_id = self._devices[0].id
        self._logs: list[dict[str, str]] = []
        self._workers: dict[str, TelescopeProcess] = {}
        self._active_sessions: dict[str, str] = {}
        self._scheduler_enabled = False
        self._clock_text = datetime.now().strftime("%H:%M:%S")
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

    def _create_worker(self, device: Device) -> TelescopeProcess:
        old = self._workers.pop(device.id, None)
        if old:
            old.shutdown()
        worker = TelescopeProcess(device, self)
        worker.logReceived.connect(lambda level, message, did=device.id: self.add_log(level, message, did))
        worker.progressReceived.connect(self._session_progress)
        worker.availabilityChanged.connect(self._worker_status_changed)
        self._workers[device.id] = worker
        if not device.demo_mode:
            worker.start()
        return worker

    def _worker_status_changed(self) -> None:
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()
        self.statusChanged.emit()

    def add_log(self, level: str, message: str, device_id: str = "") -> None:
        device = next((d.name for d in self._devices if d.id == device_id), "System")
        self._logs.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "level": level.upper(),
            "device": device,
            "message": message,
        })
        del self._logs[:-500]
        self.logsChanged.emit()

    @Property(str, constant=True)
    def appVersion(self) -> str:
        return __version__

    @Property("QVariantList", notify=devicesChanged)
    def devices(self) -> list[dict[str, Any]]:
        result = []
        for device in self._devices:
            worker = self._workers.get(device.id)
            data = to_dict(device)
            data.update({
                "connected": bool(worker and worker.connected),
                "busy": bool(worker and worker.busy),
                "status": "Demo" if device.demo_mode else "Imaging" if worker and worker.busy else "Connected" if worker and worker.connected else "Offline",
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
        data["device_name"] = device.name if device else "Unknown"
        data["device_color"] = device.color if device else "#4DE8FF"
        data["target_name"] = session.target.name
        data["start_date"] = session.scheduled_start[:10]
        data["start_time"] = session.scheduled_start[11:16]
        data["duration_text"] = self._duration_text(session.planned_duration_seconds)
        data["summary"] = f"{session.camera.frame_count} × {session.camera.exposure_seconds:g}s"
        data["display_title"] = mosaic_group_title(session.target.name, session.mosaic.group_id or "")
        data["subtitle"] = session.name if session.name != session.target.name else data["summary"]
        data["observing_date"] = observing_date(
            session.scheduled_start,
            device.observing_day_cutoff_hour if device else 12,
        )
        data["pane_index"] = pane_sort_key(session.name)[0]
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
        data["id"] = first.id
        data["group_id"] = group_id
        data["is_group"] = grouped
        data["pane_count"] = len(members)
        data["name"] = title
        data["target_name"] = mosaic_group_title(first.target.name, group_id) if grouped else first.target.name
        data["member_ids"] = [item.id for item in sorted(members, key=lambda item: pane_sort_key(item.name))]
        if grouped:
            data["summary"] = f"{len(members)} panes · {first.camera.frame_count} × {first.camera.exposure_seconds:g}s"
        else:
            data["summary"] = f"{first.camera.frame_count} × {first.camera.exposure_seconds:g}s · {first.mosaic.rows}×{first.mosaic.columns}"
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

    @Property("QVariantList", notify=historyChanged)
    def history(self) -> list[dict[str, Any]]:
        device_names = {device.id: device.name for device in self._devices}
        result = []
        for record in sorted(self.store.history.all(), key=lambda item: item.recorded_at, reverse=True):
            data = to_dict(record)
            data["device_name"] = device_names.get(record.device_id, "Unknown")
            data["date"] = record.scheduled_start[:10]
            data["planned_text"] = self._duration_text(record.planned_duration_seconds)
            data["actual_text"] = self._duration_text(record.actual_duration_seconds)
            result.append(data)
        return result

    @Property("QVariantList", notify=logsChanged)
    def logs(self) -> list[dict[str, str]]:
        return list(self._logs)

    @Property("QVariantMap", notify=sessionsChanged)
    def currentSession(self) -> dict[str, Any]:
        session_id = self._active_sessions.get(self._selected_device_id)
        if not session_id:
            return {}
        return next((item for item in self.sessions if item["id"] == session_id), {})

    @Property(str, notify=clockChanged)
    def clockText(self) -> str:
        return self._clock_text

    @Property(float, notify=sessionProgressChanged)
    def sessionProgress(self) -> float:
        session = self.currentSession
        planned = float(session.get("planned_duration_seconds") or 0)
        started = session.get("actual_started_at")
        if not session or not started or planned <= 0:
            return 0.0
        started_at = datetime.fromisoformat(started)
        now = datetime.now(started_at.tzinfo) if started_at.tzinfo else datetime.now()
        return min(1.0, max(0.0, (now - started_at).total_seconds() / planned))

    def _tick(self) -> None:
        clock = datetime.now().strftime("%H:%M:%S")
        if clock != self._clock_text:
            self._clock_text = clock
            self.clockChanged.emit()
        if self._active_sessions:
            self.sessionProgressChanged.emit()
        self._scheduler_tick()

    @Property(bool, notify=schedulerEnabledChanged)
    def schedulerEnabled(self) -> bool:
        return self._scheduler_enabled

    @Slot(bool)
    def setSchedulerEnabled(self, enabled: bool) -> None:
        self._scheduler_enabled = enabled
        self.schedulerEnabledChanged.emit()
        self.add_log("info", "Scheduler started" if enabled else "Scheduler stopped")
        if enabled:
            QTimer.singleShot(0, self._scheduler_tick)

    @Property("QVariantList", notify=sessionsChanged)
    def upcomingSessions(self) -> list[dict[str, Any]]:
        return [
            item for item in self.sessions
            if item["status"] == SessionStatus.PLANNED and item["device_id"] == self._selected_device_id
        ][:8]

    @Property(str, notify=selectedDeviceChanged)
    def videoUrl(self) -> str:
        device = next(item for item in self._devices if item.id == self._selected_device_id)
        if device.model in (DeviceModel.DWARF_3, DeviceModel.DWARF_MINI):
            return f"rtsp://{device.ip_address}/{'ch1' if device.camera == Camera.WIDE else 'ch0'}/stream0"
        return f"http://{device.ip_address}:8092/{'secondstream' if device.camera == Camera.WIDE else 'mainstream'}"

    @Slot(str)
    def startPreview(self, device_id: str) -> None:
        device = self._device_by_id(device_id)
        if device.demo_mode:
            self.add_log("demo", "Would open live camera preview", device_id)
            return
        worker = self._workers.get(device_id)
        if not worker:
            return
        camera_op = "open_wide_camera" if device.camera == Camera.WIDE else "open_camera"
        worker.send("go_live")
        worker.send(camera_op)

    @Slot(str, str)
    def uiLog(self, level: str, message: str) -> None:
        self.add_log(level, message)

    @Slot(str)
    def selectDevice(self, device_id: str) -> None:
        if any(device.id == device_id for device in self._devices):
            self._selected_device_id = device_id
            self.selectedDeviceChanged.emit()
            self.sessionsChanged.emit()

    @Slot(str)
    def connectDevice(self, device_id: str) -> None:
        device = next((item for item in self._devices if item.id == device_id), None)
        if not device:
            return
        if device.demo_mode:
            self.add_log("warning", "Demo mode is enabled; disable it in Settings to connect", device_id)
            self.toast.emit("Demo mode is enabled", "warning")
            return
        worker = self._workers[device_id]
        self.add_log("info", "Connection requested; UI remains available", device_id)
        worker.connect_device(lambda ok, result: self._connection_done(device_id, ok, result))

    def _connection_done(self, device_id: str, ok: bool, result: Any) -> None:
        self.add_log("success" if ok else "error", "Connected" if ok else f"Connection failed: {result}", device_id)
        self.toast.emit("Telescope connected" if ok else f"Connection failed: {result}", "success" if ok else "error")
        self.devicesChanged.emit()
        self.statusChanged.emit()

    @Slot(str)
    def disconnectDevice(self, device_id: str) -> None:
        worker = self._workers.get(device_id)
        if worker:
            worker.disconnect_device(lambda ok, result: self.add_log("info" if ok else "error", "Disconnected" if ok else str(result), device_id))

    @Slot(str, str)
    def deviceAction(self, device_id: str, operation: str) -> None:
        worker = self._workers.get(device_id)
        if not worker:
            return
        if self._device_by_id(device_id).demo_mode:
            self.add_log("demo", f"Would run: {operation.replace('_', ' ')}", device_id)
            return
        worker.send(operation, callback=lambda ok, result: self.toast.emit(
            operation.replace("_", " ").title() if ok else str(result), "success" if ok else "error"
        ))

    @Slot(str, float, float)
    def joystick(self, device_id: str, angle: float, speed: float) -> None:
        worker = self._workers.get(device_id)
        if self._device_by_id(device_id).demo_mode:
            self.add_log("demo", f"Joystick angle={angle:g} speed={speed:g}", device_id)
        elif worker:
            worker.send("joystick", {"args": [angle, speed]})

    @Slot(str, int)
    def manualFocus(self, device_id: str, direction: int) -> None:
        worker = self._workers.get(device_id)
        if self._device_by_id(device_id).demo_mode:
            self.add_log("demo", "Focus near" if direction else "Focus far", device_id)
        elif worker:
            worker.send("manual_focus", {"args": [direction]})

    @Slot(str)
    def stopDevice(self, device_id: str) -> None:
        worker = self._workers.get(device_id)
        if worker:
            worker.stop_all()

    @Slot()
    def addDevice(self) -> None:
        colors = ["#62A0FF", "#E879F9", "#34D399", "#FBBF24", "#FB7185"]
        device = Device(name=f"Dwarf {len(self._devices) + 1}", color=colors[len(self._devices) % len(colors)])
        self.store.devices.save(device)
        self._devices.append(device)
        self._create_worker(device)
        self._selected_device_id = device.id
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()

    @Slot(str)
    def deleteDevice(self, device_id: str) -> None:
        if len(self._devices) <= 1:
            self.toast.emit("Keep at least one telescope profile", "warning")
            return
        worker = self._workers.pop(device_id, None)
        if worker:
            worker.shutdown()
        self.store.devices.delete(device_id)
        self._devices = [item for item in self._devices if item.id != device_id]
        self._active_sessions.pop(device_id, None)
        if self._selected_device_id == device_id:
            self._selected_device_id = self._devices[0].id
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()
        self.sessionsChanged.emit()
        self.toast.emit("Device removed", "success")

    @Slot(str)
    def deleteTemplate(self, template_id: str) -> None:
        template = self.store.templates.get(template_id)
        if not template:
            return
        group_id = template.mosaic.group_id
        if group_id:
            for item in self.store.templates.all():
                if item.mosaic.group_id == group_id:
                    self.store.templates.delete(item.id)
        else:
            self.store.templates.delete(template_id)
        self.templatesChanged.emit()

    @Slot(str)
    def skipSession(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if not session or session.status != SessionStatus.PLANNED:
            self.toast.emit("Only planned sessions can be skipped", "warning")
            return
        self.store.transition(session_id, SessionStatus.SKIPPED, current_step="Skipped")
        self.sessionsChanged.emit()

    @Slot(str, str)
    def setLiveCamera(self, device_id: str, camera: str) -> None:
        current = self._device_by_id(device_id)
        updated = replace(current, camera=Camera(camera))
        self.store.devices.save(updated)
        self._devices = [updated if item.id == updated.id else item for item in self._devices]
        self.devicesChanged.emit()
        self.selectedDeviceChanged.emit()

    @Slot(str, str, str)
    def setCameraParam(self, device_id: str, name: str, value: str) -> None:
        device = self._device_by_id(device_id)
        if device.demo_mode:
            self.add_log("demo", f"Set {name} = {value}", device_id)
            return
        worker = self._workers.get(device_id)
        if not worker:
            return
        camera = device.camera.value if hasattr(device.camera, "value") else str(device.camera)
        model_id = {DeviceModel.DWARF_II: "2", DeviceModel.DWARF_3: "3", DeviceModel.DWARF_MINI: "5"}.get(device.model, "3")
        if name == "exposure":
            operation, args = "set_exposure", [value, model_id, camera]
        elif name == "gain":
            operation, args = "set_gain", [int(value), camera]
        elif name == "ir":
            operation, args = "set_ir", [value]
        else:
            return
        worker.send(operation, {"args": args}, lambda ok, result: self.toast.emit(
            f"{name.title()} set" if ok else str(result), "success" if ok else "error"
        ))

    @Slot(str)
    def saveDevice(self, payload: str) -> None:
        try:
            values = json.loads(payload)
            current = self._device_by_id(values["id"])
            hardware = replace(current.hardware, **{
                key: float(values.get(key, getattr(current.hardware, key)))
                for key in current.hardware.__dataclass_fields__
            })
            updated = replace(
                current,
                name=values["name"].strip(),
                model=DeviceModel(values["model"]),
                ip_address=values["ip_address"].strip(),
                camera=Camera(values.get("camera", current.camera)),
                color=values.get("color", current.color),
                demo_mode=bool(values.get("demo_mode", current.demo_mode)),
                latitude=float(values.get("latitude", current.latitude)),
                longitude=float(values.get("longitude", current.longitude)),
                timezone_name=values.get("timezone_name", current.timezone_name),
                stellarium_url=values.get("stellarium_url", current.stellarium_url),
                wifi_ssid=values.get("wifi_ssid", current.wifi_ssid),
                wifi_password=values.get("wifi_password", current.wifi_password),
                ble_enabled=bool(values.get("ble_enabled", current.ble_enabled)),
                observing_day_cutoff_hour=int(values.get("observing_day_cutoff_hour", current.observing_day_cutoff_hour)),
                hardware=hardware,
            )
            self.store.devices.save(updated)
            self._devices = [updated if item.id == updated.id else item for item in self._devices]
            self._create_worker(updated)
            for session in self.store.upcoming(updated.id):
                self._save_session(replace(session, planned_duration_seconds=DurationEngine.calculate(session, updated.hardware)))
            self.devicesChanged.emit()
            self.selectedDeviceChanged.emit()
            self.toast.emit("Device saved", "success")
        except Exception as exc:
            self.toast.emit(f"Could not save device: {exc}", "error")

    @Slot(str)
    def saveSession(self, payload: str) -> None:
        try:
            values = json.loads(payload)
            existing = self.store.sessions.get(values.get("id", "")) if values.get("id") else None
            if existing and existing.status == SessionStatus.RUNNING:
                raise ValueError("A running session cannot be edited")
            target_kind = TargetKind(values.get("target_kind", "equatorial"))
            session = Session(
                id=existing.id if existing else uuid4().hex,
                name=values.get("name") or values["target"],
                target=Target(
                    name=values["target"],
                    kind=target_kind,
                    ra_hours=float(values["ra"]) if values.get("ra") and target_kind == TargetKind.EQUATORIAL else None,
                    dec_degrees=float(values["dec"]) if values.get("dec") and target_kind == TargetKind.EQUATORIAL else None,
                    solar_name=values["target"] if target_kind == TargetKind.SOLAR else None,
                ),
                device_id=values["device_id"],
                scheduled_start=datetime.fromisoformat(values["scheduled_start"]).isoformat(timespec="minutes"),
                camera=CameraSettings(
                    camera=Camera(values.get("camera", "tele")),
                    exposure_seconds=float(values.get("exposure", 15)),
                    gain=int(values.get("gain", 80)),
                    frame_count=int(values.get("frame_count", 120)),
                    binning=int(values.get("binning", 1)),
                    ir_filter=values.get("ir_filter", "VIS"),
                ),
                workflow=Workflow(
                    calibrate=bool(values.get("calibrate", True)),
                    autofocus=bool(values.get("autofocus", True)),
                    infinite_focus=bool(values.get("infinite_focus", False)),
                    polar_align=bool(values.get("polar_align", False)),
                    goto=bool(values.get("goto", True)),
                    wait_before_seconds=float(values.get("wait_before", 0)),
                    wait_after_seconds=float(values.get("wait_after", 10)),
                ),
                mosaic=Mosaic(
                    rows=int(values.get("rows", 1)),
                    columns=int(values.get("columns", 1)),
                    rotation_degrees=float(values.get("rotation", 0)),
                    horizontal_scale=int(values.get("horizontal_scale", 150)),
                    vertical_scale=int(values.get("vertical_scale", 150)),
                ),
                notes=values.get("notes", existing.notes if existing else ""),
                status=existing.status if existing else SessionStatus.PLANNED,
                created_at=existing.created_at if existing else datetime.now(timezone.utc).isoformat(),
            )
            self._save_session(session)
            if values.get("save_template"):
                self.store.templates.save(SessionTemplate(
                    name=session.name,
                    target=session.target,
                    camera=session.camera,
                    workflow=session.workflow,
                    mosaic=session.mosaic,
                ))
                self.templatesChanged.emit()
            self.toast.emit("Session saved", "success")
        except Exception as exc:
            self.toast.emit(f"Could not save session: {exc}", "error")

    def _save_session(self, session: Session) -> None:
        device = self._device_by_id(session.device_id)
        session = replace(session, planned_duration_seconds=DurationEngine.calculate(session, device.hardware))
        self.store.sessions.save(session)
        self.sessionsChanged.emit()

    @Slot(str)
    def deleteSession(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if session and session.status == SessionStatus.RUNNING:
            self.toast.emit("Stop the running session before deleting it", "warning")
            return
        self.store.sessions.delete(session_id)
        self.sessionsChanged.emit()

    @Slot(str)
    def duplicateSession(self, session_id: str) -> None:
        source = self.store.sessions.get(session_id)
        if source:
            self._save_session(replace(
                source,
                id=uuid4().hex,
                name=f"{source.name} copy",
                status=SessionStatus.PLANNED,
                actual_started_at=None,
                actual_ended_at=None,
            ))

    @Slot(str)
    def runNow(self, session_id: str) -> None:
        session = self.store.sessions.get(session_id)
        if session and session.status == SessionStatus.RUNNING:
            self.toast.emit("This session is already running", "warning")
            return
        if session:
            self._save_session(replace(session, scheduled_start=datetime.now().isoformat(timespec="minutes"), status=SessionStatus.PLANNED))
            QTimer.singleShot(0, self._scheduler_tick)

    @Slot(str, str)
    def moveSessionDate(self, session_id: str, day: str) -> None:
        session = self.store.sessions.get(session_id)
        if session:
            old = datetime.fromisoformat(session.scheduled_start)
            self._save_session(replace(session, scheduled_start=f"{day}T{old.strftime('%H:%M')}"))

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
        start = datetime.now().replace(second=0, microsecond=0)
        device = self._device_by_id(self._selected_device_id)
        sessions = [
            self.store.clone_template(item, self._selected_device_id, start)
            for item in templates
        ]
        for session in stagger_mosaic_sessions(sessions, start, device.hardware):
            self.store.sessions.save(session)
        self.sessionsChanged.emit()
        count = len(sessions)
        self.toast.emit(f"Scheduled {count} pane{'s' if count != 1 else ''}", "success")

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
        self.toast.emit(f"Imported {count}; skipped {failed}", "success" if count else "warning")

    def _run_async(self, operation: str, function: Callable[[], Any]) -> None:
        def run() -> None:
            try:
                self._asyncResult.emit(operation, (True, function()))
            except Exception as exc:
                self._asyncResult.emit(operation, (False, str(exc)))

        threading.Thread(target=run, daemon=True).start()

    @Slot(str, object)
    def _handle_async_result(self, operation: str, result: tuple[bool, Any]) -> None:
        ok, value = result
        if not ok:
            self.toast.emit(f"{operation.title()}: {value}", "error")
            return
        if operation == "telescopius":
            for template in value:
                self.store.templates.save(template)
            self.templatesChanged.emit()
            self.toast.emit(f"Imported {len(value)} session templates", "success")
        elif operation == "stellarium":
            self.store.templates.save(SessionTemplate(name=value.name, target=value))
            self.templatesChanged.emit()
            self.toast.emit(f"Imported {value.name}", "success")

    def _scheduler_tick(self) -> None:
        if not self._scheduler_enabled:
            return
        now = datetime.now().astimezone()
        for device in self._devices:
            if device.id in self._active_sessions:
                continue
            worker = self._workers[device.id]
            sessions = self.store.upcoming(device.id)
            if not sessions:
                continue
            session = sessions[0]
            due = datetime.fromisoformat(session.scheduled_start)
            if due.tzinfo is None:
                due = due.astimezone()
            if due > now:
                continue
            if device.demo_mode:
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
        self.sessionsChanged.emit()
        worker.run_session(session, lambda ok, result: self._session_finished(session.id, ok, result))

    @Slot(str, str)
    def _session_progress(self, session_id: str, step: str) -> None:
        session = self.store.sessions.get(session_id)
        if session:
            self.store.sessions.save(replace(session, current_step=step))
            self.sessionsChanged.emit()

    def _session_finished(self, session_id: str, ok: bool, result: Any) -> None:
        active_device = next(
            (device_id for device_id, active_id in self._active_sessions.items() if active_id == session_id),
            None,
        )
        if active_device:
            self._active_sessions.pop(active_device, None)
        session = self.store.sessions.get(session_id)
        if not session:
            self.sessionsChanged.emit()
            return
        ended = datetime.now(timezone.utc)
        started = datetime.fromisoformat(session.actual_started_at) if session.actual_started_at else ended
        outcome = "Completed" if ok else str(result)
        final = self.store.transition(
            session.id,
            SessionStatus.DONE if ok else SessionStatus.ERROR,
            actual_ended_at=ended.isoformat(),
            current_step=outcome,
            outcome=outcome,
        )
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
            outcome=outcome,
        ))
        self.sessionsChanged.emit()
        self.historyChanged.emit()

    def shutdown(self) -> None:
        for worker in self._workers.values():
            worker.shutdown()

    def _sequence_colliding_mosaics(self) -> None:
        groups: dict[tuple[str, str], list[Session]] = {}
        for session in self.store.sessions.all():
            group_id = session.mosaic.group_id
            if not group_id or session.status != SessionStatus.PLANNED:
                continue
            groups.setdefault((group_id, session.device_id), []).append(session)
        changed = False
        for (_group_id, device_id), members in groups.items():
            if len(members) < 2:
                continue
            starts = {item.scheduled_start[:16] for item in members}
            if len(starts) != 1:
                continue
            device = self._device_by_id(device_id)
            start = datetime.fromisoformat(members[0].scheduled_start)
            for session in stagger_mosaic_sessions(members, start, device.hardware):
                self.store.sessions.save(session)
            changed = True
        if changed:
            self.sessionsChanged.emit()

    def _device_by_id(self, device_id: str) -> Device:
        return next(item for item in self._devices if item.id == device_id)

    @staticmethod
    def _duration_text(seconds: float) -> str:
        hours, remainder = divmod(max(0, int(seconds)), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _local_path(raw_path: str) -> Path:
        url = QUrl(raw_path)
        return Path(url.toLocalFile() if url.isLocalFile() else raw_path)
