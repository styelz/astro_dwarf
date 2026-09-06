import json
import time
from datetime import datetime, timedelta

import pytest

from astro_dwarf.domain import (
    CameraSettings,
    Device,
    HardwareProfile,
    Mosaic,
    Session,
    SessionStatus,
    Target,
    TargetKind,
    DeviceModel,
    Workflow,
)
from astro_dwarf.services import (
    DemoBackend,
    DurationEngine,
    DwarfClient,
    Scheduler,
    StellariumClient,
    _parse_dec,
    _parse_ra,
    import_telescopius,
    mosaic_group_title,
    observing_date,
    pane_sort_key,
    stagger_mosaic_sessions,
)
from astro_dwarf.storage import SessionStore


def make_session(device_id: str = "scope") -> Session:
    return Session(
        name="M42",
        target=Target(name="M42", ra_hours=5.5, dec_degrees=-5.4),
        device_id=device_id,
        scheduled_start=(datetime.now() + timedelta(hours=1)).isoformat(timespec="minutes"),
        camera=CameraSettings(exposure_seconds=10, frame_count=10),
        workflow=Workflow(calibrate=True, autofocus=True, goto=True, wait_after_seconds=5),
        mosaic=Mosaic(rows=2, columns=2),
    )


def test_duration_uses_hardware_steps_frames_and_panes():
    profile = HardwareProfile(
        startup_seconds=5,
        calibration_seconds=20,
        autofocus_seconds=10,
        slew_seconds=4,
        settle_seconds=1,
        readout_seconds=2,
        pane_slew_seconds=3,
    )
    # setup: 5 + 5 wait + 20 + 10 + 4 + 1 = 45
    # imaging: (10 + 2) * 10 * 4 = 480; inter-pane = 9
    assert DurationEngine.calculate(make_session(), profile) == 534


def test_store_round_trip_and_status_machine(tmp_path):
    store = SessionStore(tmp_path)
    session = make_session()
    store.sessions.save(session)
    loaded = store.sessions.get(session.id)
    assert loaded is not None
    assert loaded.target.name == "M42"
    running = store.transition(session.id, SessionStatus.RUNNING)
    assert running.status == SessionStatus.RUNNING
    done = store.transition(session.id, SessionStatus.DONE)
    assert done.status == SessionStatus.DONE
    with pytest.raises(ValueError):
        store.transition(session.id, SessionStatus.PLANNED)


def test_recover_running(tmp_path):
    store = SessionStore(tmp_path)
    session = make_session()
    store.sessions.save(session)
    store.transition(session.id, SessionStatus.RUNNING, actual_started_at=datetime.now().isoformat())
    recovered = store.recover_running()
    assert len(recovered) == 1
    assert recovered[0].status == SessionStatus.PLANNED
    assert recovered[0].actual_started_at is None


def test_multiple_devices_have_independent_queues(tmp_path):
    store = SessionStore(tmp_path)
    first, second = Device(name="A"), Device(name="B")
    store.devices.save(first)
    store.devices.save(second)
    store.sessions.save(make_session(first.id))
    store.sessions.save(make_session(second.id))
    assert len(store.upcoming(first.id)) == 1
    assert len(store.upcoming(second.id)) == 1


def test_scheduler_executes_and_writes_history(tmp_path):
    store = SessionStore(tmp_path)
    device = Device(name="Test scope")
    session = make_session(device.id)
    session.scheduled_start = datetime.now().isoformat(timespec="minutes")
    session.workflow = Workflow(calibrate=False, autofocus=False, goto=False, wait_after_seconds=0)
    session.mosaic = Mosaic()
    session.planned_duration_seconds = DurationEngine.calculate(session, device.hardware)
    store.sessions.save(session)
    scheduler = Scheduler(device, DwarfClient(device, DemoBackend()), store)
    scheduler.ignore_times = True
    scheduler.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        saved = store.sessions.get(session.id)
        if saved and saved.status in (SessionStatus.DONE, SessionStatus.ERROR):
            break
        time.sleep(0.03)
    scheduler.stop()
    assert store.sessions.get(session.id).status == SessionStatus.DONE
    assert store.history.all()[0].session_id == session.id


def test_telescopius_and_old_json_import(tmp_path):
    csv_path = tmp_path / "mosaic.csv"
    csv_path.write_text("Target,RA,Dec\nM31 pane 1,0.71,41.2\nM31 pane 2,0.75,41.1\n", encoding="utf-8")
    imported = import_telescopius(csv_path)
    assert len(imported) == 2
    assert imported[0].mosaic.group_id == "mosaic"
    assert mosaic_group_title("2x4 Mosaic - pane 4 of 8", "group") == "2x4 Mosaic"
    assert mosaic_group_title("M31 pane 1", "mosaic") == "M31"
    assert pane_sort_key("pane 8 of 8")[0] == 8
    assert observing_date("2026-09-06T06:50", 12) == "2026-09-05"
    assert observing_date("2026-09-06T22:00", 12) == "2026-09-06"
    assert _parse_ra("16.4599hr") == pytest.approx(16.4599)
    assert _parse_ra("16h 22' 49\"") == pytest.approx(16.3803, rel=1e-4)
    assert _parse_dec("-23º 32' 13\"") == pytest.approx(-23.5369, rel=1e-4)

    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"command": {
        "id_command": {"description": "Legacy M42", "date": "2026-09-06", "time": "22:30:00"},
        "goto_manual": {"do_action": True, "target": "M42", "ra_coord": 5.5, "dec_coord": -5.4},
        "setup_camera": {"exposure": "15", "gain": "80", "count": 20},
        "calibration": {"do_action": True},
        "auto_focus": {"do_action": True},
    }}), encoding="utf-8")
    store = SessionStore(tmp_path / "store")
    count, failed = store.import_old_sessions([legacy], "scope")
    assert (count, failed) == (1, 0)
    assert store.sessions.all()[0].target.name == "M42"


def test_stagger_mosaic_sessions_sequences_panes_and_skips_later_calibration():
    start = datetime(2026, 9, 6, 22, 0)
    sessions = [
        Session(
            name="2x4 Mosaic - pane 2 of 8",
            target=Target(name="2x4 Mosaic - pane 2 of 8"),
            device_id="scope",
            scheduled_start="2026-09-06T22:00",
            mosaic=Mosaic(group_id="mosaic"),
            camera=CameraSettings(exposure_seconds=10, frame_count=10),
        ),
        Session(
            name="2x4 Mosaic - pane 1 of 8",
            target=Target(name="2x4 Mosaic - pane 1 of 8"),
            device_id="scope",
            scheduled_start="2026-09-06T22:00",
            mosaic=Mosaic(group_id="mosaic"),
            camera=CameraSettings(exposure_seconds=10, frame_count=10),
        ),
    ]
    staggered = stagger_mosaic_sessions(sessions, start, HardwareProfile())
    assert [item.name for item in staggered] == ["2x4 Mosaic - pane 1 of 8", "2x4 Mosaic - pane 2 of 8"]
    assert staggered[0].scheduled_start != staggered[1].scheduled_start
    assert staggered[0].workflow.calibrate is True
    assert staggered[1].workflow.calibrate is False
    assert staggered[1].workflow.polar_align is False


def test_stellarium_uses_structured_object_endpoint(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"localized-name": "Vega", "raJ2000": 279.2347, "decJ2000": 38.7837}

    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr("astro_dwarf.services.requests.get", fake_get)
    target = StellariumClient("http://localhost:8090").current_target()
    assert captured["url"].endswith("/api/objects/info")
    assert captured["params"] == {"format": "json"}
    assert target.name == "Vega"
    assert target.ra_hours == pytest.approx(18.6156, rel=1e-4)


def test_client_handshake_astro_mode_and_mini_model_id():
    class RecordingBackend:
        def __init__(self):
            self.calls = []

        def call(self, operation, *args, **kwargs):
            self.calls.append((operation, args))
            return True

    device = Device(name="Mini", model=DeviceModel.DWARF_MINI)
    backend = RecordingBackend()
    client = DwarfClient(device, backend)
    client.execute(
        Session(
            name="Mini test",
            target=Target(name="No GOTO"),
            device_id=device.id,
            scheduled_start=datetime.now().isoformat(),
            workflow=Workflow(calibrate=False, autofocus=False, goto=False, wait_after_seconds=0),
            camera=CameraSettings(exposure_seconds=30, frame_count=1),
        ),
        lambda _: None,
        __import__("threading").Event(),
    )
    operations = [operation for operation, _ in backend.calls]
    assert operations[:4] == ["time", "host_master", "device_state", "location"]
    assert "astro_mode" in operations
    exposure_call = next(args for operation, args in backend.calls if operation == "set_exposure")
    assert exposure_call[1] == "5"


def test_solar_mosaic_uses_correct_mode_scale_and_count():
    class RecordingBackend:
        def __init__(self):
            self.calls = []

        def call(self, operation, *args, **kwargs):
            self.calls.append((operation, args))
            return True

    device = Device(name="D3")
    backend = RecordingBackend()
    client = DwarfClient(device, backend)
    client.execute(
        Session(
            name="Sun mosaic",
            target=Target(name="Sun", kind=TargetKind.SOLAR, solar_name="Sun"),
            device_id=device.id,
            scheduled_start=datetime.now().isoformat(),
            workflow=Workflow(calibrate=False, autofocus=False, goto=True, wait_after_seconds=0),
            camera=CameraSettings(frame_count=42),
            mosaic=Mosaic(rows=2, columns=3, horizontal_scale=140, vertical_scale=160),
        ),
        lambda _: None,
        __import__("threading").Event(),
    )
    calls = dict(backend.calls)
    assert calls["shooting_mode"] == (8, 2)
    assert calls["set_mosaic_count"] == (42,)
    assert calls["mosaic"] == (140, 160, 0)
