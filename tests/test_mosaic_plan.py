from __future__ import annotations

import inspect
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import Target, TargetKind
from astro_dwarf.services import (
    SKY_WEB_FOV_JS,
    device_mosaic_pa,
    generate_mosaic_plan,
    mosaic_camera_up_is_south,
    mosaic_chart_tilt,
    mosaic_overlay_pa_fields,
    mosaic_pa_chip,
    mosaic_pane_footprints,
    mosaic_position_angle,
    mosaic_sheet_column,
    mosaic_sheet_row,
    parallactic_angle_deg,
    resolve_device_mosaic_pa,
    sky_web_center_view_script,
    templates_from_mosaic_panes,
)
from astro_dwarf.sky_atlas import ATLAS_ASTRO_JS


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _close(actual: float, expected: float, places: int = 4) -> None:
    _assert(abs(actual - expected) < 10 ** (-places), f"{actual} != {expected}")


def test_pane_one_is_west_and_north_at_pa0() -> None:
    target = Target(name="Eq", kind=TargetKind.EQUATORIAL, ra_hours=5.0, dec_degrees=0.0)
    panes = mosaic_pane_footprints(target, 2, 2, 2.0, 1.0, 0.0, position_angle=0)
    by_index = {int(item["index"]): item for item in panes}
    pane1 = by_index[1]
    _assert(pane1["ra_hours"] < 5.0, pane1)
    _assert(pane1["dec_degrees"] > 0.0, pane1)
    pane2 = by_index[2]
    _assert(pane2["ra_hours"] > 5.0, pane2)
    _assert(pane2["dec_degrees"] > 0.0, pane2)


def test_templates_keep_overlay_pane_coordinates() -> None:
    overlay_center = Target(
        name="LMC", kind=TargetKind.EQUATORIAL, ra_hours=5.359722, dec_degrees=-69.666944
    )
    later_center = Target(
        name="LMC", kind=TargetKind.EQUATORIAL, ra_hours=5.392, dec_degrees=-69.667
    )
    overlay = mosaic_pane_footprints(
        overlay_center, 2, 2, 2.95, 1.66, 0.2, position_angle=359
    )
    templates = templates_from_mosaic_panes(
        later_center, overlay, overlap=0.2, fov_h=2.95, fov_v=1.66, position_angle=359
    )
    recomputed = generate_mosaic_plan(
        later_center, 2, 2, 2.95, 1.66, 0.2, position_angle=359
    )
    _assert(len(templates) == 4, len(templates))
    _close(float(templates[0].target.ra_hours or 0), float(overlay[0]["ra_hours"]), 6)
    _close(float(templates[0].target.dec_degrees or 0), float(overlay[0]["dec_degrees"]), 6)
    _assert(
        abs(float(templates[0].target.ra_hours or 0) - float(recomputed[0].target.ra_hours or 0))
        > 0.01,
        "recomputed mosaic must not replace overlay pane centres",
    )


def test_southern_site_defaults_to_south_up_pa() -> None:
    _assert(mosaic_position_angle(True) == 180.0, mosaic_position_angle(True))
    _assert(mosaic_position_angle(False) == 0.0, mosaic_position_angle(False))
    _assert(device_mosaic_pa(-37.81) == 180.0, device_mosaic_pa(-37.81))
    _assert(device_mosaic_pa(51.5) == 0.0, device_mosaic_pa(51.5))
    _assert(device_mosaic_pa(-37.81, 0, mount_mode="EQ") == 0.0, "explicit 0 stays N-up on EQ")
    _assert(device_mosaic_pa(-37.81, 0) == 180.0, "stored 0 does not force N-up before EQ")


def test_stored_zero_stays_north_up_at_southern_site() -> None:
    resolved = resolve_device_mosaic_pa(
        -37.81,
        0,
        longitude=144.96,
        ra_hours=5.36,
        dec_degrees=-69.67,
        mount_mode="EQ",
    )
    _assert(resolved.degrees == 0.0, resolved)
    _assert(resolved.source == "stored", resolved.source)
    _assert(resolved.south_up is True, resolved.south_up)
    fields = mosaic_overlay_pa_fields(resolved)
    _assert(fields["pa_source"] == "stored", fields)
    _assert(fields["position_angle"] == 0.0, fields)
    _assert(fields["mount_mode"] == "EQ", fields)
    _assert(mosaic_pa_chip(resolved.source, resolved.degrees) == "N-UP", "stored 0 is N-UP")


def test_unset_eq_uses_celestial_default() -> None:
    resolved = resolve_device_mosaic_pa(
        -37.81,
        None,
        longitude=144.96,
        ra_hours=5.36,
        dec_degrees=-69.67,
        mount_mode="EQ",
    )
    _assert(resolved.degrees == 180.0, resolved)
    _assert(resolved.source == "default", resolved.source)
    _assert(mosaic_pa_chip(resolved.source, resolved.degrees) == "S-UP", "EQ south default")


def test_unset_altaz_uses_locked_target_parallactic() -> None:
    when = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    lat, lon = -37.81, 144.96
    ra, dec = 5.36, -69.67
    expected = parallactic_angle_deg(ra, dec, lat, lon, when)
    _assert(expected is not None, "parallactic of a locked target")
    resolved = resolve_device_mosaic_pa(
        lat,
        None,
        longitude=lon,
        ra_hours=ra,
        dec_degrees=dec,
        mount_mode="AZ",
        when=when,
    )
    _assert(resolved.source == "parallactic", resolved.source)
    _close(resolved.degrees, float(expected), 6)
    _assert(mosaic_pa_chip(resolved.source, resolved.degrees) == f"ZENITH {float(expected):.0f}°", "alt-az chip")
    fields = mosaic_overlay_pa_fields(resolved)
    _assert(fields["pa_source"] == "parallactic", fields)
    _close(float(fields["position_angle"]), float(expected), 6)
    stored = resolve_device_mosaic_pa(
        lat,
        295,
        longitude=lon,
        ra_hours=ra,
        dec_degrees=dec,
        mount_mode="AZ",
        when=when,
    )
    _assert(stored.source == "parallactic", "alt-az cannot honour a stored PA")
    _close(stored.degrees, float(expected), 6)
    view = resolve_device_mosaic_pa(lat, None, longitude=lon, mount_mode="AZ", when=when)
    _assert(view.source == "default", "no locked target must not use view-centre parallactic")
    _assert(view.degrees == 180.0, view.degrees)
    _assert(mosaic_pa_chip(view.source, view.degrees) == "S-UP", "Melbourne idle chip")
    stored_idle = resolve_device_mosaic_pa(lat, 0, longitude=lon, mount_mode="AZ", when=when)
    _assert(stored_idle.source == "default", "alt-az idle ignores stored 0")
    _assert(mosaic_pa_chip(stored_idle.source, stored_idle.degrees) == "S-UP", "stored 0 is not N-UP")
    unknown = resolve_device_mosaic_pa(lat, 0, longitude=lon, mount_mode="", when=when)
    _assert(mosaic_pa_chip(unknown.source, unknown.degrees) == "S-UP", "chip before mount telemetry")


def test_overlay_payload_includes_pa_source() -> None:
    from astro_dwarf.qt_backend import AppBackend

    src = inspect.getsource(AppBackend._sky_overlay_payload)
    _assert("mosaic_overlay_pa_fields" in src, "overlay payload must use the shared PA helper")
    _assert("pa_source" in src or "mosaic_overlay_pa_fields" in src, "pa_source on overlay")
    _assert("_overlay_pa_target" in src, "overlay PA follows the locked target")
    _assert("_log_overlay_mosaic_pa" in src, "log PA once per overlay rebuild")
    _assert("has_site" in src and "latitude" in src, "overlay JS needs site for field rotation")
    _assert("function liveCameraPa" in SKY_WEB_FOV_JS, "1×1 alt-az HUD uses live parallactic")
    _assert("p.mount_mode" in SKY_WEB_FOV_JS, "overlay JS must see mount mode")
    _assert("mosaicPaManual" in inspect.getsource(AppBackend), "Sky PA editor is EQ-only")


def test_south_up_pane_one_is_east_and_south() -> None:
    target = Target(name="LMC", kind=TargetKind.EQUATORIAL, ra_hours=5.36, dec_degrees=-69.7)
    panes = {int(item["index"]): item for item in mosaic_pane_footprints(
        target, 2, 2, 2.95, 1.66, 0.2, south_up=True
    )}
    # S-up chart: east is right, south is top. Pane 1 is camera-right/up = SE.
    _assert(panes[1]["ra_hours"] > 5.36, panes[1])
    _assert(panes[1]["dec_degrees"] < -69.7, panes[1])
    _assert(panes[4]["ra_hours"] < 5.36, panes[4])
    _assert(panes[4]["dec_degrees"] > -69.7, panes[4])


def test_contact_sheet_matches_zenith_up_overlay() -> None:
    # Stellarium is zenith-up (N-up when looking south). PA 180 pane 1 is SE =
    # bottom-left, matching the ICRS overlay — not a south-up paper chart.
    _assert(mosaic_camera_up_is_south(True, 180), "PA 180 camera-up is south")
    _assert(mosaic_sheet_column(1, 2, south_up=True, position_angle=180) == 0, "pane 1 left")
    _assert(mosaic_sheet_column(2, 2, south_up=True, position_angle=180) == 1, "pane 2 right")
    _assert(mosaic_sheet_row(1, 2, 2, south_up=True, position_angle=180) == 1, "pane 1 bottom")
    _assert(mosaic_sheet_row(3, 2, 2, south_up=True, position_angle=180) == 0, "pane 3 top")
    _assert(mosaic_sheet_row(4, 2, 2, south_up=True, position_angle=180) == 0, "pane 4 top")
    _assert(mosaic_chart_tilt(True, 180) == 0.0, mosaic_chart_tilt(True, 180))
    _assert(mosaic_chart_tilt(False, 0) == 0.0, mosaic_chart_tilt(False, 0))
    # PA 0: pane 1 is NW = top-right of the zenith-up / N-up view.
    _assert(not mosaic_camera_up_is_south(True, 0), "PA 0 camera-up is north")
    _assert(mosaic_sheet_column(1, 2, south_up=True, position_angle=0) == 1, "PA 0 pane 1 right")
    _assert(mosaic_sheet_row(1, 2, 2, south_up=True, position_angle=0) == 0, "PA 0 pane 1 top")
    _assert(mosaic_sheet_column(1, 2, south_up=False, position_angle=0) == 1, "N-up pane 1 right")
    _assert(mosaic_sheet_row(1, 2, 2, south_up=False, position_angle=0) == 0, "N-up pane 1 top")
    # Alt-az PA is the parallactic angle. On the zenith-up chart that direction
    # is the top, so pane 1 stays top-right even when q is near 180°.
    _assert(
        mosaic_sheet_column(1, 2, south_up=True, position_angle=180, zenith_camera=True) == 1,
        "alt-az pane 1 right",
    )
    _assert(
        mosaic_sheet_row(1, 2, 2, south_up=True, position_angle=180, zenith_camera=True) == 0,
        "alt-az pane 1 top",
    )
    preview = (ROOT / "astro_dwarf" / "stream_preview.py").read_text(encoding="utf-8")
    _assert("mosaic_camera_up_is_south" in preview, "PA 180 JPEGs rotate to match zenith-up")
    _assert("zenith_camera" in preview, "alt-az contact sheet does not use the S-up flip")
    _assert("flipped(" in preview, "stacked frames flip with camera-up")


def test_center_view_script_uses_engine_lookat() -> None:
    script = sky_web_center_view_script(5.138, -68.991)
    _assert("s2c" in script, script)
    _assert("lookat" in script, script)
    _assert("5.138" in script and "-68.991" in script, script)


def test_atlas_overlay_labels_icrs_pane_centres() -> None:
    _assert("function paneCenterXY" in ATLAS_ASTRO_JS, "atlas projects pane centres")
    _assert("if (!quad) return [];" not in ATLAS_ASTRO_JS, "missing corners must not drop the mosaic")
    _assert("p.south_up" in SKY_WEB_FOV_JS, "stellarium screen grid follows site hemisphere")
    _assert("payload.south_up" in ATLAS_ASTRO_JS, "atlas screen grid follows site hemisphere")
    _assert("rotateChartGroup" in SKY_WEB_FOV_JS, "stellarium keeps a 1×1 HUD helper")
    _assert("chartTilt" in SKY_WEB_FOV_JS, "stellarium screen grid uses residual chart tilt")
    _assert("function cameraHudTilt" in SKY_WEB_FOV_JS, "1×1 HUD uses full camera PA, not southern chart tilt")
    _assert("function mosaicGridTilt" in SKY_WEB_FOV_JS, "numbered mosaic fallback keeps chart tilt")
    _assert("function rotateGroup" not in SKY_WEB_FOV_JS, "do not reintroduce a shared full-PA mosaic rotator")
    _assert("function livePointingQuad" in SKY_WEB_FOV_JS, "1×1 and mosaic live video share one ICRS footprint")
    _assert("panes[i].ra_hours, panes[i].dec_degrees" in SKY_WEB_FOV_JS, "stellarium labels ICRS centres")
    _assert("fovH * (1 - overlap)" in SKY_WEB_FOV_JS, "stellarium mosaic keeps overlap")
    _assert("w * (1 - overlap)" in ATLAS_ASTRO_JS, "atlas mosaic keeps overlap")
    _assert("function overlayPixRoll" in ATLAS_ASTRO_JS, "atlas HUD must follow map rotation")
    _assert("function liveGridPanes" in ATLAS_ASTRO_JS, "atlas HUD rebuilds ICRS corners while panning")
    _assert("function viewRollDeg" in SKY_WEB_FOV_JS, "stellarium HUD must follow zenith-up field rotation")
    _assert("function levelHorizon" in SKY_WEB_FOV_JS, "stellarium drag must not wait for mouseup to level the field")
    _assert("observer.roll = 0" in SKY_WEB_FOV_JS or "obj.roll = 0" in SKY_WEB_FOV_JS, "zenith-up roll is cleared while dragging")
    _assert("function hudTilt" in SKY_WEB_FOV_JS, "stellarium screen HUD adds view roll to camera PA")
    _assert("function mosaicGridTilt" in SKY_WEB_FOV_JS, "stellarium mosaic fallback adds view roll to chart tilt")
    _assert("function haloInk" not in SKY_WEB_FOV_JS, "FOV strokes must not draw a dark halo")
    _assert("rgba(0,0,0" not in SKY_WEB_FOV_JS and 'stroke="#041208"' not in SKY_WEB_FOV_JS, "FOV must not use a dark outline")
    _assert("function framedOpen" in SKY_WEB_FOV_JS, "stellarium mosaic panes share one stroke")
    _assert("function haloLine" in SKY_WEB_FOV_JS, "stellarium up-tick uses the FOV colour")
    _assert(
        "mosaic && !zenithCamera ? chartTilt" in ATLAS_ASTRO_JS,
        "atlas mosaic chart tilt is EQ and the celestial default; 1×1 uses camera PA",
    )
    _assert('pa_source || "") === "parallactic"' in SKY_WEB_FOV_JS, "alt-az screen grid is zenith-up")
    _assert('pa_source || "") === "parallactic"' in ATLAS_ASTRO_JS, "atlas screen grid is zenith-up")
    _assert("liveQ" in ATLAS_ASTRO_JS, "atlas 1×1 alt-az uses live parallactic")
    _assert("if (mosaic && hasQuads)" in ATLAS_ASTRO_JS, "atlas mosaics still project ICRS quads")
    _assert("isFinite(q) ? -q : 0" in SKY_WEB_FOV_JS, "stellarium view roll matches Aladin zenithRotation")
    _assert("p.color" in SKY_WEB_FOV_JS and "payload.color" in ATLAS_ASTRO_JS, "FOV ink comes from the theme")
    _assert("#02900A" in SKY_WEB_FOV_JS and "#02900A" in ATLAS_ASTRO_JS, "FOV fallback is the default green")
    _assert("rgba(0,0,0" not in ATLAS_ASTRO_JS, "atlas FOV must not use a dark outline")
    _assert('stroke-dasharray="1 6.5"' in SKY_WEB_FOV_JS, "stellarium seams are round dots")
    _assert("setLineDash([1, 6.5])" in ATLAS_ASTRO_JS, "aladin seams are round dots")
    _assert("function targetCornersSvg" in SKY_WEB_FOV_JS, "stellarium frame uses target corners")
    _assert("function strokeTargetQuad" in ATLAS_ASTRO_JS, "aladin frame uses target corners")
    _assert("function paintIndex" in ATLAS_ASTRO_JS, "pane numbers sit in the cell")


def _stereo_half(fov_rad: float) -> float:
    return 2.0 * math.tan(fov_rad / 4.0)


def test_stellarium_wide_fov_keeps_camera_overlay_small() -> None:
    _assert("fov > 2 * Math.PI" in SKY_WEB_FOV_JS, "185° radian FOV must not be treated as degrees")
    _assert(
        "fov > Math.PI ? fov * Math.PI / 180" not in SKY_WEB_FOV_JS,
        "π heuristic treats max UI FOV as ~3° and fills the window",
    )
    _assert("2 * Math.tan(fov / 4)" in SKY_WEB_FOV_JS, "SWE stereographic scale stays finite at 185°")
    _assert("Math.tan(fov / 2)" not in SKY_WEB_FOV_JS, "perspective tan(fov/2) is negative past 180°")
    view_185 = 185.0 * math.pi / 180.0
    tele_v = 1.66 * math.pi / 180.0
    old_as_degrees = view_185 * math.pi / 180.0
    old_frac = _stereo_half(tele_v) / _stereo_half(old_as_degrees)
    new_frac = _stereo_half(tele_v) / _stereo_half(view_185)
    _assert(old_frac > 0.5, old_frac)
    _assert(new_frac < 0.05, new_frac)
    _assert(_stereo_half(view_185) > 0.0, "stereographic scale at 185° must stay positive")


if __name__ == "__main__":
    test_pane_one_is_west_and_north_at_pa0()
    test_templates_keep_overlay_pane_coordinates()
    test_southern_site_defaults_to_south_up_pa()
    test_stored_zero_stays_north_up_at_southern_site()
    test_unset_eq_uses_celestial_default()
    test_unset_altaz_uses_locked_target_parallactic()
    test_overlay_payload_includes_pa_source()
    test_south_up_pane_one_is_east_and_south()
    test_contact_sheet_matches_zenith_up_overlay()
    test_center_view_script_uses_engine_lookat()
    test_atlas_overlay_labels_icrs_pane_centres()
    test_stellarium_wide_fov_keeps_camera_overlay_small()
    print("ok")
