from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from fractions import Fraction
from html import unescape
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote, unquote
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


def album_http_path(path: str) -> str:
    value = str(path or "").strip().replace("\\", "/")
    if value.startswith("/sdcard/"):
        value = value[7:]
    elif value.startswith("/sdcard"):
        value = value[7:] or "/"
    if value and not value.startswith("/"):
        value = "/" + value
    return value


def album_http_url(ip: str, path: str) -> str:
    host = str(ip or "").strip()
    value = album_http_path(path)
    if not host or not value:
        return ""
    encoded = "/".join(quote(part, safe="") for part in value.split("/"))
    return f"http://{host}{encoded}"


def device_name_model(name: str) -> str:
    token = str(name or "").upper().replace(" ", "").replace("-", "_")
    if token.startswith("DWARF3"):
        return DeviceModel.DWARF_3
    if "MINI" in token or token.startswith("DWARF5"):
        return DeviceModel.DWARF_MINI
    if token.startswith("DWARF2") or token.startswith("DWARFII") or token.startswith("DWARF_II"):
        return DeviceModel.DWARF_II
    return ""


def album_path_matches_model(path: str, model: DeviceModel | str) -> bool:
    text = album_http_path(path).upper()
    if not text:
        return False
    has_dwarf3 = "DWARF3" in text
    has_mini = "DWARF_MINI" in text or "DWARFMINI" in text
    has_ii = "DWARF_II" in text or "DWARF2" in text or "DWARFII" in text
    has_generic = "/DWARF/" in text
    if not (has_dwarf3 or has_mini or has_ii or has_generic):
        return True
    expected = str(model)
    if expected == DeviceModel.DWARF_3:
        return has_dwarf3
    if expected == DeviceModel.DWARF_MINI:
        return has_mini
    if expected == DeviceModel.DWARF_II:
        return (has_ii or has_generic) and not has_dwarf3 and not has_mini
    return True


ASTRO_MEDIA_TYPE = 6
BURST_MEDIA_TYPE = 3
PANORAMA_MEDIA_TYPE = 5
ALBUM_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}
ALBUM_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".fits", ".fit"}
LOCAL_ALBUM_SUFFIXES = ALBUM_IMAGE_SUFFIXES | ALBUM_VIDEO_SUFFIXES
_ALBUM_HREF = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)
_SESSION_PREVIEW_TYPES = {BURST_MEDIA_TYPE, PANORAMA_MEDIA_TYPE}
_SESSION_THUMB_NAMES = ("burst_thumbnail.jpg", "pano_thumbnail.jpg", "panorama_thumbnail.jpg")
_ASTRO_PATH_MARKERS = (
    "/ASTRONOMY/",
    "DWARF_RAW",
    "/RESTACKED",
    "STARTRAIL",
    "SOLVING_FAILED",
    "CALI_FRAME",
)


def album_model_prefix(model: DeviceModel | str) -> str:
    expected = str(model)
    if expected == DeviceModel.DWARF_3:
        return "/DWARF3"
    if expected == DeviceModel.DWARF_MINI:
        return "/DWARF_MINI"
    if expected == DeviceModel.DWARF_II:
        return "/DWARF_II"
    return ""


def album_prefixed_path(path: str, model: DeviceModel | str = "") -> str:
    value = album_http_path(path)
    prefix = album_model_prefix(model)
    if not value or not prefix:
        return value
    text = value.upper()
    if "DWARF3" in text or "DWARF_MINI" in text or "DWARFMINI" in text or "DWARF_II" in text or "DWARF2" in text:
        return value
    return prefix + value


def album_entry_key(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("filePath") or entry.get("thumbnailPath") or entry.get("fileName") or "").strip()


def _album_suffix(path: str = "", name: str = "") -> str:
    text = str(name or path or "").replace("\\", "/")
    return PurePosixPath(text).suffix.lower()


def album_is_video_name(path: str = "", name: str = "") -> bool:
    return _album_suffix(path, name) in ALBUM_VIDEO_SUFFIXES


def album_is_astro_media(path: str = "", name: str = "", media_type: Any = None) -> bool:
    try:
        if int(media_type) == ASTRO_MEDIA_TYPE:
            return True
    except (TypeError, ValueError):
        pass
    text = f"{album_http_path(path)}/{name}".upper().replace("\\", "/")
    return any(marker in text for marker in _ASTRO_PATH_MARKERS)


def album_media_kind(path: str = "", name: str = "", media_type: Any = None) -> str:
    combined = album_http_path(path or name)
    text = combined.upper()
    file_name = str(name or PurePosixPath(combined).name)
    suffix = _album_suffix(combined, file_name)
    if album_is_astro_media(path, name, media_type):
        return "video" if suffix in ALBUM_VIDEO_SUFFIXES else "astro"
    try:
        kind_type = int(media_type)
    except (TypeError, ValueError):
        kind_type = -1
    if kind_type == BURST_MEDIA_TYPE or "/BURST" in text:
        return "burst"
    if kind_type == PANORAMA_MEDIA_TYPE or "PANORAMA" in text:
        return "panorama"
    if "/VIDEO" in text or suffix in ALBUM_VIDEO_SUFFIXES:
        return "video"
    return "photo"


def album_needs_preview_check(path: str = "", name: str = "", media_type: Any = None) -> bool:
    if album_media_kind(path, name, media_type) in {"burst", "panorama"}:
        return True
    try:
        if int(media_type) in _SESSION_PREVIEW_TYPES:
            return True
    except (TypeError, ValueError):
        pass
    return PurePosixPath(album_http_path(path)).name.lower() in _SESSION_THUMB_NAMES


def album_session_dir(path: str) -> str:
    value = album_http_path(path)
    if not value:
        return ""
    posix = PurePosixPath(value)
    if posix.suffix.lower() in LOCAL_ALBUM_SUFFIXES:
        return str(posix.parent)
    return str(posix).rstrip("/")


def album_join_path(folder: str, name: str) -> str:
    directory = album_http_path(folder).rstrip("/")
    file_name = str(name or "").replace("\\", "/").split("/")[-1]
    if not directory or not file_name:
        return directory or album_http_path(file_name)
    return f"{directory}/{file_name}"


def album_listing_names(html_text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in _ALBUM_HREF.finditer(str(html_text or "")):
        href = unescape(unquote(match.group(1))).replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
        if not href or href.endswith("/") or href in {".", "./", "..", "../"}:
            continue
        name = PurePosixPath(href).name
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def album_preview_name(names: list[str] | None) -> str:
    files = [str(name) for name in (names or []) if str(name).strip()]
    lookup = {name.lower(): name for name in files}
    for preferred in (*_SESSION_THUMB_NAMES, "0.jpg"):
        if preferred in lookup:
            return lookup[preferred]
    for name in files:
        if PurePosixPath(name).suffix.lower() in ALBUM_IMAGE_SUFFIXES:
            return name
    return ""


def album_apply_listing_preview(entry: dict[str, Any], names: list[str]) -> dict[str, Any]:
    out = dict(entry)
    remote = str(out.get("filePath") or "").strip()
    thumb = str(out.get("thumbnailPath") or "").strip()
    folder = album_session_dir(thumb or remote)
    preview = album_preview_name(names)
    out["thumbnailPath"] = album_join_path(folder, preview) if preview else ""
    remote_name = PurePosixPath(album_http_path(remote)).name.lower()
    listed = {name.lower() for name in names}
    out["fileAvailable"] = bool(remote_name and remote_name in listed)
    return out


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


DEFAULT_STELLARIUM_URL = "http://localhost:8090"
DEFAULT_OBSERVING_DAY_CUTOFF_HOUR = 12
DEFAULT_EXPOSURE_SECONDS = 15.0
DEFAULT_GAIN = 40
DEFAULT_FRAME_COUNT = 60


@dataclass(slots=True)
class AppSettings:
    observing_day_cutoff_hour: int = DEFAULT_OBSERVING_DAY_CUTOFF_HOUR
    stellarium_url: str = DEFAULT_STELLARIUM_URL


@dataclass(slots=True)
class CaptureDefaults:
    exposure_seconds: float = DEFAULT_EXPOSURE_SECONDS
    gain: int = DEFAULT_GAIN
    frame_count: int = DEFAULT_FRAME_COUNT


@dataclass(slots=True)
class Device:
    name: str
    model: DeviceModel = DeviceModel.DWARF_3
    id: str = field(default_factory=new_id)
    ip_address: str = "192.168.88.1"
    camera: Camera = Camera.TELE
    color: str = "#6C8CFF"
    hardware: HardwareProfile = field(default_factory=HardwareProfile)
    capture_defaults: CaptureDefaults = field(default_factory=CaptureDefaults)
    ble_enabled: bool = True
    ble_password: str = "DWARF_12345678"
    wifi_mode: WifiMode = WifiMode.AUTO
    wifi_ssid: str = ""
    wifi_password: str = ""
    latitude: float = 0
    longitude: float = 0
    timezone_name: str = "UTC"
    location_configured: bool = False
    stellarium_url: str = DEFAULT_STELLARIUM_URL
    observing_day_cutoff_hour: int = DEFAULT_OBSERVING_DAY_CUTOFF_HOUR


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
    exposure_seconds: float = DEFAULT_EXPOSURE_SECONDS
    gain: int = DEFAULT_GAIN
    frame_count: int = DEFAULT_FRAME_COUNT
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
    exposure_seconds: float | None = None
    mosaic_panes: int = 1
    workflow: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, float] = field(default_factory=dict)
    step_seconds: dict[str, float] = field(default_factory=dict)


def to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)


def clamp_cutoff_hour(value: Any, default: int = DEFAULT_OBSERVING_DAY_CUTOFF_HOUR) -> int:
    try:
        hour = int(value)
    except (TypeError, ValueError):
        hour = default
    return max(0, min(23, hour))


def normalized_stellarium_url(value: Any, default: str = DEFAULT_STELLARIUM_URL) -> str:
    text = str(value or "").strip()
    return text or default


def app_settings_from_dict(data: dict[str, Any]) -> AppSettings:
    data = dict(data or {})
    return AppSettings(
        observing_day_cutoff_hour=clamp_cutoff_hour(data.get("observing_day_cutoff_hour")),
        stellarium_url=normalized_stellarium_url(data.get("stellarium_url")),
    )


def hardware_from_dict(data: dict[str, Any]) -> HardwareProfile:
    allowed = set(HardwareProfile.__dataclass_fields__)
    cleaned = {key: value for key, value in dict(data or {}).items() if key in allowed}
    return HardwareProfile(**cleaned)


def _positive_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _int_at_least(value: Any, default: int, minimum: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return number if number >= minimum else default


def capture_defaults_from_dict(data: dict[str, Any]) -> CaptureDefaults:
    raw = dict(data) if isinstance(data, dict) else {}
    return CaptureDefaults(
        exposure_seconds=_positive_float(raw.get("exposure_seconds"), DEFAULT_EXPOSURE_SECONDS),
        gain=_int_at_least(raw.get("gain"), DEFAULT_GAIN, 0),
        frame_count=_int_at_least(raw.get("frame_count"), DEFAULT_FRAME_COUNT, 1),
    )


def camera_settings_from_capture(
    defaults: CaptureDefaults | None = None,
    *,
    camera: Camera = Camera.TELE,
) -> CameraSettings:
    capture = defaults or CaptureDefaults()
    return CameraSettings(
        camera=camera,
        exposure_seconds=float(capture.exposure_seconds),
        gain=int(capture.gain),
        frame_count=int(capture.frame_count),
    )


def resolved_frame_count(value: Any, defaults: CaptureDefaults | None = None) -> int:
    """Use an explicit stack count when valid, otherwise the capture default."""
    capture = defaults or CaptureDefaults()
    return _int_at_least(value, int(capture.frame_count), 1)


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
    data["capture_defaults"] = capture_defaults_from_dict(data.get("capture_defaults", {}))
    data["location_configured"] = has_site_coordinates(data.get("latitude"), data.get("longitude"))
    data["observing_day_cutoff_hour"] = clamp_cutoff_hour(data.get("observing_day_cutoff_hour"))
    data["stellarium_url"] = normalized_stellarium_url(data.get("stellarium_url"))
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


# Names from the Dwarf 3 / Mini exposure tables (astro_dwarf_session dropdowns).
# perform_set_astro_exposure_by_name_v3 matches these strings exactly.
_EXPOSURE_NAMES = (
    "1/10000", "1/8000", "1/6400", "1/5000", "1/4000", "1/3200", "1/2500",
    "1/2000", "1/1600", "1/1250", "1/1000", "1/800", "1/640", "1/500", "1/400",
    "1/320", "1/250", "1/200", "1/160", "1/125", "1/100", "1/80", "1/60",
    "1/50", "1/40", "1/30", "1/25", "1/20", "1/15", "1/13", "1/10", "1/8",
    "1/6", "1/5", "1/4", "1/3", "0.4", "0.5", "0.6", "0.8", "1", "1.3", "1.6",
    "2", "2.5", "3.2", "4", "5", "6", "8", "10", "13", "15", "30", "45", "60",
    "90", "120", "180",
)


def _exposure_seconds(name: str) -> float:
    if "/" in name:
        return float(Fraction(name))
    return float(name)


def firmware_exposure_name(value: Any) -> str:
    """Map stored seconds (15.0) onto the SDK table name ("15").

    astro_dwarf_session stores the dropdown string and passes it straight to
    perform_set_astro_exposure_by_name_v3. str(15.0) is "15.0", which misses
    "15" and silently falls back to 1/30s.
    """
    text = str(value).strip()
    if not text:
        return "15"
    if text in _EXPOSURE_NAMES:
        return text
    try:
        seconds = float(Fraction(text)) if "/" in text else float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return text
    return min(_EXPOSURE_NAMES, key=lambda name: abs(_exposure_seconds(name) - seconds))


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


def _float_map(data: Any) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in dict(data or {}).items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def history_from_dict(data: dict[str, Any]) -> HistoryRecord:
    data = dict(data)
    data["workflow"] = dict(data.get("workflow") or {})
    data["hardware"] = _float_map(data.get("hardware"))
    data["step_seconds"] = _float_map(data.get("step_seconds"))
    try:
        data["mosaic_panes"] = max(1, int(data.get("mosaic_panes") or 1))
    except (TypeError, ValueError):
        data["mosaic_panes"] = 1
    allowed = set(HistoryRecord.__dataclass_fields__)
    return HistoryRecord(**{key: value for key, value in data.items() if key in allowed})


def history_record_for_run(
    session: Session,
    *,
    actual_duration_seconds: float,
    captured_frame_count: int,
    hardware: HardwareProfile | None = None,
    step_seconds: dict[str, float] | None = None,
) -> HistoryRecord:
    captured = int(captured_frame_count)
    planned_frames = int(session.camera.frame_count or 0)
    return HistoryRecord(
        session_id=session.id,
        device_id=session.device_id,
        target_name=session.target.name,
        scheduled_start=session.scheduled_start,
        actual_started_at=session.actual_started_at,
        actual_ended_at=session.actual_ended_at,
        planned_duration_seconds=session.planned_duration_seconds,
        actual_duration_seconds=actual_duration_seconds,
        frame_count=planned_frames,
        captured_frame_count=captured,
        outcome=session.outcome,
        summary=f"{captured}/{planned_frames} frames · {session.camera.exposure_seconds:g}s",
        notes=session.notes,
        exposure_seconds=float(session.camera.exposure_seconds),
        mosaic_panes=int(session.mosaic.panes),
        workflow=asdict(session.workflow),
        hardware={
            key: float(getattr(hardware, key))
            for key in HardwareProfile.__dataclass_fields__
        } if hardware is not None else {},
        step_seconds={key: round(float(value), 1) for key, value in dict(step_seconds or {}).items()},
    )
