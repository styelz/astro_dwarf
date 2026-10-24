from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import (
    album_canonical_media_type,
    album_delete_batches,
    album_delete_outcome,
    album_delete_payload,
    album_delete_summary,
    album_delete_walk_path,
    album_is_category_folder_path,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_photo_folder_row_uses_firmware_type_and_category_name() -> None:
    payload = album_delete_payload([
        {
            "filePath": "/DWARF3/Normal_Photos/DWARF3_WIDE_2026-09-19-17-32-06-639.jpg",
            "fileName": "DWARF3_WIDE_2026-09-19-17-32-06-639.jpg",
            "mediaType": 0,
        }
    ])
    _assert(payload["datas"] == [{
        "mediaType": 1,
        "filePath": "/DWARF3/Normal_Photos/DWARF3_WIDE_2026-09-19-17-32-06-639.jpg",
        "fileName": "Normal_Photos",
        "subType": 0,
    }], payload)


def test_photo_album_row_keeps_firmware_fields() -> None:
    payload = album_delete_payload([
        {
            "file_path": "/DWARF3/Normal_Photos/shot.jpg",
            "file_name": "Normal_Photos",
            "media_type": 1,
        }
    ])
    _assert(payload["datas"] == [{
        "mediaType": 1,
        "filePath": "/DWARF3/Normal_Photos/shot.jpg",
        "fileName": "Normal_Photos",
        "subType": 0,
    }], payload)


def test_astro_folder_maps_to_stacked_album_item() -> None:
    payload = album_delete_payload([
        {
            "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_Beta Hydri_2026-09-20-05-38-39-383",
            "fileName": "DWARF_RAW_TELE_Beta Hydri_2026-09-20-05-38-39-383",
            "mediaType": 6,
            "isDir": True,
        }
    ])
    _assert(payload["datas"] == [{
        "mediaType": 4,
        "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_Beta Hydri_2026-09-20-05-38-39-383/stacked.jpg",
        "fileName": "DWARF_RAW_TELE_Beta Hydri_2026-09-20-05-38-39-383",
        "subType": 0,
    }], payload)


def test_astro_file_inside_session_deletes_the_session() -> None:
    payload = album_delete_payload([
        {
            "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_M31_2026-09-20/fits_0001.fits",
            "fileName": "fits_0001.fits",
            "media_type": 0,
        }
    ])
    _assert(payload["datas"] == [{
        "mediaType": 4,
        "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_M31_2026-09-20/stacked.jpg",
        "fileName": "DWARF_RAW_TELE_M31_2026-09-20",
        "subType": 0,
    }], payload)


def test_video_keeps_type_and_file_name() -> None:
    payload = album_delete_payload([
        {
            "filePath": "/DWARF3/Videos/clip.mp4",
            "fileName": "clip.mp4",
            "mediaType": 2,
        }
    ])
    _assert(payload["datas"] == [{
        "mediaType": 2,
        "filePath": "/DWARF3/Videos/clip.mp4",
        "fileName": "clip.mp4",
        "subType": 0,
    }], payload)


def test_empty_list_is_still_object_body() -> None:
    _assert(album_delete_payload([]) == {"datas": []}, album_delete_payload([]))
    _assert(album_delete_payload(None) == {"datas": []}, album_delete_payload(None))
    _assert(album_delete_payload([{"filePath": ""}]) == {"datas": []}, "empty path")


def test_folder_paths_infer_photo_and_astro_types() -> None:
    _assert(
        album_canonical_media_type("/DWARF3/Normal_Photos/shot.jpg", "shot.jpg") == 1,
        "photo",
    )
    _assert(
        album_canonical_media_type(
            "/DWARF3/Astronomy/DWARF_RAW_TELE_M31",
            "DWARF_RAW_TELE_M31",
            6,
            True,
        ) == 4,
        "astro list filter",
    )
    _assert(
        album_canonical_media_type("/DWARF3/Videos/clip.mp4", "clip.mp4") == 2,
        "video",
    )


def test_astronomy_category_is_not_a_session() -> None:
    from astro_dwarf.domain import (
        album_is_astro_session_folder,
        album_is_astronomy_category_folder,
        album_is_protected_folder,
    )
    _assert(album_is_astronomy_category_folder("/DWARF3/Astronomy", "Astronomy"), "category")
    _assert(album_is_protected_folder("/DWARF3/Astronomy", "Astronomy"), "protected")
    _assert(album_is_category_folder_path("/DWARF3/Astronomy", "Astronomy"), "category folder")
    _assert(album_is_category_folder_path("/DWARF3/Burst", "Burst"), "burst category")
    _assert(
        album_is_category_folder_path("/DWARF3/Astronomy", "DWARF_RAW_TELE_M31"),
        "category path is still the Astronomy folder",
    )
    _assert(
        not album_is_category_folder_path(
            "/DWARF3/Astronomy/DWARF_RAW_TELE_M31",
            "Astronomy",
        ),
        "session path is not the Astronomy folder",
    )
    _assert(
        not album_is_category_folder_path(
            "/DWARF3/Normal_Photos/shot.jpg",
            "Normal_Photos",
        ),
        "photo file is not a category folder",
    )
    _assert(
        not album_is_astro_session_folder("/DWARF3/Astronomy", "Astronomy"),
        "not session",
    )
    _assert(
        album_is_astro_session_folder(
            "/DWARF3/Astronomy/DWARF_RAW_TELE_M31",
            "DWARF_RAW_TELE_M31",
        ),
        "session",
    )


def test_category_folders_are_not_sent_to_firmware() -> None:
    payload = album_delete_payload([
        {
            "filePath": "/DWARF3/Astronomy",
            "fileName": "Astronomy",
            "mediaType": 4,
            "isDir": True,
        },
        {
            "filePath": "/DWARF3/Burst",
            "fileName": "Burst",
            "mediaType": 3,
        },
        {
            "filePath": "/DWARF3/Astronomy",
            "fileName": "DWARF_RAW_TELE_M31",
            "mediaType": 4,
        },
        {
            "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_M31",
            "fileName": "Astronomy",
            "mediaType": 4,
            "isDir": True,
        },
    ])
    _assert(payload["datas"] == [{
        "mediaType": 4,
        "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_M31/stacked.jpg",
        "fileName": "DWARF_RAW_TELE_M31",
        "subType": 0,
    }], payload)


def test_burst_folder_maps_to_first_frame() -> None:
    payload = album_delete_payload([
        {
            "filePath": "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-20-07-48-13-247",
            "fileName": "DWARF3_TELE_BURST_2026-09-20-07-48-13-247",
            "mediaType": 3,
            "isDir": True,
        }
    ])
    _assert(payload["datas"] == [{
        "mediaType": 3,
        "filePath": "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-20-07-48-13-247/0.jpg",
        "fileName": "DWARF3_TELE_BURST_2026-09-20-07-48-13-247",
        "subType": 0,
    }], payload)


def test_firmware_is_success_false_is_still_accepted() -> None:
    outcome = album_delete_outcome(
        {
            "code": 0,
            "data": [
                {
                    "fileName": "DWARF_RAW_TELE_M31",
                    "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_M31/stacked.jpg",
                    "isSuccess": False,
                    "mediaType": 4,
                },
                {
                    "fileName": "DWARF_RAW_TELE_M32",
                    "filePath": "/DWARF3/Astronomy/DWARF_RAW_TELE_M32/stacked.jpg",
                    "isSuccess": False,
                    "mediaType": 4,
                },
            ],
        },
        2,
    )
    _assert(outcome["deleted"] == [], outcome)
    _assert(outcome["failed"] == 2, outcome)
    _assert(outcome["requested"] == 2, outcome)
    message, level = album_delete_summary(2, 0)
    _assert(level == "success", (message, level))
    _assert("Deleted 2" in message, message)
    message, level = album_delete_summary(2, 2)
    _assert(level == "error", (message, level))


def test_mosaic_folder_deletes_pane_subfolders_first() -> None:
    parent = "/DWARF3/Astronomy/M31 mosaic"
    pane1 = "DWARF_RAW_TELE_M31 pane 1_EXP_15_GAIN_60_2026-10-09-03-01-05-000"
    pane2 = "DWARF_RAW_TELE_M31 pane 2_EXP_15_GAIN_60_2026-10-09-03-16-15-000"
    listing = [
        {"name": pane1, "is_dir": True},
        {"name": pane2, "is_dir": True},
        {"name": "stacked.jpg", "is_dir": False},
        {"name": "Thumbnail", "is_dir": True},
    ]
    batches = album_delete_batches(
        [{"filePath": parent, "fileName": "M31 mosaic", "mediaType": 4, "isDir": True}],
        {parent: listing},
    )
    _assert(len(batches) == 2, batches)
    first = album_delete_payload(batches[0])
    _assert([item["filePath"] for item in first["datas"]] == [
        f"{parent}/{pane1}/stacked.jpg",
        f"{parent}/{pane2}/stacked.jpg",
    ], first)
    _assert([item["fileName"] for item in first["datas"]] == [pane1, pane2], first)
    second = album_delete_payload(batches[1])
    _assert(second["datas"] == [{
        "mediaType": 4,
        "filePath": f"{parent}/stacked.jpg",
        "fileName": "M31 mosaic",
        "subType": 0,
    }], second)


def test_session_without_subfolders_stays_one_delete() -> None:
    folder = "/DWARF3/Astronomy/DWARF_RAW_TELE_M31_2026-09-20"
    listing = [
        {"name": "stacked.jpg", "is_dir": False},
        {"name": "stacked_thumbnail.jpg", "is_dir": False},
        {"name": "Thumbnail", "is_dir": True},
        {"name": "notes", "is_dir": True},
    ]
    batches = album_delete_batches(
        [{
            "filePath": folder,
            "fileName": "DWARF_RAW_TELE_M31_2026-09-20",
            "mediaType": 4,
            "isDir": True,
        }],
        {folder: listing},
    )
    _assert(len(batches) == 1, batches)
    payload = album_delete_payload(batches[0])
    _assert(payload["datas"] == [{
        "mediaType": 4,
        "filePath": f"{folder}/stacked.jpg",
        "fileName": "DWARF_RAW_TELE_M31_2026-09-20",
        "subType": 0,
    }], payload)


def test_category_and_root_are_not_walked() -> None:
    listing = [{"name": "DWARF_RAW_TELE_M31", "is_dir": True}]
    _assert(album_delete_walk_path("/DWARF3/Astronomy") == "", "category")
    _assert(album_delete_walk_path("/DWARF3") == "", "root")
    batches = album_delete_batches(
        [{"filePath": "/DWARF3/Astronomy", "fileName": "Astronomy", "isDir": True}],
        {"/DWARF3/Astronomy": listing},
    )
    _assert(len(batches) == 1, batches)
    _assert(album_delete_payload(batches[0])["datas"] == [], batches)


def test_panorama_tile_folders_stay_with_the_session() -> None:
    parent = "/DWARF3/Panorama/PANO_1"
    listing = [
        {"name": "1", "is_dir": True},
        {"name": "2", "is_dir": True},
        {"name": "pano_thumbnail.jpg", "is_dir": False},
    ]
    batches = album_delete_batches(
        [{"filePath": parent, "fileName": "PANO_1", "mediaType": 5, "isDir": True}],
        {parent: listing},
    )
    _assert(len(batches) == 1, batches)
    payload = album_delete_payload(batches[0])
    _assert(payload["datas"] == [{
        "mediaType": 5,
        "filePath": f"{parent}/pano_thumbnail.jpg",
        "fileName": "PANO_1",
        "subType": 0,
    }], payload)


def test_photo_delete_is_unchanged_without_a_listing() -> None:
    item = {"filePath": "/DWARF3/Normal_Photos/shot.jpg", "fileName": "shot.jpg", "mediaType": 1}
    _assert(album_delete_batches([item], {}) == [[item]], "photo stays one batch")


def test_ignored_media_type_has_no_is_success() -> None:
    outcome = album_delete_outcome(
        {
            "code": 0,
            "data": [{"fileName": "DOES_NOT_EXIST_SESSION", "filePath": "/x", "mediaType": 6}],
        },
        1,
    )
    _assert(outcome["deleted"] == [], outcome)
    _assert(outcome["failed"] == 1, outcome)


if __name__ == "__main__":
    test_photo_folder_row_uses_firmware_type_and_category_name()
    test_photo_album_row_keeps_firmware_fields()
    test_astro_folder_maps_to_stacked_album_item()
    test_astro_file_inside_session_deletes_the_session()
    test_video_keeps_type_and_file_name()
    test_empty_list_is_still_object_body()
    test_folder_paths_infer_photo_and_astro_types()
    test_astronomy_category_is_not_a_session()
    test_category_folders_are_not_sent_to_firmware()
    test_burst_folder_maps_to_first_frame()
    test_firmware_is_success_false_is_still_accepted()
    test_mosaic_folder_deletes_pane_subfolders_first()
    test_session_without_subfolders_stays_one_delete()
    test_category_and_root_are_not_walked()
    test_panorama_tile_folders_stay_with_the_session()
    test_photo_delete_is_unchanged_without_a_listing()
    test_ignored_media_type_has_no_is_success()
    print("ok")
