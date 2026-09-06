from __future__ import annotations

import csv
import importlib
import logging
import multiprocessing
import queue
import threading
import tempfile
import re
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from typing import Any, Callable, Protocol

import requests
import subprocess

from .domain import (
    Camera,
    Device,
    HardwareProfile,
    HistoryRecord,
    Mosaic,
    Session,
    SessionStatus,
    SessionTemplate,
    Target,
    Workflow,
)
from .storage import SessionStore

LOG = logging.getLogger("astro_dwarf")
PANE_INDEX_RE = re.compile(r"pane\s+(\d+)(?:\s+of\s+(\d+))?", re.I)
PANE_TITLE_RE = re.compile(r"\s*[-–:]?\s*pane\s+\d+(?:\s+of\s+\d+)?\s*$", re.I)


def pane_sort_key(name: str) -> tuple[int, str]:
    match = PANE_INDEX_RE.search(name or "")
    return (int(match.group(1)) if match else 10**6, name or "")


def mosaic_group_title(name: str, group_id: str = "") -> str:
    stripped = PANE_TITLE_RE.sub("", name or "").strip()
    if stripped:
        return stripped
    return (group_id or "Mosaic").replace("_", " ").replace("-", " ").strip()


def observing_date(scheduled_start: str, cutoff_hour: int = 12) -> str:
    value = datetime.fromisoformat(scheduled_start)
    if value.hour < cutoff_hour:
        value -= timedelta(days=1)
    return value.date().isoformat()


def stagger_mosaic_sessions(sessions: list[Session], start: datetime, profile: HardwareProfile) -> list[Session]:
    cursor = start.replace(second=0, microsecond=0)
    result: list[Session] = []
    for index, session in enumerate(sorted(sessions, key=lambda item: pane_sort_key(item.name))):
        workflow = session.workflow
        if index > 0:
            workflow = replace(workflow, calibrate=False, polar_align=False)
        duration = DurationEngine.calculate(replace(session, workflow=workflow), profile)
        result.append(replace(
            session,
            workflow=workflow,
            scheduled_start=cursor.isoformat(timespec="minutes"),
            planned_duration_seconds=duration,
        ))
        cursor += timedelta(minutes=max(1, ceil(duration / 60.0)))
    return result


class DurationEngine:
    @staticmethod
    def calculate(session: Session | SessionTemplate, profile: HardwareProfile) -> float:
        workflow = session.workflow
        setup = profile.startup_seconds + workflow.wait_before_seconds + workflow.wait_after_seconds
        setup += profile.calibration_seconds if workflow.calibrate else 0
        setup += profile.autofocus_seconds if workflow.autofocus else 0
        setup += profile.infinite_focus_seconds if workflow.infinite_focus else 0
        setup += profile.polar_seconds if workflow.polar_align else 0
        setup += profile.slew_seconds + profile.settle_seconds if workflow.goto else 0
        panes = session.mosaic.panes
        imaging = (session.camera.exposure_seconds + profile.readout_seconds) * session.camera.frame_count * panes
        return round(setup + imaging + profile.pane_slew_seconds * max(0, panes - 1), 1)


class TelescopeBackend(Protocol):
    def call(self, operation: str, *args: Any, **kwargs: Any) -> Any: ...


class DemoBackend:
    """Deterministic backend used without hardware and by tests."""

    def call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        LOG.info("Demo telescope: %s", operation)
        time.sleep(0.03)
        return True


class DwarfSdkBackend:
    """Late-bound adapter. Keep one instance in each device worker/process."""

    FUNCTION_MAP = {
        "disconnect": "perform_disconnect",
        "reboot": "perform_reboot",
        "power_down": "perform_powerdown",
        "lights_on": "perform_powerOpenRGB",
        "lights_off": "perform_powerCloseRGB",
        "time": "perform_time",
        "timezone": "perform_timezone",
        "location": "perform_set_location",
        "host_master": "set_HostMaster",
        "host_release": "unset_HostMaster",
        "device_state": "perform_get_device_state_info",
        "astro_mode": "perform_enter_astro_mode",
        "shooting_mode": "perform_enter_shooting_mode",
        "photo": "perform_takePhoto",
        "wide_photo": "perform_takeWidePhoto",
        "calibrate": "perform_calibration",
        "stop_calibrate": "perform_stop_calibration",
        "goto": "perform_goto",
        "goto_solar": "perform_goto_stellar",
        "stop_goto": "perform_stop_goto",
        "autofocus": "perform_start_autofocus",
        "stop_autofocus": "perform_stop_autofocus",
        "polar": "start_polar_align",
        "stop_polar": "stop_polar_align",
        "joystick": "perform_motor_joystick_v3",
        "stop_motors": "perform_motor_joystick_stop_v3",
        "go_live": "perform_GoLive",
        "photo_mode": "perform_enter_photo_mode",
        "open_camera": "perform_open_camera",
        "open_wide_camera": "perform_open_widecamera",
        "astro": "perform_takeAstroPhoto",
        "wait_astro": "perform_waitEndAstroPhoto",
        "stop_astro": "perform_stopAstroPhoto",
        "wide_astro": "perform_takeAstroWidePhoto",
        "wait_wide_astro": "perform_waitEndAstroWidePhoto",
        "stop_wide_astro": "perform_stopAstroWidePhoto",
        "mosaic": "perform_start_mosaic_v3",
        "stack_status": "perform_read_astro_stacking_status_v3",
        "set_exposure": "perform_set_astro_exposure_by_name_v3",
        "set_gain": "perform_set_astro_gain_v3",
        "set_ir": "perform_set_ir_filter_v3",
        "set_count": "perform_set_astro_stack_count_v3",
        "set_mosaic_count": "perform_set_astro_mosaic_count_v3",
        "set_stack_format": "perform_set_astro_stack_format_v3",
        "set_display_source": "perform_set_astro_display_source_v3",
        "set_auto_calibration": "perform_set_astro_auto_calibration_v3",
        "read_camera": "perform_read_camera_params_http_v3",
        "set_binning": "perform_set_astro_stack_binning_v3",
        "set_brightness": "perform_set_brightness_v3",
        "set_contrast": "perform_set_contrast_v3",
        "set_saturation": "perform_set_saturation_v3",
        "set_hue": "perform_set_hue_v3",
        "set_sharpness": "perform_set_sharpness_v3",
        "set_white_balance": "perform_set_wb_preset_by_name_v3",
        "burst_start": "perform_start_burst_v3",
        "burst_stop": "perform_stop_burst_v3",
        "record_start": "perform_start_record_v3",
        "record_stop": "perform_stop_record_v3",
        "timelapse_start": "perform_start_timelapse_v3",
        "timelapse_stop": "perform_stop_timelapse_v3",
    }

    def __init__(self):
        try:
            self.api = importlib.import_module("dwarf_python_api.lib.dwarf_utils")
        except ImportError as exc:
            raise RuntimeError(
                "dwarf_python_api is not installed. Use Demo mode or install requirements-device.txt."
            ) from exc

    def call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        if operation == "manual_focus":
            focus = importlib.import_module("dwarf_python_api.proto.focus_pb2")
            message = focus.ReqManualSingleStepFocus()
            message.direction = int(args[0])
            return self.api.connect_socket(message, 15001, 0, 8)
        name = self.FUNCTION_MAP.get(operation)
        if not name or not hasattr(self.api, name):
            raise NotImplementedError(f"SDK operation is unavailable: {operation}")
        return getattr(self.api, name)(*args, **kwargs)


def _sdk_process(requests_queue, results_queue, device: Device) -> None:
    try:
        workdir = Path(tempfile.mkdtemp(prefix=f"astro-dwarf-{device.id[:8]}-"))
        (workdir / "config.py").write_text(
            "\n".join(
                [
                    f'DWARF_IP = "{device.ip_address}"',
                    f'DWARF_ID = "{int({"Dwarf II": "2", "Dwarf 3": "3", "Dwarf Mini": "5"}[device.model.value]) - 1}"',
                    'DWARF_UI = "True"',
                    'CLIENT_ID = "0000DAF2-0000-1000-8000-00805F9B34FB"',
                    'TIMEOUT_CMD = "0"',
                    'LOG_FILE = "False"',
                    "DEBUG = False",
                    "TRACE = False",
                ]
            ),
            encoding="utf-8",
        )
        (workdir / "config.ini").write_text(
            "\n".join(
                [
                    "[CONFIG]",
                    f"LATITUDE = {device.latitude}",
                    f"LONGITUDE = {device.longitude}",
                    f"TIMEZONE = {device.timezone_name}",
                    f"BLE_STA_SSID = {device.wifi_ssid}",
                    f"BLE_STA_PWD = {device.wifi_password}",
                ]
            ),
            encoding="utf-8",
        )
        import os
        os.chdir(workdir)
        backend = DwarfSdkBackend()
    except Exception as exc:
        results_queue.put((None, False, repr(exc)))
        return
    def execute(request_id, operation, args, kwargs) -> None:
        try:
            results_queue.put((request_id, True, backend.call(operation, *args, **kwargs)))
        except Exception as exc:
            results_queue.put((request_id, False, repr(exc)))

    while True:
        request = requests_queue.get()
        if request is None:
            return
        request_id, operation, args, kwargs = request
        if operation in {"wait_astro", "wait_wide_astro"}:
            threading.Thread(target=execute, args=(request_id, operation, args, kwargs), daemon=True).start()
        else:
            execute(request_id, operation, args, kwargs)


class ProcessSdkBackend:
    """One SDK process per telescope, avoiding the SDK's global-state collision."""

    def __init__(self, device: Device, timeout: float = 120):
        context = multiprocessing.get_context("spawn")
        self.requests = context.Queue()
        self.results = context.Queue()
        self.timeout = timeout
        self.sequence = 0
        self._sequence_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[int, queue.Queue] = {}
        self.process = context.Process(target=_sdk_process, args=(self.requests, self.results, device), daemon=True)
        self.process.start()
        self._response_thread = threading.Thread(target=self._route_results, daemon=True, name=f"sdk-results-{device.id}")
        self._response_thread.start()

    def _route_results(self) -> None:
        while self.process.is_alive():
            try:
                result = self.results.get(timeout=0.25)
            except queue.Empty:
                continue
            request_id = result[0]
            if request_id is None:
                with self._pending_lock:
                    pending = list(self._pending.values())
                for channel in pending:
                    channel.put(result)
                continue
            with self._pending_lock:
                channel = self._pending.get(request_id)
            if channel:
                channel.put(result)

    def call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        with self._sequence_lock:
            self.sequence += 1
            request_id = self.sequence
        channel: queue.Queue = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = channel
        self.requests.put((request_id, operation, args, kwargs))
        operation_timeout = 24 * 60 * 60 if operation in {"wait_astro", "wait_wide_astro"} else self.timeout
        try:
            deadline = time.monotonic() + operation_timeout
            while True:
                try:
                    received_id, ok, value = channel.get(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
                    break
                except queue.Empty:
                    if not self.process.is_alive():
                        raise RuntimeError("Telescope SDK worker stopped")
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"Telescope operation timed out: {operation}")
            if not ok:
                raise RuntimeError(value)
            return value
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def close(self) -> None:
        self.requests.put(None)
        self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.terminate()


class DwarfClient:
    def __init__(self, device: Device, backend: TelescopeBackend | None = None):
        self.device = device
        self.backend = backend or DemoBackend()
        self.connected = False

    @classmethod
    def real(cls, device: Device) -> "DwarfClient":
        return cls(device, ProcessSdkBackend(device))

    def connect(self) -> bool:
        # A configured Wi-Fi endpoint is verified with SET_TIME, matching the
        # stable SDK connection path. BLE/STA provisioning remains backend-owned.
        self.connected = bool(self.backend.call("time"))
        if self.connected:
            self.backend.call("host_master")
            self.backend.call("device_state")
            self.backend.call("location")
        return self.connected

    def disconnect(self) -> None:
        if self.connected:
            self.backend.call("host_release")
        self.backend.call("disconnect")
        self.connected = False

    def action(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        return self.backend.call(operation, *args, **kwargs)

    def start_preview(self, camera: Camera) -> None:
        self.action("go_live")
        self.action("photo_mode")
        self.action("open_wide_camera" if camera == Camera.WIDE else "open_camera")

    def execute(self, session: Session, progress: Callable[[str], None], stop: threading.Event) -> None:
        def wait(seconds: float) -> None:
            if seconds > 0 and stop.wait(seconds):
                raise InterruptedError("Session stopped")

        def step(name: str, operation: str | None = None, *args: Any) -> None:
            if stop.is_set():
                raise InterruptedError("Session stopped")
            progress(name)
            if operation:
                result = self.action(operation, *args)
                if result is False:
                    raise RuntimeError(f"{name} failed")

        if not self.connected:
            progress("Connecting")
            if not self.connect():
                raise RuntimeError("Could not connect to telescope")
        # GO_LIVE first closes a previous capture even when the scope was left
        # in another mode; this order matches the field-tested V3 workflow.
        step("Preparing", "go_live")
        wait(session.workflow.wait_before_seconds)
        if session.target.kind.value == "solar":
            solar_name = (session.target.solar_name or session.target.name).lower()
            shooting_mode = 8 if solar_name == "sun" else 9 if solar_name == "moon" else 10
            step("Entering solar-system mode", "shooting_mode", shooting_mode, 2)
        else:
            step("Entering astro mode", "astro_mode")
        if session.workflow.polar_align:
            step("Polar alignment", "polar")
        if session.workflow.calibrate:
            step("Calibrating", "calibrate")
        if session.workflow.autofocus:
            step("Auto focus", "autofocus", False)
        elif session.workflow.infinite_focus:
            step("Infinite focus", "autofocus", True)
        if session.workflow.goto and session.target.ra_hours is not None and session.target.dec_degrees is not None:
            step("Slewing", "goto", session.target.ra_hours, session.target.dec_degrees, session.target.name)
        elif session.workflow.goto and session.target.kind.value == "solar":
            solar_ids = {
                "mercury": 1, "venus": 2, "mars": 3, "jupiter": 4, "saturn": 5,
                "uranus": 6, "neptune": 7, "moon": 8, "sun": 9,
            }
            solar_name = (session.target.solar_name or session.target.name).lower()
            if solar_name not in solar_ids:
                raise ValueError(f"Unknown solar-system target: {solar_name}")
            step("Slewing to solar target", "goto_solar", solar_ids[solar_name], solar_name.title())
        model_id = {"Dwarf II": "2", "Dwarf 3": "3", "Dwarf Mini": "5"}[self.device.model.value]
        step("Setting exposure", "set_exposure", str(session.camera.exposure_seconds), model_id, session.camera.camera.value)
        step("Setting gain", "set_gain", session.camera.gain, session.camera.camera.value)
        step("Setting IR filter", "set_ir", session.camera.ir_filter)
        step("Setting frame count", "set_count", session.camera.frame_count, session.camera.camera.value)
        step("Setting binning", "set_binning", session.camera.binning)
        if session.mosaic.panes > 1:
            step("Setting mosaic frame count", "set_mosaic_count", session.camera.frame_count)
            step("Starting mosaic", "mosaic", session.mosaic.horizontal_scale, session.mosaic.vertical_scale, session.mosaic.rotation_degrees)
            step("Waiting for mosaic", "wait_astro")
        elif session.camera.camera == Camera.WIDE:
            step("Imaging (wide)", "wide_astro")
            step("Waiting for wide stack", "wait_wide_astro")
        else:
            step("Imaging", "astro")
            step("Waiting for stack", "wait_astro")
        wait(session.workflow.wait_after_seconds)


class DeviceHub:
    """Owns independent clients and schedulers; backends can be process-isolated."""

    def __init__(self):
        self.clients: dict[str, DwarfClient] = {}
        self.schedulers: dict[str, Scheduler] = {}

    def register(self, device: Device, store: SessionStore, on_change: Callable[[], None]) -> DwarfClient:
        client = DwarfClient(device) if device.demo_mode else DwarfClient.real(device)
        self.clients[device.id] = client
        self.schedulers[device.id] = Scheduler(device, client, store, on_change)
        return client

    def start_all(self) -> None:
        for scheduler in self.schedulers.values():
            scheduler.start()

    def stop_all(self) -> None:
        for scheduler in self.schedulers.values():
            scheduler.stop()


class Scheduler:
    def __init__(
        self,
        device: Device,
        client: DwarfClient,
        store: SessionStore,
        on_change: Callable[[], None] = lambda: None,
    ):
        self.device, self.client, self.store = device, client, store
        self.on_change = on_change
        self.before_run: Callable[[Session], None] = lambda session: None
        self.after_run: Callable[[Session], None] = lambda session: None
        self.ignore_times = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name=f"scheduler-{self.device.id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self.client.connected:
            try:
                self.client.action("stop_astro")
                self.client.action("stop_wide_astro")
                self.client.action("stop_motors")
            except Exception:
                LOG.exception("Could not stop all device activity for %s", self.device.name)

    def _loop(self) -> None:
        while not self._stop.is_set():
            upcoming = self.store.upcoming(self.device.id)
            if not upcoming:
                self._stop.wait(0.5)
                continue
            session = upcoming[0]
            try:
                due = datetime.fromisoformat(session.scheduled_start)
                if due.tzinfo is None:
                    due = due.astimezone()
                if not self.ignore_times and due > datetime.now().astimezone():
                    self._stop.wait(min(1.0, (due - datetime.now().astimezone()).total_seconds()))
                    continue
                self._run(session)
            except Exception:
                LOG.exception("Scheduler error for %s", session.name)
                self._stop.wait(1)

    def _run(self, session: Session) -> None:
        self.before_run(session)
        started = datetime.now(timezone.utc)
        session = self.store.transition(
            session.id,
            SessionStatus.RUNNING,
            actual_started_at=started.isoformat(),
            current_step="Starting",
        )
        self.on_change()

        def progress(step: str) -> None:
            nonlocal session
            session = replace(session, current_step=step)
            self.store.sessions.save(session)
            self.on_change()

        outcome = "Completed"
        status = SessionStatus.DONE
        try:
            self.client.execute(session, progress, self._stop)
        except Exception as exc:
            outcome, status = str(exc), SessionStatus.ERROR
        ended = datetime.now(timezone.utc)
        session = self.store.transition(
            session.id,
            status,
            actual_ended_at=ended.isoformat(),
            outcome=outcome,
            current_step=outcome,
        )
        self.store.history.save(
            HistoryRecord(
                session_id=session.id,
                device_id=session.device_id,
                target_name=session.target.name,
                scheduled_start=session.scheduled_start,
                actual_started_at=session.actual_started_at,
                actual_ended_at=session.actual_ended_at,
                planned_duration_seconds=session.planned_duration_seconds,
                actual_duration_seconds=(ended - started).total_seconds(),
                frame_count=session.camera.frame_count,
                outcome=outcome,
            )
        )
        self.after_run(session)
        self.on_change()


class StellariumClient:
    def __init__(self, base_url: str = "http://localhost:8090"):
        self.base_url = base_url.rstrip("/")

    def current_target(self) -> Target:
        response = requests.get(f"{self.base_url}/api/objects/info", params={"format": "json"}, timeout=3)
        response.raise_for_status()
        data = response.json()
        name = data.get("localized-name") or data.get("name") or "Stellarium target"
        ra_degrees = data.get("raJ2000")
        dec = data.get("decJ2000")
        if ra_degrees is None or dec is None:
            raise ValueError("Select a target in Stellarium before importing")
        return Target(name=name, ra_hours=(float(ra_degrees) % 360) / 15, dec_degrees=float(dec))


class VideoService:
    """UI-agnostic MJPEG/RTSP decoder that emits JPEG frames."""

    def __init__(self, device: Device, on_frame: Callable[[bytes], None]):
        self.device = device
        self.on_frame = on_frame
        self.camera = device.camera
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        wide = self.camera == Camera.WIDE
        if self.device.model.value in ("Dwarf 3", "Dwarf Mini"):
            return f"rtsp://{self.device.ip_address}/{'ch1' if wide else 'ch0'}/stream0"
        return f"http://{self.device.ip_address}:8092/{'secondstream' if wide else 'mainstream'}"

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"video-{self.device.id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def set_camera(self, camera: Camera) -> None:
        was_running = self.running
        self.stop()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        self.camera = camera
        if was_running:
            self.start()

    def _run(self) -> None:
        try:
            if self.url.startswith("rtsp://"):
                self._process = subprocess.Popen(
                    ["ffmpeg", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", self.url, "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "5", "-"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self._read_jpegs(self._process.stdout)
            else:
                with requests.get(self.url, stream=True, timeout=(3, 10)) as response:
                    response.raise_for_status()
                    self._read_jpegs(response.raw)
        except Exception as exc:
            if not self._stop.is_set():
                LOG.warning("%s video unavailable: %s", self.device.name, exc)

    def _read_jpegs(self, source) -> None:
        buffer = b""
        while not self._stop.is_set():
            chunk = source.read(8192)
            if not chunk:
                return
            buffer += chunk
            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9", start + 2)
            if start >= 0 and end > start:
                self.on_frame(buffer[start : end + 2])
                buffer = buffer[end + 2 :]
            elif len(buffer) > 5_000_000:
                buffer = buffer[-64_000:]


def _parse_ra(value: str) -> float:
    text = value.strip().lower().replace("hr", "").replace("hours", "")
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return float(text)
    values = [float(part) for part in re.findall(r"\d+(?:\.\d+)?", text)]
    if not values:
        raise ValueError(f"Invalid right ascension: {value}")
    return values[0] + (values[1] if len(values) > 1 else 0) / 60 + (values[2] if len(values) > 2 else 0) / 3600


def _parse_dec(value: str) -> float:
    text = value.strip().lower().replace("º", " ").replace("°", " ")
    sign = -1 if text.startswith("-") else 1
    values = [float(part) for part in re.findall(r"\d+(?:\.\d+)?", text)]
    if not values:
        raise ValueError(f"Invalid declination: {value}")
    return sign * (values[0] + (values[1] if len(values) > 1 else 0) / 60 + (values[2] if len(values) > 2 else 0) / 3600)


def import_telescopius(path: Path) -> list[SessionTemplate]:
    templates: list[SessionTemplate] = []
    group = path.stem
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for index, row in enumerate(csv.DictReader(handle), 1):
            lowered = {str(k).strip().lower(): v for k, v in row.items()}
            name = (
                lowered.get("target")
                or lowered.get("name")
                or lowered.get("familiar name")
                or lowered.get("catalogue entry")
                or lowered.get("pane")
                or f"{group} pane {index}"
            )
            ra = (
                lowered.get("ra")
                or lowered.get("right ascension")
                or lowered.get("ra (hours)")
                or lowered.get("right ascension (j2000)")
            )
            dec = (
                lowered.get("dec")
                or lowered.get("declination")
                or lowered.get("dec (degrees)")
                or lowered.get("declination (j2000)")
            )
            if ra in (None, "") or dec in (None, ""):
                continue
            if str(lowered.get("pane", "")).strip().lower() == "center":
                continue
            templates.append(
                SessionTemplate(
                    name=str(name),
                    target=Target(name=str(name), ra_hours=_parse_ra(str(ra)), dec_degrees=_parse_dec(str(dec))),
                    mosaic=Mosaic(group_id=group),
                    notes=f"Imported from Telescopius: {path.name}",
                )
            )
    return templates


class MemoryLogHandler(logging.Handler):
    def __init__(self, limit: int = 250):
        super().__init__()
        self.limit = limit
        self.lines: list[str] = []
        self.on_change: Callable[[], None] = lambda: None

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))
        del self.lines[:-self.limit]
        self.on_change()
