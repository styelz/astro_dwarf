from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .location import has_site_coordinates


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


class WifiMode(StrEnum):
    AUTO = "auto"
    AP = "ap"
    STA = "sta"


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
    ble_password: str = "DWARF_12345678"
    wifi_mode: WifiMode = WifiMode.AUTO
    wifi_ssid: str = ""
    wifi_password: str = ""
    latitude: float = 0
    longitude: float = 0
    timezone_name: str = "UTC"
    location_configured: bool = False
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
    # rows/columns drive the telescope's own mosaic. Imported Telescopius panes
    # keep those at 1x1 and store the CSV grid in grid_rows/grid_columns plus
    # this pane's row/column. The editor shows the CSV grid; capture still
    # treats each pane as a single pointing.
    rows: int = 1
    columns: int = 1
    rotation_degrees: float = 0
    horizontal_scale: int = 150
    vertical_scale: int = 150
    group_id: str | None = None
    grid_rows: int = 0
    grid_columns: int = 0
    row: int = 0
    column: int = 0

    @property
    def imported_plan(self) -> bool:
        return self.grid_rows >= 1 and self.grid_columns >= 1

    @property
    def panes(self) -> int:
        if self.imported_plan:
            return 1
        return max(1, self.rows * self.columns)

    @property
    def grid_text(self) -> str:
        if self.grid_rows < 1 or self.grid_columns < 1:
            return ""
        return f"{self.grid_rows}×{self.grid_columns}"

    @property
    def position_text(self) -> str:
        if self.row < 1 or self.column < 1:
            return ""
        return f"R{self.row} C{self.column}"


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
    summary: str = ""
    notes: str = ""
    captured_frame_count: int | None = None


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)


def hardware_from_dict(data: dict[str, Any]) -> HardwareProfile:
    return HardwareProfile(**data)


def device_from_dict(data: dict[str, Any]) -> Device:
    data = dict(data)
    data.pop("demo_mode", None)
    data.pop("location_configured", None)
    data["model"] = DeviceModel(data.get("model", DeviceModel.DWARF_3))
    data["camera"] = Camera(data.get("camera", Camera.TELE))
    try:
        data["wifi_mode"] = WifiMode(str(data.get("wifi_mode") or WifiMode.AUTO).lower())
    except ValueError:
        data["wifi_mode"] = WifiMode.AUTO
    data["hardware"] = hardware_from_dict(data.get("hardware", {}))
    data["location_configured"] = has_site_coordinates(data.get("latitude"), data.get("longitude"))
    allowed = set(Device.__dataclass_fields__)
    return Device(**{key: value for key, value in data.items() if key in allowed})


def target_from_dict(data: dict[str, Any]) -> Target:
    data = dict(data)
    data["kind"] = TargetKind(data.get("kind", TargetKind.EQUATORIAL))
    return Target(**data)


def firmware_binning(value: Any) -> int:
    """Map stored 1=4K / 2=2K onto firmware 0=4K / 1=2K."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 1
    return 1 if n >= 2 else 0


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
    allowed = set(HistoryRecord.__dataclass_fields__)
    return HistoryRecord(**{key: value for key, value in data.items() if key in allowed})
