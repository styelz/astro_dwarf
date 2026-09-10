from __future__ import annotations

import math
import re
import sys
from datetime import datetime
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any
from zoneinfo import TZPATH, ZoneInfo, available_timezones

import requests

from .version import __version__

_COORD = re.compile(r"^([+-])(\d{2})(\d{2})(\d{2})?([+-])(\d{3})(\d{2})(\d{2})?$")


def parse_iso6709(coord: str) -> tuple[float, float]:
    match = _COORD.match(coord.strip())
    if not match:
        raise ValueError(f"Unsupported ISO 6709 coordinate: {coord}")
    lat = _dms(match.group(1), match.group(2), match.group(3), match.group(4))
    lon = _dms(match.group(5), match.group(6), match.group(7), match.group(8))
    return lat, lon


def _dms(sign: str, degrees: str, minutes: str, seconds: str | None) -> float:
    value = int(degrees) + int(minutes) / 60 + int(seconds or 0) / 3600
    return -value if sign == "-" else value


def _zone_tab_text() -> str:
    try:
        return resources.files("tzdata").joinpath("zoneinfo/zone1970.tab").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError, AttributeError):
        pass
    for root in TZPATH:
        for name in ("zone1970.tab", "zone.tab"):
            path = Path(root) / name
            if path.is_file():
                return path.read_text(encoding="utf-8")
    return ""


def _entry(name: str, latitude: float, longitude: float, comment: str = "") -> dict[str, Any]:
    label = f"{name} — {comment}" if comment else name
    return {
        "name": name,
        "label": label,
        "comment": comment,
        "latitude": round(float(latitude), 6),
        "longitude": round(float(longitude), 6),
    }


@lru_cache(maxsize=1)
def timezone_locations() -> tuple[dict[str, Any], ...]:
    entries: dict[str, dict[str, Any]] = {}
    for line in _zone_tab_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            latitude, longitude = parse_iso6709(parts[1])
        except ValueError:
            continue
        name = parts[2]
        comment = parts[3] if len(parts) > 3 else ""
        entries[name] = _entry(name, latitude, longitude, comment)
    if "UTC" not in entries:
        entries["UTC"] = _entry("UTC", 0, 0, "Universal Time")
    if not entries:
        for name in sorted(available_timezones()):
            entries[name] = _entry(name, 0, 0)
    return tuple(sorted(entries.values(), key=lambda item: item["name"].lower()))


def _haystack(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key, "")).replace("_", " ") for key in ("name", "label", "comment")
    ).lower()


def search_timezones(query: str, limit: int = 120) -> list[dict[str, Any]]:
    needle = query.strip().lower().replace("_", " ")
    items = timezone_locations()
    if not needle:
        return list(items[:limit])
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for item in items:
        hay = _haystack(item)
        if needle not in hay:
            continue
        city = item["name"].rsplit("/", 1)[-1].lower().replace("_", " ")
        if city == needle or item["name"].lower() == needle:
            score = 0
        elif city.startswith(needle) or item["name"].lower().startswith(needle):
            score = 1
        else:
            score = 2
        ranked.append((score, item["name"], item))
    ranked.sort()
    return [item for _, _, item in ranked[:limit]]


def match_timezone(query: str) -> dict[str, Any] | None:
    text = query.strip()
    if not text:
        return None
    lowered = text.lower().replace(" ", "_")
    for item in timezone_locations():
        if item["name"].lower() == lowered or item["label"].lower() == text.lower():
            return item
        if item["name"].rsplit("/", 1)[-1].lower().replace("_", " ") == text.lower():
            return item
    hits = search_timezones(text, limit=2)
    if len(hits) == 1:
        return hits[0]
    if hits:
        city = hits[0]["name"].rsplit("/", 1)[-1].lower().replace("_", " ")
        if city == text.lower() or hits[0]["name"].lower() == lowered:
            return hits[0]
    return None


def nearest_timezone(latitude: float, longitude: float) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_distance = math.inf
    for item in timezone_locations():
        if item["name"] == "UTC":
            continue
        distance = (item["latitude"] - latitude) ** 2 + (item["longitude"] - longitude) ** 2
        if distance < best_distance:
            best_distance = distance
            best = item
    return best


def geocode_location(query: str) -> dict[str, Any] | None:
    response = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": query, "format": "json", "limit": 1},
        headers={"User-Agent": f"AstroDwarf/{__version__}"},
        timeout=12,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return None
    latitude = float(rows[0]["lat"])
    longitude = float(rows[0]["lon"])
    nearest = nearest_timezone(latitude, longitude)
    timezone_name = nearest["name"] if nearest else "UTC"
    display = str(rows[0].get("display_name") or query)
    result = _entry(timezone_name, latitude, longitude, display)
    result["display_name"] = display
    return result


def resolve_location(query: str) -> dict[str, Any] | None:
    local = match_timezone(query)
    if local and (
        local["name"] in {"UTC", "Etc/UTC"}
        or abs(local["latitude"]) > 1e-9
        or abs(local["longitude"]) > 1e-9
    ):
        return local
    return geocode_location(query) or local


def has_site_coordinates(latitude: Any, longitude: Any) -> bool:
    """True when the telescope has a real observing site (not lat/long 0,0)."""
    try:
        lat = float(latitude or 0)
        lon = float(longitude or 0)
    except (TypeError, ValueError):
        return False
    return abs(lat) >= 1e-9 or abs(lon) >= 1e-9


# Windows TimeZoneKeyName → IANA, from CLDR windowsZones (common entries).
_WINDOWS_TZ = {
    "AUS Eastern Standard Time": "Australia/Melbourne",
    "AUS Central Standard Time": "Australia/Darwin",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "E. Australia Standard Time": "Australia/Brisbane",
    "Tasmania Standard Time": "Australia/Hobart",
    "W. Australia Standard Time": "Australia/Perth",
    "New Zealand Standard Time": "Pacific/Auckland",
    "UTC": "UTC",
    "GMT Standard Time": "Europe/London",
    "Romance Standard Time": "Europe/Paris",
    "W. Europe Standard Time": "Europe/Berlin",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "GTB Standard Time": "Europe/Bucharest",
    "FLE Standard Time": "Europe/Helsinki",
    "Russian Standard Time": "Europe/Moscow",
    "Eastern Standard Time": "America/New_York",
    "US Eastern Standard Time": "America/Indianapolis",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles",
    "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Atlantic Standard Time": "America/Halifax",
    "Pacific SA Standard Time": "America/Santiago",
    "SA Pacific Standard Time": "America/Bogota",
    "SA Western Standard Time": "America/La_Paz",
    "SA Eastern Standard Time": "America/Cayenne",
    "China Standard Time": "Asia/Shanghai",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Korea Standard Time": "Asia/Seoul",
    "Singapore Standard Time": "Asia/Singapore",
    "India Standard Time": "Asia/Kolkata",
    "Arabian Standard Time": "Asia/Dubai",
    "Israel Standard Time": "Asia/Jerusalem",
    "South Africa Standard Time": "Africa/Johannesburg",
    "GMT+12": "Pacific/Auckland",
}


def _windows_timezone_key_name() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "TimeZoneKeyName")
    except OSError:
        return ""
    return str(value or "").strip()


def _timezone_with_coords(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    matched = match_timezone(name)
    if matched and has_site_coordinates(matched.get("latitude"), matched.get("longitude")):
        return matched
    return None


def _timezone_matching_offset() -> dict[str, Any] | None:
    offset = datetime.now().astimezone().utcoffset()
    if offset is None:
        return None
    for item in timezone_locations():
        name = str(item.get("name") or "")
        if name in {"UTC", "Etc/UTC"} or not has_site_coordinates(item.get("latitude"), item.get("longitude")):
            continue
        try:
            zone_offset = datetime.now(ZoneInfo(name)).utcoffset()
        except Exception:
            continue
        if zone_offset == offset:
            return item
    return None


def suggested_timezone() -> dict[str, Any] | None:
    """Best observing timezone for this computer: IANA key, Windows map, then UTC offset."""
    tzinfo = datetime.now().astimezone().tzinfo
    key = getattr(tzinfo, "key", None) or getattr(tzinfo, "zone", None)
    matched = _timezone_with_coords(str(key) if key else "")
    if matched:
        return matched
    windows_name = _windows_timezone_key_name()
    mapped = _WINDOWS_TZ.get(windows_name)
    if not mapped and windows_name:
        mapped = _WINDOWS_TZ.get(windows_name.replace("\x00", ""))
    matched = _timezone_with_coords(mapped)
    if matched:
        return matched
    return _timezone_matching_offset()
