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
    _assert(device_mosaic_pa(-37.81, 0) == 0.0, "explicit 0 stays N-up")


def test_stored_zero_stays_north_up_at_southern_site() -> None:
    resolved = resolve_device_mosaic_pa(
        -37.81,
        0,
        longitude=144.96,
        ra_hours=5.36,
        dec_degrees=-69.67,
        mount_mode="AZ",
    )
    _assert(resolved.degrees == 0.0, resolved)
    _assert(resolved.source == "stored", resolved.source)
    _assert(resolved.south_up is True, resolved.south_up)
    fields = mosaic_overlay_pa_fields(resolved)
    _assert(fields["pa_source"] == "stored", fields)
    _assert(fields["position_angle"] == 0.0, fields)
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
    _assert(mosaic_pa_chip(resolved.source, resolved.degrees) == "ZENITH", "alt-az chip")
    fields = mosaic_overlay_pa_fields(resolved)
    _assert(fields["pa_source"] == "parallactic", fields)
    _close(float(fields["position_angle"]), float(expected), 6)
    view = resolve_device_mosaic_pa(lat, None, longitude=lon, mount_mode="AZ", when=when)
    _assert(view.source == "default", "no locked target must not use view-centre parallactic")
    _assert(view.degrees == 180.0, view.degrees)


def test_overlay_payload_includes_pa_source() -> None:
    from astro_dwarf.qt_backend import AppBackend

    src = inspect.getsource(AppBackend._sky_overlay_payload)
    _assert("mosaic_overlay_pa_fields" in src, "overlay payload must use the shared PA helper")
    _assert("pa_source" in src or "mosaic_overlay_pa_fields" in src, "pa_source on overlay")
    _assert("_overlay_pa_target" in src, "overlay PA follows the locked target")
    _assert("_log_overlay_mosaic_pa" in src, "log PA once per overlay rebuild")
    _assert("has_site" in src and "latitude" in src, "overlay JS needs site for field rotation")
    _assert("pa_source" not in SKY_WEB_FOV_JS, "Phase 1 overlay drawers must not consume pa_source")


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


def test_contact_sheet_matches_sky_chart() -> None:
    # PA 180 S-up: pane 1 top-right, pane 2 top-left, pane 3 bottom-right, pane 4 bottom-left.
    _assert(mosaic_sheet_column(1, 2, south_up=True, position_angle=180) == 1, "pane 1 right")
    _assert(mosaic_sheet_column(2, 2, south_up=True, position_angle=180) == 0, "pane 2 left")
    _assert(mosaic_sheet_row(1, 2, 2, south_up=True, position_angle=180) == 0, "pane 1 top")
    _assert(mosaic_sheet_row(4, 2, 2, south_up=True, position_angle=180) == 1, "pane 4 bottom")
    _assert(mosaic_chart_tilt(True, 180) == 0.0, mosaic_chart_tilt(True, 180))
    _assert(mosaic_chart_tilt(False, 0) == 0.0, mosaic_chart_tilt(False, 0))
    # PA 0 on a southern site: pane 1 is NW = bottom-left of the S-up chart.
    _assert(mosaic_sheet_column(1, 2, south_up=True, position_angle=0) == 0, "PA 0 pane 1 left")
    _assert(mosaic_sheet_row(1, 2, 2, south_up=True, position_angle=0) == 1, "PA 0 pane 1 bottom")


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
    _assert("rotateChartGroup" in SKY_WEB_FOV_JS, "stellarium must not rotate numbered panes by full PA")
    _assert("chartTilt" in SKY_WEB_FOV_JS, "stellarium screen grid uses residual chart tilt")
    _assert("function rotateGroup" not in SKY_WEB_FOV_JS, "1×1 HUD must use chart tilt, not full PA")
    _assert("function livePointingQuad" in SKY_WEB_FOV_JS, "1×1 and mosaic live video share one ICRS footprint")
    _assert("panes[i].ra_hours, panes[i].dec_degrees" in SKY_WEB_FOV_JS, "stellarium labels ICRS centres")
    _assert("fovH * (1 - overlap)" in SKY_WEB_FOV_JS, "stellarium mosaic keeps overlap")
    _assert("w * (1 - overlap)" in ATLAS_ASTRO_JS, "atlas mosaic keeps overlap")
    _assert("function overlayPixRoll" in ATLAS_ASTRO_JS, "atlas HUD must follow map rotation")
    _assert("function liveGridPanes" in ATLAS_ASTRO_JS, "atlas HUD rebuilds ICRS corners while panning")
    _assert("function viewRollDeg" in SKY_WEB_FOV_JS, "stellarium HUD must follow zenith-up field rotation")
    _assert("function hudTilt" in SKY_WEB_FOV_JS, "stellarium screen grid adds view roll to chart tilt")
    _assert("function haloInk" in SKY_WEB_FOV_JS, "stellarium FOV strokes need a dark halo on daytime sky")
    _assert("function framedOpen" in SKY_WEB_FOV_JS, "stellarium mosaic panes share the halo plus accent stroke")
    _assert("function haloLine" in SKY_WEB_FOV_JS, "stellarium up-tick uses a halo under the accent")
    _assert("if (mosaic && hasQuads)" in ATLAS_ASTRO_JS, "atlas 1×1 HUD stays on the rotating screen box")
    _assert("isFinite(q) ? -q : 0" in SKY_WEB_FOV_JS, "stellarium view roll matches Aladin zenithRotation")


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
    test_contact_sheet_matches_sky_chart()
    test_center_view_script_uses_engine_lookat()
    test_atlas_overlay_labels_icrs_pane_centres()
    test_stellarium_wide_fov_keeps_camera_overlay_small()
    print("ok")
