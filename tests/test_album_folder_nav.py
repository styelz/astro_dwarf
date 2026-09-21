from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import album_folder_parent, album_folder_root, album_http_path


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_album_root_has_no_parent() -> None:
    root = album_folder_root("Dwarf 3")
    _assert(root == "/DWARF3", "dwarf 3 album root")
    _assert(album_folder_parent(root, root) == "", "root listing has no parent")
    _assert(album_folder_parent("", root) == "", "empty path has no parent")


def test_category_folder_parent_is_device_root() -> None:
    root = album_folder_root("Dwarf 3")
    parent = album_folder_parent("/DWARF3/Astronomy", root)
    _assert(parent == root, "astronomy returns to device root")
    _assert(album_http_path(parent).rstrip("/") == album_http_path(root).rstrip("/"), "parent is the album root")


def test_nested_folder_parent_stays_inside_album() -> None:
    root = album_folder_root("Dwarf 3")
    parent = album_folder_parent("/DWARF3/Astronomy/DWARF_RAW_1", root)
    _assert(parent == "/DWARF3/Astronomy", "session parent is the category folder")
    _assert(album_folder_parent(parent, root) == root, "category parent is the device root")


def test_outside_root_has_no_parent() -> None:
    root = album_folder_root("Dwarf 3")
    _assert(album_folder_parent("/Astronomy", root) == "", "path outside the album root")


if __name__ == "__main__":
    test_album_root_has_no_parent()
    test_category_folder_parent_is_device_root()
    test_nested_folder_parent_stays_inside_album()
    test_outside_root_has_no_parent()
    print("ok")
