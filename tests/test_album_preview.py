from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    album_apply_listing_preview,
    album_entry_preview_path,
    album_folder_preview_path,
    album_frame_sidecar_path,
    album_http_url,
    album_item_preview_path,
    album_session_dir,
    album_sidecar_thumbnail_path,
)


SESSION = "/DWARF3/Astronomy/DWARF_RAW_TELE_FOV centre pane 1_EXP_15_GAIN_60_2026-09-18-21-33-40-701"
STACKED_THUMB = f"{SESSION}/stacked_thumbnail.jpg"
FRAME = "FOV centre pane 1_15s60_Astro_20260918-213434837_26C.tif"
STACKED16 = "stacked-16_FOV centre pane 1_15s60_Astro_20260918-213420620.png"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_astro_stack_products_use_session_thumbnail() -> None:
    for name in ("stacked.jpg", "img_reference.png", STACKED16):
        preview = album_item_preview_path(SESSION, name)
        _assert(preview == STACKED_THUMB, f"{name} -> {preview}")
        _assert("/Thumbnail/" not in preview, preview)


def test_small_astro_thumbs_keep_themselves() -> None:
    _assert(album_item_preview_path(SESSION, "stacked_thumbnail.jpg") == STACKED_THUMB, "stacked_thumbnail")
    _assert(
        album_item_preview_path(SESSION, "img_stacked_counter.png")
        == f"{SESSION}/img_stacked_counter.png",
        "counter",
    )


def test_astro_tiff_uses_jpg_frame_sidecar() -> None:
    preview = album_item_preview_path(SESSION, FRAME)
    _assert(preview == f"{SESSION}/Thumbnail/{Path(FRAME).stem}.jpg", preview)
    _assert(album_frame_sidecar_path(SESSION, FRAME) == preview, "sidecar helper")


def test_session_folder_preview_is_at_root() -> None:
    _assert(album_folder_preview_path(SESSION) == STACKED_THUMB, album_folder_preview_path(SESSION))
    _assert(
        album_item_preview_path("/DWARF3/Astronomy", Path(SESSION).name, is_dir=True) == STACKED_THUMB,
        "dir tile",
    )


def test_photo_still_keeps_same_name_sidecar() -> None:
    folder = "/DWARF3/Normal_Photos"
    _assert(
        album_item_preview_path(folder, "IMG_001.jpg") == f"{folder}/Thumbnail/IMG_001.jpg",
        album_item_preview_path(folder, "IMG_001.jpg"),
    )
    _assert(
        album_sidecar_thumbnail_path(folder, "IMG_001.jpg") == f"{folder}/Thumbnail/IMG_001.jpg",
        "photo sidecar",
    )


def test_firmware_session_row_uses_stacked_thumbnail() -> None:
    preview = album_entry_preview_path({
        "fileName": Path(SESSION).name,
        "filePath": f"{SESSION}/stacked.jpg",
        "thumbnailPath": f"{SESSION}/Thumbnail/stacked.jpg",
        "mediaType": 4,
    })
    _assert(preview == STACKED_THUMB, preview)


def test_session_dir_skips_thumbnail_folder() -> None:
    _assert(album_session_dir(f"{SESSION}/Thumbnail/stacked.jpg") == SESSION, album_session_dir(f"{SESSION}/Thumbnail/stacked.jpg"))
    _assert(album_session_dir(f"{SESSION}/stacked.jpg") == SESSION, album_session_dir(f"{SESSION}/stacked.jpg"))


def test_album_http_url_encodes_spaces() -> None:
    url = album_http_url("192.168.1.42", STACKED_THUMB)
    _assert(" " not in url, url)
    _assert("%20centre%20pane%20" in url, url)
    _assert(url.endswith("/stacked_thumbnail.jpg"), url)


def test_stacked_fits_uses_session_thumbnail() -> None:
    preview = album_item_preview_path(SESSION, "stacked-16_Gaia DR3_30s60_Duo-Band_20260911-231826473.fits")
    _assert(preview == STACKED_THUMB, preview)
    _assert("/Thumbnail/" not in preview, preview)


def test_listing_preview_skips_missing_stack_files() -> None:
    folder = "/DWARF3/Astronomy/STARTRAILS"
    updated = album_apply_listing_preview(
        {
            "fileName": "STARTRAILS",
            "filePath": folder,
            "thumbnailPath": f"{folder}/stacked_thumbnail.jpg",
            "isDir": True,
            "mediaType": 4,
        },
        [],
    )
    _assert(updated.get("previewResolved") is True, "resolved")
    _assert(updated.get("thumbnailPath") == "", updated.get("thumbnailPath"))


def test_listing_preview_uses_existing_stack_thumbnail() -> None:
    updated = album_apply_listing_preview(
        {
            "fileName": Path(SESSION).name,
            "filePath": SESSION,
            "thumbnailPath": f"{SESSION}/stacked_thumbnail.jpg",
            "isDir": True,
            "mediaType": 4,
        },
        ["shotsInfo.json", "stacked.jpg", "stacked_thumbnail.jpg"],
    )
    _assert(updated.get("thumbnailPath") == STACKED_THUMB, updated.get("thumbnailPath"))


def main() -> None:
    test_astro_stack_products_use_session_thumbnail()
    test_small_astro_thumbs_keep_themselves()
    test_astro_tiff_uses_jpg_frame_sidecar()
    test_session_folder_preview_is_at_root()
    test_photo_still_keeps_same_name_sidecar()
    test_firmware_session_row_uses_stacked_thumbnail()
    test_session_dir_skips_thumbnail_folder()
    test_album_http_url_encodes_spaces()
    test_stacked_fits_uses_session_thumbnail()
    test_listing_preview_skips_missing_stack_files()
    test_listing_preview_uses_existing_stack_thumbnail()
    print("test_album_preview: ok")


if __name__ == "__main__":
    main()
