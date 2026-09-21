from __future__ import annotations

import sys
from math import cos, radians
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import Camera, DeviceModel, Target, camera_fov, camera_fov_plausible
from astro_dwarf.services import (
    mosaic_pane_footprints,
    mosaic_panes_match_center,
    named_mosaic_center,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _target(ra_hours: float = 5.0, dec_degrees: float = 20.0) -> Target:
    return Target(name="Centre", ra_hours=ra_hours, dec_degrees=dec_degrees)


def test_two_by_two_is_built_around_the_centre() -> None:
    panes = mosaic_pane_footprints(_target(), 2, 2, 2.95, 1.66, 0.2, position_angle=0)
    _assert(len(panes) == 4, "2×2 has four panes")
    ra = [pane["ra_hours"] for pane in panes]
    dec = [pane["dec_degrees"] for pane in panes]
    _assert(abs(sum(ra) / 4 - 5.0) < 0.01, "RA barycentre stays on the target")
    _assert(abs(sum(dec) / 4 - 20.0) < 0.01, "Dec barycentre stays on the target")


def test_pa0_pane_one_is_west_and_north_of_centre() -> None:
    panes = {pane["index"]: pane for pane in mosaic_pane_footprints(
        _target(), 2, 2, 2.95, 1.66, 0.2, position_angle=0
    )}
    # N-up chart: west is smaller RA, north is larger Dec. Pane 1 is camera-right/up.
    _assert(panes[1]["ra_hours"] < 5.0, "pane 1 is west of centre")
    _assert(panes[1]["dec_degrees"] > 20.0, "pane 1 is north of centre")
    _assert(panes[2]["ra_hours"] > 5.0, "pane 2 is east of centre")
    _assert(panes[2]["dec_degrees"] > 20.0, "pane 2 is north of centre")
    _assert(panes[3]["ra_hours"] < 5.0, "pane 3 is west of centre")
    _assert(panes[3]["dec_degrees"] < 20.0, "pane 3 is south of centre")
    _assert(panes[4]["ra_hours"] > 5.0, "pane 4 is east of centre")
    _assert(panes[4]["dec_degrees"] < 20.0, "pane 4 is south of centre")


def test_adjacent_pane_step_matches_fov_and_overlap() -> None:
    fov_h, fov_v, overlap = 2.95, 1.66, 0.2
    panes = {pane["index"]: pane for pane in mosaic_pane_footprints(
        _target(6.0, 0.0), 2, 2, fov_h, fov_v, overlap, position_angle=0
    )}
    east_hours = (panes[2]["ra_hours"] - panes[1]["ra_hours"]) * 15.0
    north = panes[1]["dec_degrees"] - panes[3]["dec_degrees"]
    _assert(abs(east_hours - fov_h * (1.0 - overlap)) < 0.05, "2×2 row step uses overlap")
    _assert(abs(north - fov_v * (1.0 - overlap)) < 0.05, "2×2 column step uses overlap")


def test_two_by_two_keeps_overlap_offset() -> None:
    fov_h, fov_v, overlap = 2.95, 1.66, 0.2
    ra_hours, dec_degrees = 14.66, -60.83
    panes = mosaic_pane_footprints(
        _target(ra_hours, dec_degrees),
        2,
        2,
        fov_h,
        fov_v,
        overlap,
        south_up=True,
        position_angle=180,
    )
    offset_x = fov_h * (1.0 - overlap) / 2.0
    offset_y = fov_v * (1.0 - overlap) / 2.0
    _assert(abs(offset_x - 1.18) < 0.01, offset_x)
    _assert(abs(offset_y - 0.664) < 0.01, offset_y)
    by_index = {pane["index"]: pane for pane in panes}
    pane1 = by_index[1]
    dra_hours = ((pane1["ra_hours"] - ra_hours + 12.0) % 24.0) - 12.0
    dra = dra_hours * 15.0 * cos(radians(dec_degrees))
    ddec = pane1["dec_degrees"] - dec_degrees
    _assert(dra > 0, "PA 180 pane 1 is east of centre")
    _assert(ddec < 0, "PA 180 pane 1 is south of centre")
    for pane in panes:
        dra_hours = ((pane["ra_hours"] - ra_hours + 12.0) % 24.0) - 12.0
        dra = dra_hours * 15.0 * cos(radians(dec_degrees))
        ddec = pane["dec_degrees"] - dec_degrees
        _assert(abs(abs(dra) - offset_x) < 0.08, (pane["index"], dra, offset_x))
        _assert(abs(abs(ddec) - offset_y) < 0.08, (pane["index"], ddec, offset_y))


def test_three_by_three_keeps_overlap_step() -> None:
    fov_h, fov_v, overlap = 2.95, 1.66, 0.2
    panes = {pane["index"]: pane for pane in mosaic_pane_footprints(
        _target(6.0, 0.0), 3, 3, fov_h, fov_v, overlap, position_angle=0
    )}
    east_hours = (panes[2]["ra_hours"] - panes[1]["ra_hours"]) * 15.0
    north = panes[1]["dec_degrees"] - panes[4]["dec_degrees"]
    _assert(abs(east_hours - fov_h * (1.0 - overlap)) < 0.05, "3×3 row step uses overlap")
    _assert(abs(north - fov_v * (1.0 - overlap)) < 0.05, "3×3 column step uses overlap")
    _assert(abs(panes[5]["ra_hours"] - 6.0) < 0.01, "centre pane stays on the target")
    _assert(abs(panes[5]["dec_degrees"] - 0.0) < 0.01, "centre pane stays on the target")


def test_live_mosaic_center_prefers_locked_target() -> None:
    locked = Target(name="Toliman", ra_hours=14.66, dec_degrees=-60.83)
    view = Target(name="FOV centre", ra_hours=14.316, dec_degrees=-61.537)
    chosen = named_mosaic_center(locked, view)
    _assert(chosen is not None and chosen.name == "Toliman", chosen)
    _assert(abs(chosen.ra_hours - 14.66) < 1e-6, chosen)
    pane = Target(name="Toliman pane 1", ra_hours=14.74, dec_degrees=-61.16)
    _assert(named_mosaic_center(pane) is None, "pane labels are not mosaic centres")
    _assert(named_mosaic_center(pane, locked).name == "Toliman", "falls through pane labels")
    view_panes = mosaic_pane_footprints(view, 2, 2, 2.95, 1.66, 0.2, position_angle=180)
    _assert(
        not mosaic_panes_match_center(view_panes, 14.66, -60.83, 2.95, 1.66),
        "view-centre overlay must not be reused around Toliman",
    )
    locked_panes = mosaic_pane_footprints(locked, 2, 2, 2.95, 1.66, 0.2, position_angle=180)
    _assert(mosaic_panes_match_center(locked_panes, 14.66, -60.83, 2.95, 1.66), "locked grid matches")
    shifted = mosaic_pane_footprints(
        Target(name="Shifted", ra_hours=14.66 + 0.737 / 15.0, dec_degrees=-60.83 - 0.415),
        2,
        2,
        2.95,
        1.66,
        0.2,
        position_angle=180,
    )
    _assert(
        not mosaic_panes_match_center(shifted, 14.66, -60.83, 2.95, 1.66),
        "a quarter-tile view-centre overlay must not be reused",
    )


def test_swapped_firmware_fov_does_not_shrink_step() -> None:
    _assert(not camera_fov_plausible(1.66, 2.95, Camera.TELE), "swapped H×V")
    _assert(not camera_fov_plausible(1.0, 0.6, Camera.TELE), "stub field")
    _assert(camera_fov_plausible(2.95, 1.66, Camera.TELE), "published tele")
    fov_h, fov_v = 1.66, 2.95
    if not camera_fov_plausible(fov_h, fov_v, Camera.TELE, DeviceModel.DWARF_3):
        fov_h, fov_v = camera_fov(DeviceModel.DWARF_3, Camera.TELE)
    panes = {pane["index"]: pane for pane in mosaic_pane_footprints(
        _target(6.0, 0.0), 2, 2, fov_h, fov_v, 0.2, position_angle=0
    )}
    step_x = 2.95 * 0.8
    east_hours = (panes[2]["ra_hours"] - panes[1]["ra_hours"]) * 15.0
    _assert(abs(east_hours - step_x) < 0.05, "published tele FOV with overlap, not swapped FOV")


if __name__ == "__main__":
    test_two_by_two_is_built_around_the_centre()
    test_pa0_pane_one_is_west_and_north_of_centre()
    test_adjacent_pane_step_matches_fov_and_overlap()
    test_two_by_two_keeps_overlap_offset()
    test_three_by_three_keeps_overlap_step()
    test_live_mosaic_center_prefers_locked_target()
    test_swapped_firmware_fov_does_not_shrink_step()
    print("ok")
