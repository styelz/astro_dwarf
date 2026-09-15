from __future__ import annotations

import csv
import re
from dataclasses import replace
from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from .domain import (
    HardwareProfile,
    Mosaic,
    Session,
    SessionTemplate,
    Target,
    Workflow,
)

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


def zoneinfo_from_name(name: str | None) -> ZoneInfo:
    text = str(name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo("UTC")


def parse_in_zone(value: str, tz: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def store_local_iso(value: datetime, tz: ZoneInfo) -> str:
    if value.tzinfo is None:
        local = value.replace(tzinfo=tz)
    else:
        local = value.astimezone(tz)
    return local.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def observing_date(scheduled_start: str, cutoff_hour: int = 12, tz: ZoneInfo | str | None = None) -> str:
    zone = tz if isinstance(tz, ZoneInfo) else zoneinfo_from_name(tz) if tz else None
    if zone is None:
        value = datetime.fromisoformat(str(scheduled_start).replace("Z", "+00:00"))
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
    else:
        value = parse_in_zone(scheduled_start, zone)
    if value.hour < cutoff_hour:
        value -= timedelta(days=1)
    return value.date().isoformat()


def mosaic_pane_workflow(workflow: Workflow, index: int) -> Workflow:
    if index <= 0:
        return workflow
    return replace(workflow, calibrate=False, polar_align=False)


def stagger_mosaic_sessions(sessions: list[Session], start: datetime, profile: HardwareProfile) -> list[Session]:
    cursor = start.replace(second=0, microsecond=0)
    result: list[Session] = []
    for index, session in enumerate(sorted(sessions, key=lambda item: pane_sort_key(item.name))):
        workflow = mosaic_pane_workflow(session.workflow, index)
        duration = DurationEngine.calculate(replace(session, workflow=workflow), profile)
        result.append(replace(
            session,
            workflow=workflow,
            scheduled_start=cursor.isoformat(timespec="minutes"),
            planned_duration_seconds=duration,
        ))
        cursor += timedelta(minutes=max(1, ceil(duration / 60.0)))
    return result


def occupied_minutes(session: Session) -> int:
    return max(1, int(ceil(max(0, session.planned_duration_seconds) / 60.0)))


def session_window(session: Session, tz) -> tuple[datetime, datetime]:
    start = parse_in_zone(session.scheduled_start, tz).replace(second=0, microsecond=0)
    return start, start + timedelta(minutes=occupied_minutes(session))


def sessions_overlap(left: Session, right: Session, tz) -> bool:
    left_start, left_end = session_window(left, tz)
    right_start, right_end = session_window(right, tz)
    return left_start < right_end and right_start < left_end


def next_free_start(
    occupied: list[tuple[datetime, datetime]],
    start: datetime,
    duration: timedelta,
) -> datetime:
    cursor = start.replace(second=0, microsecond=0)
    span = duration if duration > timedelta(0) else timedelta(minutes=1)
    blocks = sorted(occupied, key=lambda item: item[0])
    while True:
        end = cursor + span
        hit = next((block_end for block_start, block_end in blocks if cursor < block_end and block_start < end), None)
        if hit is None:
            return cursor
        cursor = hit.replace(second=0, microsecond=0)


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


def _parse_grid_index(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


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
                    mosaic=Mosaic(
                        group_id=group,
                        row=_parse_grid_index(lowered.get("row")),
                        column=_parse_grid_index(lowered.get("column")),
                    ),
                    notes=f"Imported from Telescopius: {path.name}",
                )
            )
    templates.sort(key=lambda item: pane_sort_key(item.name))
    # the plan grid is whatever the pane positions span; a plain target list has none
    grid_rows = max((item.mosaic.row for item in templates), default=0)
    grid_columns = max((item.mosaic.column for item in templates), default=0)
    return [
        replace(
            template,
            workflow=mosaic_pane_workflow(template.workflow, index),
            mosaic=replace(template.mosaic, grid_rows=grid_rows, grid_columns=grid_columns),
        )
        for index, template in enumerate(templates)
    ]
