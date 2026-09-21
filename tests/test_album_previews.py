from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    album_folder_preview_fallback_path,
    album_folder_preview_path,
    album_is_astro_session_folder,
    album_item_preview_path,
    album_preview_name,
    album_sidecar_thumbnail_path,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_astronomy_session_folder_uses_stacked_thumbnail() -> None:
    folder = "/DWARF3/Astronomy/DWARF_RAW_TELE_M42"
    _assert(album_is_astro_session_folder(folder), folder)
    _assert(
        album_folder_preview_path(folder) == f"{folder}/stacked_thumbnail.jpg",
        album_folder_preview_path(folder),
    )
    _assert(
        album_folder_preview_fallback_path(folder) == f"{folder}/stacked.jpg",
        album_folder_preview_fallback_path(folder),
    )
    _assert(
        album_item_preview_path("/DWARF3/Astronomy", "DWARF_RAW_TELE_M42", is_dir=True)
        == f"{folder}/stacked_thumbnail.jpg",
        album_item_preview_path("/DWARF3/Astronomy", "DWARF_RAW_TELE_M42", is_dir=True),
    )


def test_astronomy_category_has_no_guessed_preview() -> None:
    _assert(not album_is_astro_session_folder("/DWARF3/Astronomy"), "Astronomy")
    _assert(album_folder_preview_path("/DWARF3/Astronomy") == "", "category thumb")
    _assert(
        album_item_preview_path("/DWARF3", "Astronomy", is_dir=True) == "",
        album_item_preview_path("/DWARF3", "Astronomy", is_dir=True),
    )


def test_astronomy_jpegs_use_session_thumbnail() -> None:
    folder = "/DWARF3/Astronomy/DWARF_RAW_TELE_M42"
    stacked = album_item_preview_path(folder, "stacked.jpg")
    thumb = album_item_preview_path(folder, "stacked_thumbnail.jpg")
    _assert(stacked == f"{folder}/stacked_thumbnail.jpg", stacked)
    _assert(thumb == f"{folder}/stacked_thumbnail.jpg", thumb)


def test_astronomy_fits_uses_session_thumbnail() -> None:
    folder = "/DWARF3/Astronomy/DWARF_RAW_TELE_M42"
    preview = album_item_preview_path(folder, "stacked.fits")
    _assert(preview == f"{folder}/stacked_thumbnail.jpg", preview)


def test_photo_stills_keep_sidecar_thumbnail() -> None:
    folder = "/DWARF3/Normal_Photos"
    preview = album_item_preview_path(folder, "IMG_0001.jpg")
    sidecar = album_sidecar_thumbnail_path(folder, "IMG_0001.jpg")
    _assert(preview == sidecar, preview)
    _assert(preview == f"{folder}/Thumbnail/IMG_0001.jpg", preview)


def test_burst_folder_does_not_guess_astro_preview() -> None:
    preview = album_item_preview_path("/DWARF3/Burst", "BURST_001", is_dir=True)
    _assert(preview == "", preview)


def test_album_preview_name_prefers_stacked_thumbnail() -> None:
    name = album_preview_name(["stacked.fits", "stacked.jpg", "stacked_thumbnail.jpg"])
    _assert(name == "stacked_thumbnail.jpg", name)


def main() -> None:
    test_astronomy_session_folder_uses_stacked_thumbnail()
    test_astronomy_category_has_no_guessed_preview()
    test_astronomy_jpegs_use_session_thumbnail()
    test_astronomy_fits_uses_session_thumbnail()
    test_photo_stills_keep_sidecar_thumbnail()
    test_burst_folder_does_not_guess_astro_preview()
    test_album_preview_name_prefers_stacked_thumbnail()
    print("album preview tests passed")


if __name__ == "__main__":
    main()
