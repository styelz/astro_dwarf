from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.services import (
    format_coordinate_fields,
    format_coordinates,
    parse_coordinate_fields,
    parse_coordinate_text,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _close(actual: float, expected: float, places: int = 4) -> None:
    _assert(abs(actual - expected) < 10 ** (-places), f"{actual} != {expected}")


def test_format_matches_copied_text() -> None:
    text = format_coordinates(5.575, 22.014)
    _assert(text == "RA 5.575h  DEC +22.014°", text)
    parsed = parse_coordinate_text(text)
    _assert(parsed is not None, "formatted text should parse")
    _close(parsed[0], 5.575)
    _close(parsed[1], 22.014)


def test_parse_app_copy_formats() -> None:
    cases = [
        ("RA 12.345h  DEC +67.890°", 12.345, 67.890),
        ("RA 12.345h  DEC 67.890°", 12.345, 67.890),
        ("RA  5.575h   DEC  -22.014°", 5.575, -22.014),
        ("12.345, +67.890", 12.345, 67.890),
        ("5.575 +22.014", 5.575, 22.014),
        ("83.625, 22.0", 83.625 / 15.0, 22.0),
        ("05h 34m 31.94s +22° 00' 52.2\"", 5.575539, 22.0145),
    ]
    for text, ra, dec in cases:
        parsed = parse_coordinate_text(text)
        _assert(parsed is not None, text)
        _close(parsed[0], ra, 3)
        _close(parsed[1], dec, 3)


def test_parse_rejects_invalid() -> None:
    for text in ("", "M31", "hello", "RA only", "12.3", "12.3 91.0", "400, 10"):
        _assert(parse_coordinate_text(text) is None, text)


def test_field_formats_round_trip() -> None:
    ra, dec = 11.77694, -61.18694
    for fmt in range(4):
        fields = format_coordinate_fields(ra, dec, fmt)
        _assert(fields["valid"], f"format {fmt}")
        _assert(fields["format_name"] != "", f"format {fmt} name")
        parsed = parse_coordinate_fields(fields["ra_text"], fields["dec_text"], fmt)
        _assert(parsed is not None, f"{fmt} {fields['ra_text']} {fields['dec_text']}")
        _close(parsed[0], ra, 3)
        _close(parsed[1], dec, 3)


def test_decimal_degrees_ra_below_24() -> None:
    parsed = parse_coordinate_fields("10.6847", "+41.2692", 3)
    _assert(parsed is not None, "andromeda degrees")
    _close(parsed[0], 10.6847 / 15.0, 4)
    _close(parsed[1], 41.2692, 4)
    hours = parse_coordinate_fields("0.71231", "+41.2692", 2)
    _assert(hours is not None, "andromeda hours")
    _close(hours[0], 0.71231, 4)


def test_space_and_unit_fields() -> None:
    spaces = parse_coordinate_fields("05 34 32", "+22 00 52", 1)
    _assert(spaces is not None, "spaces")
    _close(spaces[0], 5.575556, 3)
    _close(spaces[1], 22.014444, 3)
    units = parse_coordinate_fields("05h 34m 32s", "+22° 00' 52\"", 0)
    _assert(units is not None, "units")
    _close(units[0], 5.575556, 3)
    _close(units[1], 22.014444, 3)


if __name__ == "__main__":
    test_format_matches_copied_text()
    test_parse_app_copy_formats()
    test_parse_rejects_invalid()
    test_field_formats_round_trip()
    test_decimal_degrees_ra_below_24()
    test_space_and_unit_fields()
    print("ok")
