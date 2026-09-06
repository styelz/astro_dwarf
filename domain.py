from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def new_id() -> str:
    return uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeviceModel(StrEnum):
    DWARF_II = "Dwarf II"
    DWARF_3 = "Dwarf 3"
    DWARF_MINI = "Dwarf Mini"


class Camera(StrEnum):
    TELE = "tele"
    WIDE = "wide"


class TargetKind(StrEnum):
    EQUATORIAL = "equatorial"
    SOLAR = "solar"
    NONE = "none"


class SessionStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass(slots=True)
class HardwareProfile:
    slew_seconds: float = 20
    settle_seconds: float = 10
    calibration_seconds: float = 90
    autofocus_seconds: float = 45
    infinite_focus_seconds: float = 15
    polar_seconds: float = 180
    readout_seconds: float = 1.2
    pane_slew_seconds: float = 12
    startup_seconds: float = 8


@dataclass(slots=True)
class Device:
    name: str
    model: DeviceModel = DeviceModel.DWARF_3
    id: str = field(default_factory=new_id)
    ip_address: str = "192.168.88.1"
    camera: Camera = Camera.TELE
    color: str = "#6C8CFF"
    hardware: HardwareProfile = field(default_factory=HardwareProfile)
    ble_enabled: bool = True
    wifi_ssid: str = ""
    wifi_password: str = ""
    demo_mode: bool = True
    latitude: float = 0
    longitude: float = 0
    timezone_name: str = "UTC"
    stellarium_url: str = "http://localhost:8090"
    observing_day_cutoff_hour: int = 12


@dataclass(slots=True)
class Target:
    name: str = "Untitled target"
    kind: TargetKind = TargetKind.EQUATORIAL
    ra_hours: float | None = None
    dec_degrees: float | None = None
    solar_name: str | None = None


@dataclass(slots=True)
class CameraSettings:
    camera: Camera = Camera.TELE
    exposure_seconds: float = 15
    gain: int = 80
    frame_count: int = 120
    binning: int = 1
    ir_filter: str = "VIS"


@dataclass(slots=True)
class Workflow:
    calibrate: bool = True
    autofocus: bool = True
    infinite_focus: bool = False
    polar_align: bool = False
    goto: bool = True
    wait_before_seconds: float = 0
    wait_after_seconds: float = 10


@dataclass(slots=True)
class Mosaic:
    rows: int = 1
    columns: int = 1
    rotation_degrees: float = 0
    horizontal_scale: int = 150
    vertical_scale: int = 150
    group_id: str | None = None

    @property
    def panes(self) -> int:
        return max(1, self.rows * self.columns)


@dataclass(slots=True)
class SessionTemplate:
    name: str
    target: Target
    id: str = field(default_factory=new_id)
    camera: CameraSettings = field(default_factory=CameraSettings)
    workflow: Workflow = field(default_factory=Workflow)
    mosaic: Mosaic = field(default_factory=Mosaic)
    notes: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Session:
    name: str
    target: Target
    device_id: str
    scheduled_start: str
    id: str = field(default_factory=new_id)
    template_id: str | None = None
    camera: CameraSettings = field(default_factory=CameraSettings)
    workflow: Workflow = field(default_factory=Workflow)
    mosaic: Mosaic = field(default_factory=Mosaic)
    status: SessionStatus = SessionStatus.PLANNED
    current_step: str = "Waiting"
    planned_duration_seconds: float = 0
    actual_started_at: str | None = None
    actual_ended_at: str | None = None
    outcome: str = ""
    notes: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class HistoryRecord:
    session_id: str
    device_id: str
    target_name: str
    scheduled_start: str
    actual_started_at: str | None
    actual_ended_at: str | None
    planned_duration_seconds: float
    actual_duration_seconds: float
    frame_count: int
    outcome: str
    id: str = field(default_factory=new_id)
    recorded_at: str = field(default_factory=utc_now)


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)


def hardware_from_dict(data: dict[str, Any]) -> HardwareProfile:
    return HardwareProfile(**data)


def device_from_dict(data: dict[str, Any]) -> Device:
    data = dict(data)
    data["model"] = DeviceModel(data.get("model", DeviceModel.DWARF_3))
    data["camera"] = Camera(data.get("camera", Camera.TELE))
    data["hardware"] = hardware_from_dict(data.get("hardware", {}))
    return Device(**data)


def target_from_dict(data: dict[str, Any]) -> Target:
    data = dict(data)
    data["kind"] = TargetKind(data.get("kind", TargetKind.EQUATORIAL))
    return Target(**data)


def camera_from_dict(data: dict[str, Any]) -> CameraSettings:
    data = dict(data)
    data["camera"] = Camera(data.get("camera", Camera.TELE))
    return CameraSettings(**data)


def template_from_dict(data: dict[str, Any]) -> SessionTemplate:
    data = dict(data)
    data["target"] = target_from_dict(data["target"])
    data["camera"] = camera_from_dict(data.get("camera", {}))
    data["workflow"] = Workflow(**data.get("workflow", {}))
    data["mosaic"] = Mosaic(**data.get("mosaic", {}))
    return SessionTemplate(**data)


def session_from_dict(data: dict[str, Any]) -> Session:
    data = dict(data)
    data["target"] = target_from_dict(data["target"])
    data["camera"] = camera_from_dict(data.get("camera", {}))
    data["workflow"] = Workflow(**data.get("workflow", {}))
    data["mosaic"] = Mosaic(**data.get("mosaic", {}))
    data["status"] = SessionStatus(data.get("status", SessionStatus.PLANNED))
    return Session(**data)


def history_from_dict(data: dict[str, Any]) -> HistoryRecord:
    return HistoryRecord(**data)
