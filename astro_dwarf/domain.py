from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from fractions import Fraction
from html import unescape
from pathlib import Path, PurePosixPath
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


def default_device_name(existing_count: int) -> str:
    try:
        count = int(existing_count)
    except (TypeError, ValueError):
        count = 0
    return f"DWARF #{max(count, 0) + 1}"


def is_first_device_setup(devices: list[Any]) -> bool:
    if len(devices) != 1:
        return False
    device = devices[0]
    if isinstance(device, dict):
        return not bool(device.get("location_configured"))
    return not bool(getattr(device, "location_configured", False))


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


PHOTO_MEDIA_TYPE = 1
VIDEO_MEDIA_TYPE = 2
BURST_MEDIA_TYPE = 3
ASTRO_MEDIA_TYPE = 4
PANORAMA_MEDIA_TYPE = 5
ASTRO_LIST_MEDIA_TYPE = 6
_ALBUM_CANONICAL_MEDIA_TYPES = {
    PHOTO_MEDIA_TYPE,
    VIDEO_MEDIA_TYPE,
    BURST_MEDIA_TYPE,
    ASTRO_MEDIA_TYPE,
    PANORAMA_MEDIA_TYPE,
}
_ASTRO_MEDIA_TYPES = {ASTRO_MEDIA_TYPE, ASTRO_LIST_MEDIA_TYPE}
ALBUM_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}
ALBUM_FITS_SUFFIXES = {".fits", ".fit", ".fts"}
ALBUM_TIFF_SUFFIXES = {".tif", ".tiff"}
ALBUM_HEAVY_PREVIEW_SUFFIXES = ALBUM_FITS_SUFFIXES | ALBUM_TIFF_SUFFIXES
ALBUM_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"} | ALBUM_HEAVY_PREVIEW_SUFFIXES
ALBUM_STACK_DISPLAY_SUFFIXES = {".jpg", ".jpeg", ".png"}
LOCAL_ALBUM_SUFFIXES = ALBUM_IMAGE_SUFFIXES | ALBUM_VIDEO_SUFFIXES
_ALBUM_CATEGORY_NAMES = {
    "astronomy",
    "astro",
    "burst",
    "bursts",
    "normal photos",
    "normal_photos",
    "panorama",
    "panoramas",
    "photos",
    "video",
    "videos",
}
_ALBUM_SKIP_DIR_NAMES = {
    "system volume information",
    "thumbnail",
    "thumbnails",
}
_ALBUM_INDEX_ROW = re.compile(
    r"""<a href=["']([^"']+)["']>[^<]*</a>(?:\s+(\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}))?""",
    re.IGNORECASE,
)
_ALBUM_LISTING_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_STACK_JPEG_NAMES = ("stacked.jpg", "stacked.jpeg")
_STACK_THUMB_NAMES = ("stacked_thumbnail.jpg", "stacked_thumbnail.jpeg")
_STACK_COUNTER_NAMES = ("img_stacked_counter.png",)
_STACK_RESULT_SKEW_S = 15
_SESSION_PREVIEW_TYPES = {BURST_MEDIA_TYPE, PANORAMA_MEDIA_TYPE}
_SESSION_THUMB_NAMES = ("burst_thumbnail.jpg", "pano_thumbnail.jpg", "panorama_thumbnail.jpg")
_THUMBNAIL_DIR_NAMES = frozenset(_ALBUM_SKIP_DIR_NAMES & {"thumbnail", "thumbnails"})
_ASTRO_PATH_MARKERS = (
    "/ASTRONOMY/",
    "DWARF_RAW",
    "/RESTACKED",
    "STARTRAIL",
    "SOLVING_FAILED",
    "CALI_FRAME",
)


ALBUM_NO_FOLDER_INDEX = (
    "This telescope lists sessions from its album and does not publish a folder index, "
    "so frames inside a session are not browsable here."
)
_ALBUM_TYPE_FOLDERS = {
    PHOTO_MEDIA_TYPE: "Normal_Photos",
    VIDEO_MEDIA_TYPE: "Videos",
    BURST_MEDIA_TYPE: "Burst",
    ASTRO_MEDIA_TYPE: "Astronomy",
    PANORAMA_MEDIA_TYPE: "Panorama",
    ASTRO_LIST_MEDIA_TYPE: "Astronomy",
}


def album_model_prefix_candidates(model: DeviceModel | str) -> tuple[str, ...]:
    """Fallback HTTP roots when the album API has not reported a path yet."""
    expected = str(model)
    if expected == DeviceModel.DWARF_3:
        return ("/DWARF3",)
    if expected == DeviceModel.DWARF_MINI:
        return ("/DWARF_mini", "/DWARF_MINI")
    if expected == DeviceModel.DWARF_II:
        return ("/DWARF_II",)
    return ()


def album_model_prefix(model: DeviceModel | str) -> str:
    candidates = album_model_prefix_candidates(model)
    return candidates[0] if candidates else ""


def album_is_model_segment(name: str) -> bool:
    token = str(name or "").upper().replace("-", "_")
    return token in {
        "DWARF3",
        "DWARF_3",
        "DWARF_MINI",
        "DWARFMINI",
        "DWARF_II",
        "DWARFII",
        "DWARF2",
        "DWARF_2",
    }


def album_root_from_path(path: str) -> str:
    """Model folder spelled the way the device wrote it, such as /DWARF_mini."""
    for part in album_http_path(path).split("/"):
        if part and album_is_model_segment(part):
            return "/" + part
    return ""


def album_root_from_entries(entries: list[dict[str, Any]] | None) -> str:
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        for key in ("filePath", "thumbnailPath"):
            root = album_root_from_path(str(entry.get(key) or ""))
            if root:
                return root
    return ""


def album_prefixed_path(path: str, model: DeviceModel | str = "") -> str:
    value = album_http_path(path)
    prefix = album_model_prefix(model)
    if not value or not prefix:
        return value
    if album_root_from_path(value):
        return value
    return prefix + value


def album_entry_key(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("filePath") or entry.get("thumbnailPath") or entry.get("fileName") or "").strip()


def album_is_astro_type(media_type: Any) -> bool:
    try:
        return int(media_type) in _ASTRO_MEDIA_TYPES
    except (TypeError, ValueError):
        return False


def album_canonical_media_type(
    path: str = "",
    name: str = "",
    media_type: Any = None,
    is_dir: bool = False,
) -> int:
    """Firmware album item type. 0 and list-filter 6 are ignored by /album/delete."""
    try:
        current = int(media_type)
    except (TypeError, ValueError):
        current = 0
    if current == ASTRO_LIST_MEDIA_TYPE:
        current = ASTRO_MEDIA_TYPE
    if current in _ALBUM_CANONICAL_MEDIA_TYPES:
        return current
    text = album_http_path(path or name).upper()
    if album_is_astro_media(path, name, media_type):
        return ASTRO_MEDIA_TYPE
    if "/BURST" in text:
        return BURST_MEDIA_TYPE
    if "PANORAMA" in text:
        return PANORAMA_MEDIA_TYPE
    suffix = _album_suffix(path, name)
    if "/VIDEO" in text or (not is_dir and suffix in ALBUM_VIDEO_SUFFIXES):
        return VIDEO_MEDIA_TYPE
    return PHOTO_MEDIA_TYPE


def album_is_category_folder_path(path: str = "", name: str = "") -> bool:
    """True for an album category directory, not a file or session inside one.

    Firmware photo rows often set fileName to the category (Normal_Photos,
    Astronomy). Decide from the path itself so a session is not skipped and
    the category folder is never sent to /album/delete.
    """
    remote = album_http_path(path).rstrip("/")
    if not remote or _album_suffix(remote) in LOCAL_ALBUM_SUFFIXES:
        return False
    folder = PurePosixPath(remote).name
    return album_is_category_name(folder) or album_is_skip_dir(folder)


def _album_session_delete_file(path: str, file_name: str) -> str:
    remote = album_http_path(path)
    session = album_session_dir(remote)
    label = PurePosixPath(session).name if session else ""
    if not session or album_is_category_name(label) or album_is_skip_dir(label):
        return remote
    if _album_suffix(remote) in LOCAL_ALBUM_SUFFIXES:
        return remote
    return album_join_path(session, file_name) or remote


def album_delete_remote_path(path: str, media_type: int) -> str:
    remote = album_http_path(path)
    if media_type == ASTRO_MEDIA_TYPE:
        session = album_session_dir(remote)
        if not session or not album_is_astro_session_folder(session):
            return remote
        return album_join_path(session, _STACK_JPEG_NAMES[0]) or remote
    if media_type == BURST_MEDIA_TYPE:
        return _album_session_delete_file(remote, "0.jpg")
    if media_type == PANORAMA_MEDIA_TYPE:
        return _album_session_delete_file(remote, "pano_thumbnail.jpg")
    return remote


def album_delete_remote_name(path: str, name: str, media_type: int) -> str:
    remote = album_http_path(path)
    label = str(name or "").strip()
    parts = [part for part in remote.replace("\\", "/").split("/") if part]
    if media_type == PHOTO_MEDIA_TYPE:
        if album_is_category_name(label):
            return label
        if len(parts) >= 2 and album_is_category_name(parts[-2]):
            return parts[-2]
        return label or (parts[-1] if parts else "")
    if media_type == ASTRO_MEDIA_TYPE:
        session = album_session_dir(remote)
        session_name = PurePosixPath(session).name if session else ""
        if session_name and not album_is_category_name(session_name):
            return session_name
        if label and not album_is_category_name(label):
            return label
    if label and not album_is_category_name(label):
        return label
    if not label:
        return parts[-2] if len(parts) >= 2 else (parts[-1] if parts else "")
    return label


def album_delete_payload(items: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Firmware album delete body. A bare array is ignored; wrap in `datas`."""
    datas: list[dict[str, Any]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("filePath") or item.get("file_path") or "").strip()
        if not file_path:
            continue
        file_name = str(item.get("fileName") or item.get("file_name") or "").strip()
        try:
            media_type = int(item.get("mediaType", item.get("media_type", 0)) or 0)
        except (TypeError, ValueError):
            media_type = 0
        try:
            sub_type = int(item.get("subType", item.get("sub_type", 0)) or 0)
        except (TypeError, ValueError):
            sub_type = 0
        is_dir = item.get("isDir", item.get("is_dir")) is True
        media_type = album_canonical_media_type(file_path, file_name, media_type, is_dir)
        if album_is_category_folder_path(file_path, file_name):
            continue
        file_path = album_delete_remote_path(file_path, media_type)
        file_name = album_delete_remote_name(file_path, file_name, media_type)
        datas.append({
            "mediaType": media_type,
            "filePath": file_path,
            "fileName": file_name,
            "subType": sub_type,
        })
    return {"datas": datas}


def album_delete_entry_ok(entry: dict[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in ("isSuccess", "success", "is_success"):
        value = entry.get(key)
        if value is None:
            continue
        if value is True or value == 1:
            return True
        text = str(value).strip().lower()
        return text in {"true", "1", "ok"}
    return False


def album_delete_result_entries(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    data = result.get("data")
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, dict)]
    if isinstance(data, dict):
        for key in ("datas", "list", "items", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return [entry for entry in value if isinstance(entry, dict)]
        if any(key in data for key in ("isSuccess", "filePath", "fileName")):
            return [data]
    return []


def album_delete_outcome(result: Any, requested: int) -> dict[str, Any]:
    """Interpret firmware /album/delete JSON. code 0 means the body was accepted."""
    if not isinstance(result, dict):
        raise RuntimeError("Album delete failed")
    try:
        code = int(result.get("code"))
    except (TypeError, ValueError):
        code = -1
    if code != 0:
        detail = str(result.get("message") or result.get("msg") or result)
        raise RuntimeError(detail or "Album delete failed")
    entries = album_delete_result_entries(result)
    succeeded = [entry for entry in entries if album_delete_entry_ok(entry)]
    requested = max(0, int(requested or 0))
    failed = max(0, requested - len(succeeded))
    return {"deleted": succeeded, "failed": failed, "results": entries, "requested": requested}


def album_delete_summary(requested: int, remaining: int) -> tuple[str, str]:
    """Toast after re-listing. Firmware isSuccess is not proof the folders stayed."""
    wanted = max(0, int(requested or 0))
    left = max(0, int(remaining or 0))
    gone = max(0, wanted - left)
    if wanted <= 0:
        return ("Nothing to delete from the telescope", "warning")
    if left == 0:
        return (f"Deleted {gone} item{'s' if gone != 1 else ''} from telescope", "success")
    if gone:
        return (f"Deleted {gone}, {left} still on telescope", "warning")
    return ("Those items are still on the telescope", "error")


def album_local_file_in_dir(album_dir: Path | str, candidate: str) -> Path | None:
    folder = Path(album_dir).expanduser().resolve()
    text = str(candidate or "").strip()
    if not text:
        return None
    target = Path(text)
    if not target.is_absolute():
        target = folder / Path(text.replace("\\", "/")).name
    try:
        resolved = target.expanduser().resolve()
        resolved.relative_to(folder)
    except (OSError, ValueError):
        return None
    if not resolved.is_file() or resolved.suffix.lower() not in LOCAL_ALBUM_SUFFIXES:
        return None
    return resolved


def _album_suffix(path: str = "", name: str = "") -> str:
    text = str(name or path or "").replace("\\", "/")
    return PurePosixPath(text).suffix.lower()


def album_is_video_name(path: str = "", name: str = "") -> bool:
    return _album_suffix(path, name) in ALBUM_VIDEO_SUFFIXES


def album_is_fits_name(path: str = "", name: str = "") -> bool:
    return _album_suffix(path, name) in ALBUM_FITS_SUFFIXES


def album_is_heavy_preview(path: str = "", name: str = "") -> bool:
    """TIFF/FITS are too large to decode as grid thumbnails."""
    return _album_suffix(path, name) in ALBUM_HEAVY_PREVIEW_SUFFIXES


def album_is_category_name(name: str = "") -> bool:
    token = str(name or "").strip().lower().replace("-", "_")
    token = " ".join(token.split())
    return token in _ALBUM_CATEGORY_NAMES or token.replace(" ", "_") in _ALBUM_CATEGORY_NAMES


def album_display_name(path: str = "", name: str = "") -> str:
    """Prefer the real file when firmware fileName is an album category like Videos."""
    remote_name = PurePosixPath(album_http_path(path)).name
    label = str(name or "").strip()
    if album_is_category_name(label):
        return remote_name or label
    return label or remote_name


def album_is_media_file(path: str = "", name: str = "") -> bool:
    return _album_suffix(path, name) in LOCAL_ALBUM_SUFFIXES


def album_is_skip_dir(name: str = "") -> bool:
    token = str(name or "").strip().lower()
    return not token or token in {".", ".."} or token in _ALBUM_SKIP_DIR_NAMES


def album_folder_root(model: DeviceModel | str = "", resolved: str = "") -> str:
    found = album_root_from_path(resolved)
    if found:
        return found
    return album_model_prefix(model) or "/DWARF3"


def album_path_in_root(path: str, root: str) -> bool:
    value = album_http_path(path).rstrip("/")
    base = album_http_path(root).rstrip("/")
    if not value or not base:
        return False
    folded = value.upper()
    prefix = base.upper()
    return folded == prefix or folded.startswith(prefix + "/")


def album_folder_parent(path: str, root: str = "") -> str:
    current = album_http_path(path).rstrip("/")
    base = album_http_path(root).rstrip("/")
    if not current or current == base:
        return ""
    parent = str(PurePosixPath(current).parent).replace("\\", "/")
    if parent in {".", "/"}:
        return ""
    if base and not (parent == base or parent.startswith(base + "/")):
        return ""
    return parent


def album_is_protected_folder(path: str = "", name: str = "") -> bool:
    label = str(name or PurePosixPath(album_http_path(path)).name).strip()
    return album_is_category_name(label) or album_is_skip_dir(label)


def album_is_astro_session_folder(path: str = "", name: str = "") -> bool:
    """True for an astronomy session directory, not the Astronomy category itself."""
    directory = album_http_path(path).rstrip("/")
    label = str(name or PurePosixPath(directory).name).strip()
    if not directory or album_is_category_name(label) or album_is_skip_dir(label):
        return False
    return album_is_astro_media(directory, label)


def album_is_astronomy_category_folder(path: str = "", name: str = "") -> bool:
    """True for the Astronomy album category, not a session inside it."""
    label = str(name or PurePosixPath(album_http_path(path).rstrip("/")).name).strip()
    if not album_is_category_name(label):
        return False
    token = label.lower().replace("-", "_").replace(" ", "")
    return token in {"astronomy", "astro"}


def album_is_thumbnail_dir_name(name: str = "") -> bool:
    return str(name or "").strip().lower() in _THUMBNAIL_DIR_NAMES


def album_is_inside_thumbnail_dir(path: str = "") -> bool:
    return any(album_is_thumbnail_dir_name(part) for part in PurePosixPath(album_http_path(path)).parts)


def album_is_astro_stack_product(path: str = "", name: str = "") -> bool:
    """True for stacked.jpg, stacked-16_*.png/.fits, img_reference.png, and similar."""
    token = str(name or PurePosixPath(album_http_path(path)).name).strip().lower()
    if not token:
        return False
    if token in {item.lower() for item in (*_STACK_JPEG_NAMES, *_STACK_THUMB_NAMES, *_STACK_COUNTER_NAMES)}:
        return True
    if token == "img_reference.png":
        return True
    stem = PurePosixPath(token).stem
    return stem == "stacked" or token.startswith("stacked-")


def album_folder_preview_path(folder: str) -> str:
    """Astronomy session folders keep stacked_thumbnail.jpg at the session root."""
    directory = album_http_path(folder).rstrip("/")
    if album_is_inside_thumbnail_dir(directory):
        directory = album_session_dir(directory)
    if not album_is_astro_session_folder(directory):
        return ""
    return album_join_path(directory, _STACK_THUMB_NAMES[0])


def album_folder_preview_fallback_path(folder: str) -> str:
    """Full stacked.jpg used when the session thumbnail is missing."""
    directory = album_http_path(folder).rstrip("/")
    if album_is_inside_thumbnail_dir(directory):
        directory = album_session_dir(directory)
    if not album_is_astro_session_folder(directory):
        return ""
    return album_join_path(directory, _STACK_JPEG_NAMES[0])


def album_item_preview_path(folder: str, name: str, *, is_dir: bool = False) -> str:
    """Grid thumbnail for a folder listing row.

    Astronomy stack products live at the session root. The grid uses
    stacked_thumbnail.jpg, not Thumbnail/<same name> — that folder only holds
    JPEG sidecars for the individual TIFF/FITS frames. Photo stills keep the
    firmware Thumbnail/ sidecar with the same file name.
    """
    directory = album_http_path(folder).rstrip("/")
    file_name = str(name or "").replace("\\", "/").split("/")[-1]
    remote = album_join_path(directory, file_name) if file_name else directory
    if is_dir:
        return album_folder_preview_path(remote)
    if not file_name:
        return ""
    if album_is_inside_thumbnail_dir(directory):
        directory = album_session_dir(directory)
        remote = album_join_path(directory, file_name) if file_name else directory
    astro = album_is_astro_media(remote, file_name)
    if astro and album_is_astro_stack_product(remote, file_name):
        lower = file_name.lower()
        if lower in {item.lower() for item in (*_STACK_THUMB_NAMES, *_STACK_COUNTER_NAMES)}:
            return remote
        return album_folder_preview_path(directory) or (
            remote if album_is_stack_display_image(file_name) else ""
        )
    if album_is_stack_display_image(file_name):
        if astro:
            return album_folder_preview_path(directory) or remote
        return album_sidecar_thumbnail_path(directory, file_name)
    if astro and album_is_heavy_preview(file_name):
        return album_frame_sidecar_path(directory, file_name) or album_folder_preview_path(directory)
    return ""


def album_entry_preview_path(entry: dict[str, Any] | None, folder: str = "") -> str:
    """Preview path for a firmware album row or HTTP folder listing entry."""
    if not isinstance(entry, dict):
        return ""
    name = str(entry.get("fileName") or "").strip()
    remote = str(entry.get("filePath") or "").strip()
    is_dir = entry.get("isDir") is True
    session = album_session_dir(remote or name or folder)
    if is_dir or (
        not album_is_media_file("", name)
        and not album_is_media_file("", PurePosixPath(album_http_path(remote)).name)
        and album_is_astro_session_folder(session or remote, name)
    ):
        return album_folder_preview_path(remote if is_dir else (session or remote or name))
    file_name = PurePosixPath(album_http_path(remote)).name
    if album_is_media_file("", name):
        label = name
    elif album_is_media_file("", file_name):
        label = file_name
    else:
        label = name or file_name
    return album_item_preview_path(session or folder, label)


def album_sidecar_thumbnail_path(folder: str, name: str) -> str:
    """Firmware photo thumbs live in Thumbnail/ with the same JPEG/PNG name."""
    file_name = str(name or "").replace("\\", "/").split("/")[-1]
    if not album_is_stack_display_image(file_name):
        return ""
    directory = album_http_path(folder).rstrip("/")
    if not directory or not file_name:
        return ""
    if album_is_inside_thumbnail_dir(directory):
        directory = album_session_dir(directory)
    return album_join_path(f"{directory}/Thumbnail", file_name)


def album_frame_sidecar_path(folder: str, name: str) -> str:
    """Astro TIFF/FITS frames have JPEG thumbs in Thumbnail/ with a .jpg suffix."""
    file_name = str(name or "").replace("\\", "/").split("/")[-1]
    if not album_is_heavy_preview(file_name):
        return ""
    directory = album_http_path(folder).rstrip("/")
    stem = PurePosixPath(file_name).stem
    if not directory or not stem:
        return ""
    if album_is_inside_thumbnail_dir(directory):
        directory = album_session_dir(directory)
    return album_join_path(f"{directory}/Thumbnail", f"{stem}.jpg")


def album_listing_mtime(stamp: str = "") -> int:
    text = str(stamp or "").strip()
    if not text:
        return 0
    try:
        day_s, mon_s, rest = text.replace("-", " ").split(None, 2)
        year_s, clock = rest.split()
        hour_s, minute_s = clock.split(":")
        month = _ALBUM_LISTING_MONTHS.get(mon_s[:3].lower(), 0)
        year = int(year_s)
        if not month or year >= 2038:
            return 0
        return int(datetime(year, month, int(day_s), int(hour_s), int(minute_s)).timestamp())
    except (TypeError, ValueError):
        return 0


def album_is_astro_media(path: str = "", name: str = "", media_type: Any = None) -> bool:
    if album_is_astro_type(media_type):
        return True
    text = f"{album_http_path(path)}/{name}".upper().replace("\\", "/")
    return any(marker in text for marker in _ASTRO_PATH_MARKERS)


def album_media_kind(path: str = "", name: str = "", media_type: Any = None) -> str:
    combined = album_http_path(path or name)
    text = combined.upper()
    file_name = str(name or PurePosixPath(combined).name)
    suffix = _album_suffix(combined, file_name)
    path_suffix = _album_suffix(combined)
    if album_is_category_name(file_name) and path_suffix not in LOCAL_ALBUM_SUFFIXES:
        return "folder"
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
    if kind_type == VIDEO_MEDIA_TYPE or "/VIDEO" in text or suffix in ALBUM_VIDEO_SUFFIXES:
        return "video"
    return "photo"


def album_needs_preview_check(path: str = "", name: str = "", media_type: Any = None) -> bool:
    if album_media_kind(path, name, media_type) in {"burst", "panorama", "astro"}:
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
        posix = posix.parent
    if album_is_thumbnail_dir_name(posix.name):
        posix = posix.parent
    text = str(posix).rstrip("/")
    return "" if text in {".", "/"} else text


def album_join_path(folder: str, name: str) -> str:
    directory = album_http_path(folder).rstrip("/")
    file_name = str(name or "").replace("\\", "/").split("/")[-1]
    if not directory or not file_name:
        return directory or album_http_path(file_name)
    return f"{directory}/{file_name}"


def album_listing_entries(html_text: str) -> list[dict[str, Any]]:
    """Parse an HTTP directory index into files and folders."""
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _ALBUM_INDEX_ROW.finditer(str(html_text or "")):
        href = unescape(unquote(match.group(1))).replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
        if not href or href in {".", "./", "..", "../"}:
            continue
        is_dir = href.endswith("/")
        name = PurePosixPath(href.rstrip("/")).name
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        entries.append({
            "name": name,
            "is_dir": is_dir,
            "modification_time": album_listing_mtime(match.group(2) if match.lastindex and match.lastindex >= 2 else ""),
        })
    return entries


def _album_category_of(path: str, media_type: Any = None) -> tuple[str, str]:
    remote = album_http_path(path)
    parts = [part for part in remote.split("/") if part]
    for index, part in enumerate(parts):
        if album_is_category_name(part):
            return part, "/" + "/".join(parts[: index + 1])
    try:
        kind = int(media_type)
    except (TypeError, ValueError):
        kind = 0
    name = _ALBUM_TYPE_FOLDERS.get(kind, "")
    root = album_root_from_path(remote)
    if name and root:
        return name, album_join_path(root, name)
    return "", ""


def _album_api_row(
    name: str,
    remote: str,
    *,
    is_dir: bool,
    media_type: int,
    thumb: str = "",
    modified: int = 0,
) -> dict[str, Any]:
    return {
        "fileName": name,
        "filePath": remote,
        "thumbnailPath": thumb,
        "mediaType": media_type,
        "modificationTime": modified,
        "isDir": is_dir,
        "fileAvailable": False,
        "previewResolved": False,
    }


def album_unindexed_listing(
    entries: list[dict[str, Any]] | None,
    folder: str,
    root: str,
) -> dict[str, Any]:
    """Album rows from firmware filePath values when nginx has no directory index."""
    requested = album_http_path(folder).rstrip("/") or album_http_path(root).rstrip("/")
    base = album_http_path(root).rstrip("/")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    at_root = requested.upper() == base.upper()
    in_session = album_is_astro_session_folder(requested) or (
        not at_root and not album_is_category_folder_path(requested)
    )
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        remote = album_http_path(str(entry.get("filePath") or entry.get("thumbnailPath") or ""))
        if not remote or not album_path_in_root(remote, base):
            continue
        try:
            media_type = int(entry.get("mediaType") or 0)
        except (TypeError, ValueError):
            media_type = 0
        try:
            modified = int(entry.get("modificationTime") or 0)
        except (TypeError, ValueError):
            modified = 0
        name = str(entry.get("fileName") or PurePosixPath(remote).name).strip()
        thumb = album_http_path(str(entry.get("thumbnailPath") or ""))
        if at_root:
            label, category = _album_category_of(remote, media_type)
            key = category.upper()
            if not label or not category or key in seen:
                continue
            seen.add(key)
            rows.append(_album_api_row(label, category, is_dir=True, media_type=media_type, modified=modified))
            continue
        session = album_session_dir(remote)
        if album_is_category_folder_path(requested) and not in_session:
            child = session if session and album_path_in_root(session, requested) and session.rstrip("/").upper() != requested.upper() else ""
            if child and PurePosixPath(child).parent.as_posix().rstrip("/").upper() == requested.upper():
                key = child.upper()
                if key in seen:
                    continue
                seen.add(key)
                child_name = name if name and not album_is_category_name(name) else PurePosixPath(child).name
                rows.append(_album_api_row(
                    child_name,
                    child,
                    is_dir=True,
                    media_type=media_type or ASTRO_MEDIA_TYPE,
                    thumb=thumb,
                    modified=modified,
                ))
                continue
            if album_is_media_file(remote) and PurePosixPath(remote).parent.as_posix().rstrip("/").upper() == requested.upper():
                key = remote.upper()
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_album_api_row(
                    PurePosixPath(remote).name,
                    remote,
                    is_dir=False,
                    media_type=media_type or PHOTO_MEDIA_TYPE,
                    thumb=thumb,
                    modified=modified,
                ))
            continue
        if not album_is_media_file(remote):
            continue
        if album_session_dir(remote).rstrip("/").upper() != requested.upper() and remote.rstrip("/").upper() != requested.upper():
            continue
        key = remote.upper()
        if key in seen:
            continue
        seen.add(key)
        rows.append(_album_api_row(
            PurePosixPath(remote).name,
            remote,
            is_dir=False,
            media_type=media_type or ASTRO_MEDIA_TYPE,
            thumb=thumb,
            modified=modified,
        ))
    notice = ""
    if in_session or not rows:
        notice = ALBUM_NO_FOLDER_INDEX
    return {
        "directory": requested,
        "parent": album_folder_parent(requested, base),
        "root": base,
        "sessions": rows,
        "notice": notice,
    }


def album_preview_name(names: list[str] | None) -> str:
    files = [str(name) for name in (names or []) if str(name).strip()]
    lookup = {name.lower(): name for name in files}
    for preferred in (*_STACK_THUMB_NAMES, *_SESSION_THUMB_NAMES, *_STACK_JPEG_NAMES, "0.jpg"):
        if preferred in lookup:
            return lookup[preferred]
    for name in files:
        if album_is_stack_display_image(name):
            return name
    return ""


def album_apply_listing_preview(entry: dict[str, Any], names: list[str]) -> dict[str, Any]:
    out = dict(entry)
    remote = str(out.get("filePath") or "").strip()
    thumb = str(out.get("thumbnailPath") or "").strip()
    name = str(out.get("fileName") or "").strip()
    folder = album_session_dir(thumb or remote or name)
    preview = album_preview_name(names)
    listed = {str(item).lower(): str(item) for item in names if str(item).strip()}
    remote_name = PurePosixPath(album_http_path(remote)).name.lower()
    file_name = remote_name or name.lower()
    out["previewResolved"] = True
    if out.get("isDir") is True:
        out["thumbnailPath"] = album_join_path(folder, preview) if preview else ""
        out["fileAvailable"] = False
        return out
    if file_name in {item.lower() for item in (*_STACK_THUMB_NAMES, *_STACK_COUNTER_NAMES)} and file_name in listed:
        out["thumbnailPath"] = album_join_path(folder, listed[file_name])
        out["fileAvailable"] = True
        return out
    out["thumbnailPath"] = album_join_path(folder, preview) if preview else ""
    out["fileAvailable"] = bool(remote_name and remote_name in listed)
    return out


def album_is_stack_display_image(path: str = "", name: str = "") -> bool:
    """JPEG/PNG that the live preview can paint. Skip FITS/TIFF."""
    return _album_suffix(path, name) in ALBUM_STACK_DISPLAY_SUFFIXES


def album_stack_image_name(names: list[str] | None) -> str:
    """Prefer the firmware stacked JPEG over other files in a session folder."""
    files = [str(name) for name in (names or []) if str(name).strip()]
    lookup = {name.lower(): name for name in files}
    stacked = [
        name for name in files
        if "stacked" in name.lower() and album_is_stack_display_image(name)
    ]
    for preferred in _STACK_JPEG_NAMES:
        if preferred in lookup:
            return lookup[preferred]
    if stacked:
        return stacked[0]
    if "0.jpg" in lookup:
        return lookup["0.jpg"]
    for name in files:
        if album_is_stack_display_image(name):
            return name
    return ""


def album_astro_details(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    for key in ("astroImageDetails", "astroMosaicImageDetails", "astroMultiImageDetails"):
        details = entry.get(key)
        if isinstance(details, dict) and details:
            return details
    return {}


def album_stack_session_target(entry: dict[str, Any] | None) -> str:
    details = album_astro_details(entry)
    target = str(details.get("target") or "").strip()
    if target:
        return target
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("fileName") or "").strip()


def album_stack_session_camera(entry: dict[str, Any] | None) -> str:
    if not isinstance(entry, dict):
        return ""
    try:
        cam_id = int(entry.get("camId"))
    except (TypeError, ValueError):
        cam_id = -1
    if cam_id == 1:
        return "wide"
    if cam_id == 0:
        return "tele"
    text = f"{entry.get('filePath') or ''} {entry.get('thumbnailPath') or ''} {entry.get('fileName') or ''}".upper()
    if "WIDE" in text:
        return "wide"
    if "TELE" in text:
        return "tele"
    return ""


def album_stack_session_mtime(entry: dict[str, Any] | None) -> int:
    if not isinstance(entry, dict):
        return 0
    try:
        return int(entry.get("modificationTime") or 0)
    except (TypeError, ValueError):
        return 0


def album_stack_result_path(entry: dict[str, Any] | None, listing_names: list[str] | None = None) -> str:
    """Remote path of the stacked JPEG for live preview, if one is known."""
    if not isinstance(entry, dict):
        return ""
    remote = str(entry.get("filePath") or "").strip()
    thumb = str(entry.get("thumbnailPath") or "").strip()
    if album_is_stack_display_image(remote):
        return album_http_path(remote)
    if album_is_stack_display_image(thumb):
        return album_http_path(thumb)
    folder = album_session_dir(thumb or remote)
    name = album_stack_image_name(listing_names)
    if folder and name:
        return album_join_path(folder, name)
    return ""


def choose_latest_astro_stack(
    sessions: list[dict[str, Any]] | None,
    *,
    target: str = "",
    camera: str = "",
    since: int = 0,
    skew_s: int = _STACK_RESULT_SKEW_S,
) -> dict[str, Any] | None:
    """Newest matching astro album session, or None if nothing is ready yet."""
    entries = [entry for entry in (sessions or []) if isinstance(entry, dict)]
    if not entries:
        return None
    want_target = str(target or "").strip().lower()
    want_camera = str(camera or "").strip().lower()
    min_mtime = int(since or 0) - int(skew_s or 0)
    scored: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for entry in entries:
        mtime = album_stack_session_mtime(entry)
        if since and mtime and mtime < min_mtime:
            continue
        cam = album_stack_session_camera(entry)
        if want_camera and cam and cam != want_camera:
            continue
        blob = " ".join((
            album_stack_session_target(entry),
            str(entry.get("fileName") or ""),
            album_http_path(str(entry.get("filePath") or "")),
        )).lower()
        target_hit = 1 if want_target and want_target in blob else 0
        scored.append(((target_hit, mtime), entry))
    if not scored:
        return None
    if want_target and any(item[0][0] for item in scored):
        scored = [item for item in scored if item[0][0]]
    scored.sort(key=lambda item: (item[0][0], item[0][1]), reverse=True)
    return scored[0][1]


class Camera(StrEnum):
    TELE = "tele"
    WIDE = "wide"


# Published H×V degrees. Live firmware h_fov/v_fov overrides these when present.
_CAMERA_FOV: dict[DeviceModel, dict[Camera, tuple[float, float]]] = {
    DeviceModel.DWARF_II: {
        Camera.TELE: (3.20, 1.80),
        Camera.WIDE: (43.58, 24.51),
    },
    DeviceModel.DWARF_3: {
        Camera.TELE: (2.95, 1.66),
        Camera.WIDE: (45.06, 25.93),
    },
    DeviceModel.DWARF_MINI: {
        Camera.TELE: (2.14, 1.20),
    },
}


def _as_device_model(model: DeviceModel | str | None) -> DeviceModel:
    if isinstance(model, DeviceModel):
        return model
    try:
        return DeviceModel(str(model or DeviceModel.DWARF_3))
    except ValueError:
        return DeviceModel.DWARF_3


def _as_camera(camera: Camera | str | None) -> Camera:
    value = camera.value if isinstance(camera, Camera) else str(camera or Camera.TELE)
    return Camera.WIDE if value == Camera.WIDE.value else Camera.TELE


def device_supports_wide(model: DeviceModel | str | None) -> bool:
    """DWARF Mini is a single telephoto. Wide commands and sessions do not apply."""
    return str(model or "") != DeviceModel.DWARF_MINI


def camera_fov(model: DeviceModel | str | None = None, camera: Camera | str | None = Camera.TELE) -> tuple[float, float]:
    """Return the default horizontal × vertical FOV for a telescope model and lens."""
    table = _CAMERA_FOV.get(_as_device_model(model), _CAMERA_FOV[DeviceModel.DWARF_3])
    lens = _as_camera(camera)
    if lens not in table:
        lens = Camera.TELE
    return table[lens]


def camera_fov_plausible(
    fov_h: float,
    fov_v: float,
    camera: Camera | str | None = Camera.TELE,
    model: DeviceModel | str | None = None,
) -> bool:
    """True when firmware H×V degrees look like that lens, not a stub or swap.

    Tele must stay landscape and close to the published field. A swapped
    1.66×2.95 pair or a 1° stub would shrink mosaic pane spacing.
    """
    if fov_h <= 0 or fov_v <= 0:
        return False
    if _as_camera(camera) == Camera.WIDE:
        return 15.0 <= fov_h <= 80.0 and 8.0 <= fov_v <= 50.0
    if fov_h < fov_v:
        return False
    published_h, published_v = camera_fov(model, camera)
    def _close(value: float, published: float) -> bool:
        return abs(value - published) <= max(0.35, published * 0.2)
    return _close(fov_h, published_h) and _close(fov_v, published_v)


def sky_map_camera(
    selected: Camera | str | None,
    *,
    mosaic_grid: bool = False,
    stacking: bool = False,
) -> Camera:
    """Lens used for the SKY map FOV rectangle.

    The box follows the selected camera, including a multi-pane plan. A 2×2
    with Wide selected is a wide grid, not a jump to the tele field.
    Live stacking frames stay tele so JPEG previews do not inflate.
    ``mosaic_grid`` is retained so older callers keep working; it no longer
    changes the lens.
    """
    _ = mosaic_grid
    if stacking:
        return Camera.TELE
    return _as_camera(selected)


def mosaic_stack_camera(selected: Camera | str | None = None) -> Camera:
    """Lens used for mosaic pane spacing and MOSAIC STACK. Always tele.

    The live-camera combo may be Wide so the 1×1 SKY FOV matches that lens.
    A wide 2×2 would space panes ~45° apart, then stack 3° tele fields with
    holes between them. Overlay footprints and GOTO share this tele grid.
    """
    _ = selected
    return Camera.TELE


def apply_camera_fov_defaults(telemetry: dict[str, Any], model: DeviceModel | str | None = None) -> dict[str, Any]:
    """Fill missing or implausible FOV fields from the model."""
    for camera, prefix in ((Camera.TELE, "tele"), (Camera.WIDE, "wide")):
        h_key = f"{prefix}_fov_h"
        v_key = f"{prefix}_fov_v"
        try:
            fov_h = float(telemetry.get(h_key) or 0)
            fov_v = float(telemetry.get(v_key) or 0)
        except (TypeError, ValueError):
            fov_h = fov_v = 0.0
        if not camera_fov_plausible(fov_h, fov_v, camera, model):
            fov_h, fov_v = camera_fov(model, camera)
            telemetry[h_key] = fov_h
            telemetry[v_key] = fov_v
            telemetry[f"{prefix}_fov"] = f"{fov_h:.2f}° × {fov_v:.2f}°"
        elif not telemetry.get(f"{prefix}_fov"):
            telemetry[f"{prefix}_fov"] = f"{fov_h:.2f}° × {fov_v:.2f}°"
    return telemetry


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
SKY_MAP_PROVIDER_ALADIN = "aladin"
SKY_MAP_PROVIDER_STELLARIUM_WEB = "stellarium_web"
DEFAULT_SKY_MAP_PROVIDER = SKY_MAP_PROVIDER_STELLARIUM_WEB
SKY_MAP_PROVIDERS = frozenset({SKY_MAP_PROVIDER_ALADIN, SKY_MAP_PROVIDER_STELLARIUM_WEB})


@dataclass(slots=True)
class AppSettings:
    observing_day_cutoff_hour: int = DEFAULT_OBSERVING_DAY_CUTOFF_HOUR
    stellarium_url: str = DEFAULT_STELLARIUM_URL
    sky_map_provider: str = DEFAULT_SKY_MAP_PROVIDER
    last_device_id: str = ""


@dataclass(slots=True)
class CaptureDefaults:
    exposure_seconds: float = DEFAULT_EXPOSURE_SECONDS
    gain: int = DEFAULT_GAIN
    frame_count: int = DEFAULT_FRAME_COUNT


DEVICE_COLORS: tuple[str, ...] = (
    "#62A0FF",
    "#E879F9",
    "#34D399",
    "#FBBF24",
    "#FB7185",
)
_DEVICE_COLOR_RE = re.compile(r"^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


def parse_device_color(value: Any) -> str:
    text = str(value or "").strip()
    match = _DEVICE_COLOR_RE.fullmatch(text)
    if not match:
        return ""
    hex_body = match.group(1)
    if len(hex_body) == 3:
        hex_body = "".join(ch * 2 for ch in hex_body)
    return f"#{hex_body.upper()}"


def normalize_device_color(value: Any, fallback: str | None = None) -> str:
    parsed = parse_device_color(value)
    if parsed:
        return parsed
    parsed = parse_device_color(fallback)
    return parsed or DEVICE_COLORS[0]


def next_device_color(existing: Any = None) -> str:
    used: set[str] = set()
    count = 0
    if existing:
        for item in existing:
            count += 1
            parsed = parse_device_color(item)
            if parsed:
                used.add(parsed)
    for color in DEVICE_COLORS:
        if color not in used:
            return color
    return DEVICE_COLORS[count % len(DEVICE_COLORS)]


WB_PRESET_NAMES: tuple[str, ...] = (
    "Incandescent",
    "Warm Fluorescent",
    "Fluorescent",
    "Sunlight",
    "Cloudy",
    "Shadow",
    "Twilight",
)
IR_FILTER_NAMES: tuple[str, ...] = ("VIS Filter", "Astro Filter", "Duo-Band Filter")


def normalize_ir_filter(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    key = text.lower().replace(" filter", "").replace("_", "-").replace(" ", "")
    aliases = {
        "vis": "VIS Filter",
        "0": "VIS Filter",
        "astro": "Astro Filter",
        "1": "Astro Filter",
        "duo": "Duo-Band Filter",
        "duoband": "Duo-Band Filter",
        "duo-band": "Duo-Band Filter",
        "2": "Duo-Band Filter",
    }
    return aliases.get(key, next((name for name in IR_FILTER_NAMES if name.lower() == text.lower()), text))


def wb_preset_name(value: Any) -> str:
    if isinstance(value, str) and value.strip() and not value.strip().isdigit():
        text = value.strip()
        for name in WB_PRESET_NAMES:
            if name.lower() == text.lower():
                return name
        return text
    try:
        index = int(float(value))
    except (TypeError, ValueError):
        return ""
    if 0 <= index < len(WB_PRESET_NAMES):
        return WB_PRESET_NAMES[index]
    return ""


@dataclass(slots=True)
class ControlSettings:
    """Last live camera / shooting values for one telescope."""

    shooting_mode: int = 0
    exposure: str = ""
    wide_exposure: str = ""
    gain: str = ""
    wide_gain: str = ""
    photo_exposure: str = ""
    photo_wide_exposure: str = ""
    photo_gain: str = ""
    photo_wide_gain: str = ""
    stack_count: str = ""
    stack_format: str = ""
    ir_filter: str = ""
    burst_count: str = ""
    burst_interval: str = ""
    timelapse_interval: str = ""
    timelapse_duration: str = ""
    auto_calibration: str = ""
    auto_parameters: str = ""
    wb_scene: str = ""
    wb_value: str = ""
    brightness: str = ""
    contrast: str = ""
    saturation: str = ""
    hue: str = ""
    sharpness: str = ""
    wide_wb_scene: str = ""
    wide_wb_value: str = ""
    wide_brightness: str = ""
    wide_contrast: str = ""
    wide_saturation: str = ""
    wide_hue: str = ""
    wide_sharpness: str = ""


def _control_text(value: Any) -> str:
    if value is None or value is False:
        return ""
    if value is True:
        return "true"
    text = str(value).strip()
    if not text or text == "—":
        return ""
    return text


def control_settings_from_dict(data: Any) -> ControlSettings:
    raw = dict(data) if isinstance(data, dict) else {}
    mode = 0
    try:
        parsed = int(raw.get("shooting_mode") or 0)
        if parsed in {1, 2}:
            mode = parsed
    except (TypeError, ValueError):
        mode = 0
    return ControlSettings(
        shooting_mode=mode,
        exposure=_control_text(raw.get("exposure")),
        wide_exposure=_control_text(raw.get("wide_exposure")),
        gain=_control_text(raw.get("gain")),
        wide_gain=_control_text(raw.get("wide_gain")),
        photo_exposure=_control_text(raw.get("photo_exposure")),
        photo_wide_exposure=_control_text(raw.get("photo_wide_exposure")),
        photo_gain=_control_text(raw.get("photo_gain")),
        photo_wide_gain=_control_text(raw.get("photo_wide_gain")),
        stack_count=_control_text(raw.get("stack_count")),
        stack_format=_control_text(firmware_stack_format(raw.get("stack_format"))),
        ir_filter=normalize_ir_filter(raw.get("ir_filter")),
        burst_count=_control_text(raw.get("burst_count")),
        burst_interval=_control_text(raw.get("burst_interval")),
        timelapse_interval=_control_text(raw.get("timelapse_interval")),
        timelapse_duration=_control_text(raw.get("timelapse_duration")),
        auto_calibration=_control_text(raw.get("auto_calibration")).lower(),
        auto_parameters=_control_text(raw.get("auto_parameters")).lower(),
        wb_scene=_control_text(raw.get("wb_scene")),
        wb_value=_control_text(raw.get("wb_value")),
        brightness=_control_text(raw.get("brightness")),
        contrast=_control_text(raw.get("contrast")),
        saturation=_control_text(raw.get("saturation")),
        hue=_control_text(raw.get("hue")),
        sharpness=_control_text(raw.get("sharpness")),
        wide_wb_scene=_control_text(raw.get("wide_wb_scene")),
        wide_wb_value=_control_text(raw.get("wide_wb_value")),
        wide_brightness=_control_text(raw.get("wide_brightness")),
        wide_contrast=_control_text(raw.get("wide_contrast")),
        wide_saturation=_control_text(raw.get("wide_saturation")),
        wide_hue=_control_text(raw.get("wide_hue")),
        wide_sharpness=_control_text(raw.get("wide_sharpness")),
    )


def control_settings_from_telemetry(
    telemetry: dict[str, Any] | None,
    previous: ControlSettings | None = None,
    *,
    persist_mode: bool = True,
) -> ControlSettings:
    data = to_dict(previous or ControlSettings())
    tel = telemetry or {}

    def take(source: str, dest: str) -> None:
        text = _control_text(tel.get(source))
        if text:
            data[dest] = text

    mode = 0
    try:
        mode = int(tel["shooting_mode"]) if tel.get("shooting_mode") is not None else 0
    except (TypeError, ValueError, KeyError):
        mode = 0
    if persist_mode and mode in {1, 2}:
        data["shooting_mode"] = mode
    # Photo and DSO keep independent firmware tables. Never let a PHOTO
    # 1/30 notify overwrite a saved DSO exposure such as 15s.
    # Auto Parameters owns exposure and gain. Saving those live numbers would
    # make the next mode entry treat them as a manual choice and turn auto off.
    tele_auto = tel.get("auto_parameters_tele") is True
    wide_auto = tel.get("auto_parameters_wide") is True
    if not tele_auto:
        take("astro_exposure_text", "exposure")
        take("astro_gain", "gain")
        take("photo_exposure_text", "photo_exposure")
        take("photo_gain", "photo_gain")
    if not wide_auto:
        take("astro_wide_exposure_text", "wide_exposure")
        take("astro_wide_gain", "wide_gain")
        take("photo_wide_exposure_text", "photo_wide_exposure")
        take("photo_wide_gain", "photo_wide_gain")
    if mode == 1:
        if not tele_auto:
            if not tel.get("photo_exposure_text"):
                take("exposure_text", "photo_exposure")
            if tel.get("photo_gain") in (None, "", "—"):
                take("gain", "photo_gain")
        if not wide_auto:
            if not tel.get("photo_wide_exposure_text"):
                take("wide_exposure_text", "photo_wide_exposure")
            if tel.get("photo_wide_gain") in (None, "", "—"):
                take("wide_gain", "photo_wide_gain")
    # DSO slots are updated only from astro_* keys above. The generic
    # exposure_text / gain keys are the HUD view and still hold the last
    # PHOTO values after a mode change, so copying them here turned a live
    # 1/30 and gain 0 into the saved DSO exposure.
    take("stack_count", "stack_count")
    take("stack_format", "stack_format")
    if tel.get("ir_filter") not in (None, "", "—"):
        data["ir_filter"] = normalize_ir_filter(tel.get("ir_filter"))
    take("burst_count", "burst_count")
    take("burst_interval", "burst_interval")
    take("timelapse_interval", "timelapse_interval")
    take("timelapse_duration", "timelapse_duration")
    if tel.get("auto_calibration") is True:
        data["auto_calibration"] = "true"
    elif tel.get("auto_calibration") is False:
        data["auto_calibration"] = "false"
    take("wb_scene", "wb_scene")
    take("wb_value", "wb_value")
    take("brightness", "brightness")
    take("contrast", "contrast")
    take("saturation", "saturation")
    take("hue", "hue")
    take("sharpness", "sharpness")
    take("wide_wb_scene", "wide_wb_scene")
    take("wide_wb_value", "wide_wb_value")
    take("wide_brightness", "wide_brightness")
    take("wide_contrast", "wide_contrast")
    take("wide_saturation", "wide_saturation")
    take("wide_hue", "wide_hue")
    take("wide_sharpness", "wide_sharpness")
    return control_settings_from_dict(data)


def control_settings_to_telemetry(settings: ControlSettings | None) -> dict[str, Any]:
    item = settings or ControlSettings()
    out: dict[str, Any] = {}
    if item.shooting_mode in {1, 2}:
        out["shooting_mode"] = item.shooting_mode
    photo = item.shooting_mode == 1
    tele_exp = item.photo_exposure if photo else item.exposure
    wide_exp = item.photo_wide_exposure if photo else item.wide_exposure
    tele_gain = item.photo_gain if photo else item.gain
    wide_gain = item.photo_wide_gain if photo else item.wide_gain
    if tele_exp:
        out["exposure_text"] = tele_exp
    if wide_exp:
        out["wide_exposure_text"] = wide_exp
    if item.exposure:
        out["astro_exposure_text"] = item.exposure
    if item.wide_exposure:
        out["astro_wide_exposure_text"] = item.wide_exposure
    if item.photo_exposure:
        out["photo_exposure_text"] = item.photo_exposure
    if item.photo_wide_exposure:
        out["photo_wide_exposure_text"] = item.photo_wide_exposure

    def put_int(name: str, text: str) -> None:
        if not text:
            return
        try:
            out[name] = int(float(text))
        except (TypeError, ValueError):
            out[name] = text

    put_int("gain", tele_gain)
    put_int("wide_gain", wide_gain)
    put_int("astro_gain", item.gain)
    put_int("astro_wide_gain", item.wide_gain)
    put_int("photo_gain", item.photo_gain)
    put_int("photo_wide_gain", item.photo_wide_gain)
    put_int("stack_count", item.stack_count)
    put_int("stack_format", item.stack_format)
    if item.ir_filter:
        out["ir_filter"] = item.ir_filter
    put_int("burst_count", item.burst_count)
    if item.burst_interval:
        out["burst_interval"] = item.burst_interval
    if item.timelapse_interval:
        out["timelapse_interval"] = item.timelapse_interval
    if item.timelapse_duration:
        out["timelapse_duration"] = item.timelapse_duration
    if item.auto_calibration in {"true", "false", "1", "0"}:
        out["auto_calibration"] = item.auto_calibration in {"true", "1"}
    put_int("wb_scene", item.wb_scene)
    put_int("wb_value", item.wb_value)
    put_int("brightness", item.brightness)
    put_int("contrast", item.contrast)
    put_int("saturation", item.saturation)
    put_int("hue", item.hue)
    put_int("sharpness", item.sharpness)
    put_int("wide_wb_scene", item.wide_wb_scene)
    put_int("wide_wb_value", item.wide_wb_value)
    put_int("wide_brightness", item.wide_brightness)
    put_int("wide_contrast", item.wide_contrast)
    put_int("wide_saturation", item.wide_saturation)
    put_int("wide_hue", item.wide_hue)
    put_int("wide_sharpness", item.wide_sharpness)
    return out


def control_exposure_field(shooting_mode: int, wide: bool) -> str:
    """Persisted exposure slot for this shooting mode and camera."""
    if shooting_mode == 1:
        return "photo_wide_exposure" if wide else "photo_exposure"
    return "wide_exposure" if wide else "exposure"


def control_gain_field(shooting_mode: int, wide: bool) -> str:
    """Persisted gain slot for this shooting mode and camera."""
    if shooting_mode == 1:
        return "photo_wide_gain" if wide else "photo_gain"
    return "wide_gain" if wide else "gain"


def camera_has_manual_settings(settings: ControlSettings | None, shooting_mode: int, wide: bool) -> bool:
    """True when this mode and camera have a saved exposure or gain."""
    item = settings or ControlSettings()
    exposure = getattr(item, control_exposure_field(shooting_mode, wide), "")
    gain = getattr(item, control_gain_field(shooting_mode, wide), "")
    return bool(str(exposure or "").strip() or str(gain or "").strip())


def shooting_mode_camera_steps(
    settings: ControlSettings | None,
    shooting_mode: int,
    *,
    include_wide: bool,
) -> list[tuple[str, str, str]]:
    """Camera writes after entering PHOTO or DSO.

    When Auto Parameters is selected it stays on in both PHOTO and DSO.
    Otherwise a camera with a saved exposure or gain stays manual, and a camera
    with neither gets Auto Parameters. DSO manual mode also restores filter
    and stack count.
    """
    if shooting_mode not in {1, 2}:
        return []
    item = settings or ControlSettings()
    steps: list[tuple[str, str, str]] = []
    cameras = ["tele", "wide"] if include_wide else ["tele"]
    if str(item.auto_parameters).strip().lower() in {"1", "true", "yes", "on"}:
        return [("auto_parameters", "true", camera) for camera in cameras]
    manual_cameras: list[str] = []
    for camera in cameras:
        wide = camera == "wide"
        if camera_has_manual_settings(item, shooting_mode, wide):
            manual_cameras.append(camera)
            steps.append(("auto_parameters", "false", camera))
            exposure = str(getattr(item, control_exposure_field(shooting_mode, wide)) or "").strip()
            gain = str(getattr(item, control_gain_field(shooting_mode, wide)) or "").strip()
            if exposure:
                steps.append(("exposure", exposure, camera))
            if gain:
                steps.append(("gain", gain, camera))
        else:
            steps.append(("auto_parameters", "true", camera))
    if shooting_mode == 2 and manual_cameras:
        if "tele" in manual_cameras and item.ir_filter:
            steps.append(("ir", item.ir_filter, "tele"))
        if item.stack_count:
            steps.append(("count", item.stack_count, manual_cameras[0]))
    return steps


def control_settings_patch(previous: ControlSettings | None, **changes: Any) -> ControlSettings:
    data = to_dict(previous or ControlSettings())
    for key, value in changes.items():
        if key == "ir_filter":
            data[key] = normalize_ir_filter(value)
        elif key == "shooting_mode":
            try:
                mode = int(value)
            except (TypeError, ValueError):
                continue
            if mode in {1, 2}:
                data[key] = mode
        elif key in data:
            if isinstance(value, bool):
                data[key] = "true" if value else "false"
            else:
                data[key] = _control_text(value)
    return control_settings_from_dict(data)


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
    control_settings: ControlSettings = field(default_factory=ControlSettings)
    ble_enabled: bool = True
    auto_start_preview: bool = False
    ble_password: str = "DWARF_12345678"
    wifi_mode: WifiMode = WifiMode.AUTO
    wifi_ssid: str = ""
    wifi_password: str = ""
    latitude: float = 0
    longitude: float = 0
    timezone_name: str = "UTC"
    mosaic_pa: float | None = None
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


# Device mosaic framing is the tele field times this ratio (protocol integer).
# 100 is 1.00× (one pane on that axis). 110–180 is 1.10×–1.80× (two panes).
FIRMWARE_MOSAIC_SCALE_MIN = 100
FIRMWARE_MOSAIC_SCALE_MAX = 180
FIRMWARE_MOSAIC_SCALE_STEP = 10


def clamp_firmware_mosaic_scale(value: Any, default: int = 150) -> int:
    """Snap a device-mosaic scale to 100–180, step 10."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if number != number:
        number = float(default)
    snapped = int(round(number / FIRMWARE_MOSAIC_SCALE_STEP) * FIRMWARE_MOSAIC_SCALE_STEP)
    return max(FIRMWARE_MOSAIC_SCALE_MIN, min(FIRMWARE_MOSAIC_SCALE_MAX, snapped))


def firmware_mosaic_axis_panes(scale: int) -> int:
    """1.0× stays one pane. Anything above 1.0× is two panes on that axis."""
    return 1 if int(scale) <= FIRMWARE_MOSAIC_SCALE_MIN else 2


def firmware_mosaic_overlap(scale: int) -> float:
    """Overlap when two panes cover ``scale/100`` tele fields. 1.0× has no second pane."""
    snapped = int(scale)
    if snapped <= FIRMWARE_MOSAIC_SCALE_MIN:
        return 0.0
    return max(0.0, 2.0 - snapped / 100.0)


def resolve_firmware_mosaic(
    *,
    rows: int = 1,
    columns: int = 1,
    grid_rows: int = 0,
    grid_columns: int = 0,
    horizontal_scale: Any = 150,
    vertical_scale: Any = 150,
) -> tuple[int, int, int, int] | None:
    """Device mosaic as (columns, rows, horizontal_scale, vertical_scale).

    Imported custom panes and a stored 1×1 stay host-side or a single frame.
    A stored 3×3 still resolves from the scales, which the telescope actually
    uses: each axis above 1.0× is two panes, never more. Both scales at 1.0×
    are not a mosaic even if rows and columns were left above 1.
    """
    try:
        imported = int(grid_rows or 0) >= 1 and int(grid_columns or 0) >= 1
        stored = max(1, int(rows or 1)) * max(1, int(columns or 1))
    except (TypeError, ValueError):
        return None
    if imported or stored <= 1:
        return None
    horizontal = clamp_firmware_mosaic_scale(horizontal_scale)
    vertical = clamp_firmware_mosaic_scale(vertical_scale)
    pane_columns = firmware_mosaic_axis_panes(horizontal)
    pane_rows = firmware_mosaic_axis_panes(vertical)
    if pane_columns * pane_rows <= 1:
        return None
    return pane_columns, pane_rows, horizontal, vertical


def device_mosaic_from_scales(horizontal_scale: Any, vertical_scale: Any) -> tuple[int, int, int, int]:
    """(columns, rows, horizontal_scale, vertical_scale). 1.0×1.0 is 1×1."""
    horizontal = clamp_firmware_mosaic_scale(horizontal_scale, default=100)
    vertical = clamp_firmware_mosaic_scale(vertical_scale, default=100)
    return (
        firmware_mosaic_axis_panes(horizontal),
        firmware_mosaic_axis_panes(vertical),
        horizontal,
        vertical,
    )


@dataclass(slots=True)
class Mosaic:
    # rows/columns record a device mosaic (1 or 2 per axis). Imported custom
    # panes keep those at 1x1 and store the grid in grid_rows/grid_columns.
    # The telescope sizes its own mosaic from horizontal_scale/vertical_scale.
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

    def firmware_layout(self) -> tuple[int, int, int, int] | None:
        return resolve_firmware_mosaic(
            rows=self.rows,
            columns=self.columns,
            grid_rows=self.grid_rows,
            grid_columns=self.grid_columns,
            horizontal_scale=self.horizontal_scale,
            vertical_scale=self.vertical_scale,
        )

    @property
    def panes(self) -> int:
        if self.imported_plan:
            return 1
        layout = self.firmware_layout()
        if layout is None:
            return 1
        columns, rows, _horizontal, _vertical = layout
        return columns * rows

    @property
    def grid_text(self) -> str:
        if self.grid_rows < 1 or self.grid_columns < 1:
            return ""
        return f"{self.grid_rows}×{self.grid_columns}"

    @property
    def scale_text(self) -> str:
        """Device mosaic framed field as width × height. Empty for a single frame."""
        layout = self.firmware_layout()
        if layout is None:
            return ""
        _columns, _rows, horizontal, vertical = layout
        return f"{horizontal / 100:.1f}×{vertical / 100:.1f}"

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
    mosaic_group_id: str = ""
    workflow: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, float] = field(default_factory=dict)
    step_seconds: dict[str, float] = field(default_factory=dict)
    camera_settings: dict[str, Any] = field(default_factory=dict)
    target_snapshot: dict[str, Any] = field(default_factory=dict)
    mosaic_settings: dict[str, Any] = field(default_factory=dict)


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


def normalized_sky_map_provider(value: Any, default: str = DEFAULT_SKY_MAP_PROVIDER) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        SKY_MAP_PROVIDER_ALADIN: SKY_MAP_PROVIDER_ALADIN,
        "aladin_lite": SKY_MAP_PROVIDER_ALADIN,
        "atlas": SKY_MAP_PROVIDER_ALADIN,
        SKY_MAP_PROVIDER_STELLARIUM_WEB: SKY_MAP_PROVIDER_STELLARIUM_WEB,
        "stellarium": SKY_MAP_PROVIDER_STELLARIUM_WEB,
        "stellariumweb": SKY_MAP_PROVIDER_STELLARIUM_WEB,
    }
    return aliases.get(text, default if default in SKY_MAP_PROVIDERS else DEFAULT_SKY_MAP_PROVIDER)


def app_settings_from_dict(data: dict[str, Any]) -> AppSettings:
    data = dict(data or {})
    return AppSettings(
        observing_day_cutoff_hour=clamp_cutoff_hour(data.get("observing_day_cutoff_hour")),
        stellarium_url=normalized_stellarium_url(data.get("stellarium_url")),
        sky_map_provider=normalized_sky_map_provider(data.get("sky_map_provider")),
        last_device_id=str(data.get("last_device_id") or "").strip(),
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


def parse_mosaic_pa(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value) % 360.0
    except (TypeError, ValueError):
        return None


def device_from_dict(data: dict[str, Any]) -> Device:
    data = dict(data)
    data.pop("demo_mode", None)
    data.pop("location_configured", None)
    data["mosaic_pa"] = parse_mosaic_pa(data.get("mosaic_pa"))
    data["model"] = DeviceModel(data.get("model", DeviceModel.DWARF_3))
    data["camera"] = Camera(data.get("camera", Camera.TELE))
    if data["model"] == DeviceModel.DWARF_MINI:
        data["camera"] = Camera.TELE
    try:
        data["wifi_mode"] = WifiMode(str(data.get("wifi_mode") or WifiMode.AUTO).lower())
    except ValueError:
        data["wifi_mode"] = WifiMode.AUTO
    data["hardware"] = hardware_from_dict(data.get("hardware", {}))
    data["capture_defaults"] = capture_defaults_from_dict(data.get("capture_defaults", {}))
    data["control_settings"] = control_settings_from_dict(data.get("control_settings", {}))
    data["auto_start_preview"] = bool(data.get("auto_start_preview", False))
    data["color"] = normalize_device_color(data.get("color"), Device.__dataclass_fields__["color"].default)
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


def firmware_stack_format(value: Any) -> int | None:
    """Map a panel choice onto firmware stackFormat: 2 = FITS, 3 = TIFF.

    The control combo used to send its index, 0 or 1. Those are not firmware
    values. 0 is kept as FITS and 1 as TIFF so a saved selection still applies.
    """
    text = str(value if value is not None else "").strip().lower()
    if text in {"2", "fits", "fit", "0"}:
        return 2
    if text in {"3", "tiff", "tif", "1"}:
        return 3
    return None


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


def _plain_dict(data: Any) -> dict[str, Any]:
    return dict(data) if isinstance(data, dict) else {}


def history_camera_snapshot(camera: CameraSettings) -> dict[str, Any]:
    lens = camera.camera.value if isinstance(camera.camera, Camera) else str(camera.camera or Camera.TELE)
    return {
        "camera": lens,
        "exposure_seconds": float(camera.exposure_seconds),
        "gain": int(camera.gain),
        "binning": int(camera.binning or 1),
        "ir_filter": normalize_ir_filter(camera.ir_filter),
        "frame_count": int(camera.frame_count or 0),
    }


def history_target_snapshot(target: Target) -> dict[str, Any]:
    kind = target.kind.value if isinstance(target.kind, TargetKind) else str(target.kind or "")
    return {
        "kind": kind,
        "ra_hours": target.ra_hours,
        "dec_degrees": target.dec_degrees,
        "solar_name": str(target.solar_name or ""),
    }


def history_mosaic_snapshot(mosaic: Mosaic) -> dict[str, Any]:
    return {
        "rows": int(mosaic.rows),
        "columns": int(mosaic.columns),
        "rotation_degrees": float(mosaic.rotation_degrees),
        "horizontal_scale": int(mosaic.horizontal_scale),
        "vertical_scale": int(mosaic.vertical_scale),
        "grid_rows": int(mosaic.grid_rows),
        "grid_columns": int(mosaic.grid_columns),
        "row": int(mosaic.row),
        "column": int(mosaic.column),
    }


def history_from_dict(data: dict[str, Any]) -> HistoryRecord:
    data = dict(data)
    data["workflow"] = _plain_dict(data.get("workflow"))
    data["camera_settings"] = _plain_dict(data.get("camera_settings"))
    data["target_snapshot"] = _plain_dict(data.get("target_snapshot"))
    data["mosaic_settings"] = _plain_dict(data.get("mosaic_settings"))
    data["hardware"] = _float_map(data.get("hardware"))
    data["step_seconds"] = _float_map(data.get("step_seconds"))
    try:
        data["mosaic_panes"] = max(1, int(data.get("mosaic_panes") or 1))
    except (TypeError, ValueError):
        data["mosaic_panes"] = 1
    data["mosaic_group_id"] = str(data.get("mosaic_group_id") or "")
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
        mosaic_group_id=str(session.mosaic.group_id or ""),
        workflow=asdict(session.workflow),
        camera_settings=history_camera_snapshot(session.camera),
        target_snapshot=history_target_snapshot(session.target),
        mosaic_settings=history_mosaic_snapshot(session.mosaic),
        hardware={
            key: float(getattr(hardware, key))
            for key in HardwareProfile.__dataclass_fields__
        } if hardware is not None else {},
        step_seconds={key: round(float(value), 1) for key, value in dict(step_seconds or {}).items()},
    )


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _history_workflow_text(workflow: dict[str, Any]) -> str:
    steps: list[str] = []
    if workflow.get("calibrate") or workflow.get("polar_align"):
        steps.append("POS")
    if workflow.get("calibrate"):
        steps.append("CAL")
    if workflow.get("autofocus"):
        steps.append("AF")
    elif workflow.get("infinite_focus"):
        steps.append("INF")
    if workflow.get("polar_align"):
        steps.append("POLAR")
    if workflow.get("goto"):
        steps.append("GOTO")
    wait_before = _optional_number(workflow.get("wait_before_seconds")) or 0
    wait_after = _optional_number(workflow.get("wait_after_seconds")) or 0
    if wait_before > 0:
        steps.append(f"WAIT {wait_before:g}s")
    if wait_after > 0:
        steps.append(f"SETTLE {wait_after:g}s")
    return " · ".join(steps) if steps else "Capture only"


def _history_mosaic_text(settings: dict[str, Any], panes: int) -> str:
    try:
        rows = int(settings.get("rows") or 1)
        columns = int(settings.get("columns") or 1)
        grid_rows = int(settings.get("grid_rows") or 0)
        grid_columns = int(settings.get("grid_columns") or 0)
        row = int(settings.get("row") or 0)
        column = int(settings.get("column") or 0)
        h_scale = int(settings.get("horizontal_scale") or 150)
        v_scale = int(settings.get("vertical_scale") or 150)
    except (TypeError, ValueError):
        rows, columns, grid_rows, grid_columns = 1, 1, 0, 0
        row, column, h_scale, v_scale = 0, 0, 150, 150
    rotation = _optional_number(settings.get("rotation_degrees")) or 0
    if grid_rows >= 1 and grid_columns >= 1:
        text = f"{grid_rows}×{grid_columns}"
        if row >= 1 and column >= 1:
            text += f" · R{row} C{column}"
        return text
    if rows > 1 or columns > 1 or panes > 1:
        text = f"{rows}×{columns}" if rows > 1 or columns > 1 else f"{max(1, panes)} panes"
        if h_scale != 150 or v_scale != 150:
            text += f" · {h_scale}%×{v_scale}%"
        if rotation:
            text += f" · {rotation:g}°"
        return text
    return "Single pane"


def _history_coords_text(target: dict[str, Any]) -> str:
    ra = _optional_number(target.get("ra_hours"))
    dec = _optional_number(target.get("dec_degrees"))
    if ra is not None and dec is not None:
        ra = ((ra % 24.0) + 24.0) % 24.0
        dec = max(-90.0, min(90.0, dec))
        return f"RA {ra:.3f}h  DEC {dec:+.3f}°"
    kind = str(target.get("kind") or "").lower()
    solar = str(target.get("solar_name") or "").strip()
    if kind == TargetKind.SOLAR.value and solar:
        return solar
    return ""


def history_detail_fields(record: HistoryRecord, session: Session | None = None) -> dict[str, str]:
    """Capture setup shown in the history row. Prefer the snapshot taken at run time."""
    camera = dict(record.camera_settings or {})
    target = dict(record.target_snapshot or {})
    mosaic = dict(record.mosaic_settings or {})
    workflow = dict(record.workflow or {})
    if session is not None:
        if not camera:
            camera = history_camera_snapshot(session.camera)
        if not target:
            target = history_target_snapshot(session.target)
        if not mosaic:
            mosaic = history_mosaic_snapshot(session.mosaic)
        if not workflow:
            workflow = asdict(session.workflow)
    ir = normalize_ir_filter(camera.get("ir_filter"))
    gain = camera.get("gain")
    try:
        gain_text = f"G{int(gain)}" if gain is not None and gain != "" else ""
    except (TypeError, ValueError):
        gain_text = ""
    lens = str(camera.get("camera") or "").strip().lower()
    if lens == Camera.WIDE.value:
        lens_text = "WIDE"
    elif lens == Camera.TELE.value:
        lens_text = "TELE"
    else:
        lens_text = ""
    try:
        binning = int(camera.get("binning") or 0)
    except (TypeError, ValueError):
        binning = 0
    if binning >= 2:
        bin_text = "2K"
    elif binning == 1:
        bin_text = "4K"
    else:
        bin_text = ""
    camera_bits = [bit for bit in (lens_text, bin_text) if bit]
    exposure = _optional_number(camera.get("exposure_seconds"))
    if exposure is None:
        exposure = _optional_number(record.exposure_seconds)
    return {
        "filter_text": ir,
        "gain_text": gain_text,
        "camera_text": " · ".join(camera_bits),
        "exposure_text": f"{exposure:g}s" if exposure is not None else "",
        "workflow_text": _history_workflow_text(workflow) if workflow else "",
        "mosaic_text": _history_mosaic_text(mosaic, int(record.mosaic_panes or 1)),
        "coords_text": _history_coords_text(target),
    }


def iso_duration_seconds(started: str | None, ended: str | None) -> float:
    if not started or not ended:
        return 0.0
    try:
        start = datetime.fromisoformat(started)
        end = datetime.fromisoformat(ended)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (end - start).total_seconds())


def capture_history_owner(
    *,
    session_active: bool,
    mosaic_running: bool,
    session_finalizing: bool = False,
) -> str:
    """Who should persist History for this capture: scheduled, live mosaic, or manual."""
    if session_active or session_finalizing:
        return "session"
    if mosaic_running:
        return "mosaic"
    return "manual"


def history_record_for_manual_stack(
    *,
    device_id: str,
    target_name: str,
    camera: CameraSettings,
    started_at: str,
    ended_at: str,
    captured_frame_count: int,
    outcome: str,
    hardware: HardwareProfile | None = None,
) -> HistoryRecord:
    name = str(target_name or "").strip() or "Manual stack"
    session = Session(
        name=name,
        target=Target(name=name),
        device_id=device_id,
        scheduled_start=started_at,
        camera=camera,
        actual_started_at=started_at,
        actual_ended_at=ended_at,
        outcome=outcome,
    )
    return history_record_for_run(
        session,
        actual_duration_seconds=iso_duration_seconds(started_at, ended_at),
        captured_frame_count=max(0, int(captured_frame_count or 0)),
        hardware=hardware,
    )


def history_records_for_live_mosaic(
    members: list[Session],
    captured: dict[Any, Any] | None,
    *,
    ok: bool,
    stopped: bool,
    current_index: int,
    ended_at: str,
    result: Any = None,
    hardware: HardwareProfile | None = None,
) -> list[HistoryRecord]:
    """One History row per completed pane plus the pane that stopped or failed."""
    last = max(0, int(current_index or 0))
    if last < 1:
        return []
    counts = captured or {}
    records: list[HistoryRecord] = []
    for index, member in enumerate(members, start=1):
        if index > last:
            break
        if index < last or ok:
            outcome = "Completed"
        elif stopped:
            outcome = "Stopped by user"
        else:
            outcome = str(result or "Failed")
        try:
            frames = max(0, int(counts.get(index) or counts.get(str(index)) or 0))
        except (TypeError, ValueError):
            frames = 0
        started = member.actual_started_at or member.scheduled_start
        ended = member.actual_ended_at or ended_at
        session = replace(
            member,
            status=SessionStatus.DONE if outcome == "Completed" else SessionStatus.ERROR,
            outcome=outcome,
            actual_started_at=started,
            actual_ended_at=ended,
        )
        records.append(
            history_record_for_run(
                session,
                actual_duration_seconds=iso_duration_seconds(started, ended),
                captured_frame_count=frames,
                hardware=hardware,
            )
        )
    return records
