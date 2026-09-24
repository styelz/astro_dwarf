from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    ALBUM_NO_FOLDER_INDEX,
    Camera,
    DeviceModel,
    album_folder_root,
    album_listing_entries,
    album_model_prefix,
    album_prefixed_path,
    album_root_from_path,
    album_unindexed_listing,
    camera_fov,
    device_supports_wide,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


_MINI_STACK = "/sdcard/DWARF_mini/Astronomy/M31/stacked.jpg"
_D3_INDEX = """
<html><body>
<a href="Astronomy/">Astronomy/</a> 19-Sep-2026 17:32
<a href="Normal_Photos/">Normal_Photos/</a> 19-Sep-2026 17:32
</body></html>
"""


def test_mini_root_keeps_device_case() -> None:
    root = album_root_from_path(_MINI_STACK)
    _assert(root == "/DWARF_mini", root)
    _assert(album_folder_root("Dwarf Mini", root) == "/DWARF_mini", "resolved root")
    _assert(album_prefixed_path("/DWARF_mini/Astronomy/M31/stacked.jpg", "Dwarf Mini") == "/DWARF_mini/Astronomy/M31/stacked.jpg", "not rewritten")
    _assert(album_model_prefix("Dwarf Mini") == "/DWARF_mini", "fallback tries lowercase first")
    _assert("/DWARF_MINI" not in album_prefixed_path(_MINI_STACK, "Dwarf Mini"), "no uppercase rewrite")


def test_missing_index_uses_api_paths() -> None:
    entries = [{
        "fileName": "M31",
        "filePath": _MINI_STACK,
        "thumbnailPath": "/sdcard/DWARF_mini/Astronomy/M31/stacked_thumbnail.jpg",
        "mediaType": 4,
    }, {
        "fileName": "shot.jpg",
        "filePath": "/DWARF_mini/Normal_Photos/shot.jpg",
        "mediaType": 1,
    }]
    root = album_unindexed_listing(entries, "/DWARF_mini", "/DWARF_mini")
    names = {item["fileName"] for item in root["sessions"]}
    _assert(names == {"Astronomy", "Normal_Photos"}, names)
    _assert("Could not list" not in str(root), "no guessed-path error")
    _assert(root["notice"] == "", "categories are the album")
    session = album_unindexed_listing(entries, "/DWARF_mini/Astronomy/M31", "/DWARF_mini")
    _assert(session["notice"] == ALBUM_NO_FOLDER_INDEX, session["notice"])
    _assert(session["sessions"][0]["filePath"] == "/DWARF_mini/Astronomy/M31/stacked.jpg", session["sessions"])
    _assert(session["sessions"][0]["fileAvailable"] is False, "availability waits for a HEAD")
    _assert(all("stacked.jpg" not in item["filePath"] or item["filePath"].endswith("/M31/stacked.jpg") for item in session["sessions"]), "no invented name")


def test_dwarf3_autoindex_still_parses() -> None:
    rows = album_listing_entries(_D3_INDEX)
    _assert([item["name"] for item in rows] == ["Astronomy", "Normal_Photos"], rows)
    _assert(all(item["is_dir"] for item in rows), "folders")
    _assert(album_folder_root("Dwarf 3") == "/DWARF3", "dwarf 3 root")


def test_mini_wide_uses_tele_fov() -> None:
    _assert(not device_supports_wide(DeviceModel.DWARF_MINI), "mini sessions and preview stay on tele")
    _assert(device_supports_wide(DeviceModel.DWARF_3), "dwarf 3 keeps wide")
    _assert(camera_fov(DeviceModel.DWARF_MINI, Camera.WIDE) == (2.14, 1.20), "mini wide is the tele field")
    _assert(camera_fov(DeviceModel.DWARF_MINI, Camera.TELE) == (2.14, 1.20), "mini tele")
    _assert(camera_fov(DeviceModel.DWARF_3, Camera.WIDE) == (45.06, 25.93), "dwarf 3 wide unchanged")


if __name__ == "__main__":
    test_mini_root_keeps_device_case()
    test_missing_index_uses_api_paths()
    test_dwarf3_autoindex_still_parses()
    test_mini_wide_uses_tele_fov()
    print("ok")
