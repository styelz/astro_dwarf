from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import Target
from astro_dwarf.services import StellariumClient, choose_session_stellarium_target, stellarium_template_notes


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _response(ok: bool = True, payload: dict | None = None, text: str = "ok") -> Mock:
    response = Mock()
    response.ok = ok
    response.text = text
    response.json.return_value = payload or {}
    if ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = RuntimeError("http error")
    return response


def test_available_ok_and_fail() -> None:
    client = StellariumClient("http://localhost:8090")
    with patch("astro_dwarf.services.requests.get", return_value=_response(True)) as get:
        _assert(client.available() is True, "live rc")
        get.assert_called_once()
        _assert(get.call_args.args[0].endswith("/api/main/status"), str(get.call_args))
    with patch("astro_dwarf.services.requests.get", side_effect=OSError("down")):
        _assert(client.available() is False, "offline rc")


def test_focus_name_and_j2000() -> None:
    client = StellariumClient("http://127.0.0.1:8090")
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.focus_target("M 31")
        _assert(post.call_args.args[0].endswith("/api/main/focus"), str(post.call_args))
        _assert(post.call_args.kwargs["data"]["target"] == "M 31", str(post.call_args))
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.focus_j2000(1.0, -20.0)
        data = post.call_args.kwargs["data"]
        vec = json.loads(data["position"])
        _assert(len(vec) == 3, str(vec))
        ra = 1.0 * 15.0 * math.pi / 180.0
        dec = -20.0 * math.pi / 180.0
        _assert(math.isclose(vec[0], math.cos(dec) * math.cos(ra), abs_tol=1e-9), str(vec))
        _assert(math.isclose(vec[2], math.sin(dec), abs_tol=1e-9), str(vec))


def test_location_and_fov_and_push() -> None:
    client = StellariumClient("http://localhost:8090/")
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.set_location(-37.8, 144.9, "DWARF 3")
        data = post.call_args.kwargs["data"]
        _assert(data["latitude"] == "-37.8", str(data))
        _assert(data["longitude"] == "144.9", str(data))
        _assert(data["name"] == "DWARF 3", str(data))
        _assert(post.call_args.args[0].endswith("/api/location/setlocationfields"), str(post.call_args))
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.set_fov(2.95)
        _assert(post.call_args.args[0].endswith("/api/main/fov"), str(post.call_args))
        _assert(post.call_args.kwargs["data"]["fov"] == "2.95", str(post.call_args))
    target = Target(name="M 42", ra_hours=5.5, dec_degrees=-5.4)
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.push_view(target, -37.8, 144.9, "DWARF 3", 2.95)
        paths = [call.args[0] for call in post.call_args_list]
        _assert(any(item.endswith("/api/location/setlocationfields") for item in paths), str(paths))
        _assert(any(item.endswith("/api/main/focus") for item in paths), str(paths))
        _assert(any(item.endswith("/api/main/fov") for item in paths), str(paths))


def test_current_target_reads_selection() -> None:
    client = StellariumClient("http://localhost:8090")
    payload = {"localized-name": "M 31", "raJ2000": 10.684708, "decJ2000": 41.26875}
    with patch("astro_dwarf.services.requests.get", return_value=_response(True, payload)) as get:
        target = client.current_target()
        _assert(get.call_args.args[0].endswith("/api/objects/info"), str(get.call_args))
        _assert(target.name == "M 31", target.name)
        _assert(abs(float(target.ra_hours) - (10.684708 / 15.0)) < 1e-9, target.ra_hours)
        _assert(abs(float(target.dec_degrees) - 41.26875) < 1e-9, target.dec_degrees)


def test_current_target_without_selection() -> None:
    client = StellariumClient("http://localhost:8090")
    missing = _response(False, text="no current selection, and no name parameter given")
    with patch("astro_dwarf.services.requests.get", return_value=missing):
        try:
            client.current_target()
        except Exception:
            return
    raise AssertionError("a Stellarium response with no selection must not import")


def test_desktop_notes_include_catalog_fields() -> None:
    star = {
        "localized-name": "Gaia DR3 5932576208005295872",
        "name": "Gaia DR3 5932576208005295872",
        "type": "star",
        "vmag": 12.34,
        "absolute-mag": 5.2,
        "spectral-class": "K3V",
        "bV": 0.85,
        "distance-ly": 842.4,
        "iauConstellation": "Ara",
        "raJ2000": 16.21595308009155 * 15,
        "decJ2000": -54.06888549290931,
        "size-dd": 1e-6,
    }
    notes = stellarium_template_notes(star)
    for part in (
        "Star",
        "Magnitude: 12.34",
        "Absolute magnitude: 5.20",
        "Distance: 842 ly",
        "Spectral type: K3V",
        "B−V: 0.85",
        "Constellation: Ara",
        "Ra/Dec:",
    ):
        _assert(part in notes, notes)
    _assert("Size:" not in notes, notes)

    galaxy = {
        "type": "Galaxy",
        "localized-name": "Andromeda Galaxy",
        "name": "Andromeda Galaxy",
        "designations": "M 31 - NGC 224 - Andromeda Galaxy",
        "vmag": 3.44,
        "morpho": "SA(s)b",
        "axis-major-dd": 3.16,
        "axis-major-dms": "+3°10'",
        "axis-minor-dd": 1.0,
        "axis-minor-dms": "+1°00'",
        "iauConstellation": "And",
        "raJ2000": 10.6847,
        "decJ2000": 41.2687,
    }
    notes = stellarium_template_notes(galaxy)
    _assert(notes.startswith("Galaxy"), notes)
    _assert("Also known as: M 31, NGC 224" in notes, notes)
    alias = notes.split("Also known as: ", 1)[1].split("  ·  ")[0]
    _assert("Andromeda Galaxy" not in alias, alias)
    _assert("Morphology: SA(s)b" in notes, notes)
    _assert("Size: +3°10' × +1°00'" in notes, notes)
    _assert("Constellation: Andromeda" in notes, notes)

    # Stellarium raJ2000 is atan2 degrees and is negative for this Gaia star.
    western = {
        "type": "Star",
        "localized-name": "Gaia DR3 5932576208005295872",
        "raJ2000": -116.76070766221582,
        "decJ2000": -54.068884454407026,
        "vmag": 8.81,
    }
    notes = stellarium_template_notes(western)
    _assert("16h 12m 57s" in notes, notes)
    _assert("7h 47m" not in notes, notes)
    _assert("-54° 04' 08\"" in notes, notes)


def test_session_import_prefers_desktop_then_sky() -> None:
    desktop = Target(name="M 31", ra_hours=0.7, dec_degrees=41.3)
    sky_map = Target(name="M 42", ra_hours=5.6, dec_degrees=-5.4)
    locked = Target(name="M 45", ra_hours=3.8, dec_degrees=24.1)
    chosen, source = choose_session_stellarium_target(desktop, sky_map, locked)
    _assert(chosen.name == "M 31" and source == "desktop", f"{chosen.name} {source}")
    chosen, source = choose_session_stellarium_target(None, sky_map, locked)
    _assert(chosen.name == "M 42" and source == "sky", f"{chosen.name} {source}")
    chosen, source = choose_session_stellarium_target(
        Target(name="empty", ra_hours=None, dec_degrees=None), None, locked
    )
    _assert(chosen.name == "M 45" and source == "sky", f"{chosen.name} {source}")
    try:
        choose_session_stellarium_target(None, None, None)
    except ValueError as exc:
        _assert("Sky page" in str(exc), str(exc))
        return
    raise AssertionError("missing desktop and sky targets must fail")


def main() -> int:
    test_available_ok_and_fail()
    test_focus_name_and_j2000()
    test_location_and_fov_and_push()
    test_current_target_reads_selection()
    test_current_target_without_selection()
    test_desktop_notes_include_catalog_fields()
    test_session_import_prefers_desktop_then_sky()
    print("stellarium client tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
