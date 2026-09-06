import importlib.util
import time
from dataclasses import replace

import pytest
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from astro_dwarf import __version__
from astro_dwarf.domain import CameraSettings, Device, Mosaic, Session, SessionStatus, SessionTemplate, Target
from astro_dwarf.qt_backend import AppBackend
from astro_dwarf.storage import SessionStore


def test_app_backend_exposes_package_version(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    backend = AppBackend(tmp_path)
    assert backend.appVersion == __version__
    application.processEvents()


@pytest.mark.skipif(
    importlib.util.find_spec("dwarf_python_api") is None
    or importlib.util.find_spec("websockets") is None,
    reason="optional telescope SDK is not installed",
)
def test_telescope_sdk_imports_websocket_client():
    from dwarf_python_api.lib import dwarf_utils

    assert callable(getattr(dwarf_utils, "connect_socket", None))


@pytest.mark.skipif(
    importlib.util.find_spec("dwarf_python_api") is None,
    reason="optional telescope SDK is not installed",
)
def test_isolated_worker_starts_and_forwards_logs(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    store = SessionStore(tmp_path)
    store.devices.save(Device(name="Worker test", demo_mode=False))
    backend = AppBackend(tmp_path)

    loop = QEventLoop()
    QTimer.singleShot(2500, loop.quit)
    loop.exec()

    messages = [item["message"] for item in backend.logs]
    assert any("Starting isolated worker" in message for message in messages)
    assert any("Worker ready" in message or "Worker configured" in message for message in messages), messages
    backend.shutdown()
    application.processEvents()


def test_connect_request_never_waits_on_device_io(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    backend = AppBackend(tmp_path)
    device = replace(backend._devices[0], demo_mode=False)
    backend._devices[0] = device

    class DelayedWorker:
        def connect_device(self, callback):
            self.callback = callback

    worker = DelayedWorker()
    backend._workers[device.id] = worker
    started = time.perf_counter()
    backend.connectDevice(device.id)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.05
    assert any("UI remains available" in item["message"] for item in backend.logs)
    worker.callback(False, "simulated timeout")
    assert any("Connection failed" in item["message"] for item in backend.logs)
    application.processEvents()


def test_delete_device_and_template(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    backend = AppBackend(tmp_path)
    first_id = backend.selectedDeviceId
    backend.addDevice()
    second_id = backend.selectedDeviceId
    assert len(backend.devices) == 2
    backend.deleteDevice(second_id)
    assert len(backend.devices) == 1
    assert backend.selectedDeviceId == first_id
    backend.deleteDevice(first_id)
    assert len(backend.devices) == 1
    backend.store.templates.save(SessionTemplate(name="Orion", target=Target(name="M42")))
    template_id = backend.templates[0]["id"]
    backend.deleteTemplate(template_id)
    assert backend.templates == []
    application.processEvents()


def test_mosaic_templates_group_and_schedule_staggers(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    backend = AppBackend(tmp_path)
    for index in (2, 1, 3):
        backend.store.templates.save(SessionTemplate(
            name=f"M31 pane {index}",
            target=Target(name=f"M31 pane {index}", ra_hours=0.7, dec_degrees=41.2),
            mosaic=Mosaic(group_id="m31"),
            camera=CameraSettings(exposure_seconds=10, frame_count=6),
        ))
    groups = backend.templates
    assert len(groups) == 1
    assert groups[0]["is_group"] is True
    assert groups[0]["pane_count"] == 3
    assert groups[0]["name"] == "M31"
    backend.scheduleTemplate(groups[0]["id"])
    sessions = sorted(backend.store.sessions.all(), key=lambda item: item.scheduled_start)
    assert [item.name for item in sessions] == ["M31 pane 1", "M31 pane 2", "M31 pane 3"]
    assert len({item.scheduled_start for item in sessions}) == 3
    assert sessions[0].workflow.calibrate is True
    assert sessions[1].workflow.calibrate is False
    assert all(item["observing_date"] for item in backend.sessions)
    backend.deleteTemplate(groups[0]["id"])
    assert backend.templates == []
    application.processEvents()


def test_colliding_mosaic_sessions_are_staggered_on_load(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    store = SessionStore(tmp_path)
    device = store.seed_device()
    for index in (3, 1, 2):
        store.sessions.save(Session(
            name=f"M31 pane {index}",
            target=Target(name=f"M31 pane {index}"),
            device_id=device.id,
            scheduled_start="2026-09-06T06:50",
            mosaic=Mosaic(group_id="m31"),
            camera=CameraSettings(exposure_seconds=10, frame_count=10),
            status=SessionStatus.PLANNED,
        ))
    backend = AppBackend(tmp_path)
    sessions = sorted(backend.store.sessions.all(), key=lambda item: item.scheduled_start)
    assert len({item.scheduled_start for item in sessions}) == 3
    assert sessions[0].name == "M31 pane 1"
    assert backend.sessions[0]["observing_date"] == "2026-09-05"
    application.processEvents()


def test_running_session_cannot_be_deleted_or_requeued(tmp_path):
    application = QCoreApplication.instance() or QCoreApplication([])
    backend = AppBackend(tmp_path)
    device = backend._devices[0]
    session = Session(
        name="Active",
        target=Target(name="M42"),
        device_id=device.id,
        scheduled_start="2026-09-06T22:00",
        status=SessionStatus.RUNNING,
    )
    backend.store.sessions.save(session)

    backend.deleteSession(session.id)
    backend.runNow(session.id)

    saved = backend.store.sessions.get(session.id)
    assert saved is not None
    assert saved.status == SessionStatus.RUNNING
    application.processEvents()
