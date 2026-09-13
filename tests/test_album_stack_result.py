import unittest

from astro_dwarf.domain import (
    album_is_stack_display_image,
    album_stack_image_name,
    album_stack_result_path,
    album_stack_session_camera,
    album_stack_session_target,
    choose_latest_astro_stack,
)


def _session(
    *,
    name: str = "DWARF3_TELE_2026-09-13",
    file_path: str = "/DWARF3/Astronomy/DWARF3_TELE_2026-09-13/stacked.jpg",
    thumb: str = "",
    target: str = "",
    cam_id: int | None = 0,
    mtime: int = 1_000,
) -> dict:
    entry: dict = {
        "fileName": name,
        "filePath": file_path,
        "thumbnailPath": thumb,
        "mediaType": 6,
        "modificationTime": mtime,
    }
    if cam_id is not None:
        entry["camId"] = cam_id
    if target:
        entry["astroImageDetails"] = {"target": target}
    return entry


class AlbumStackResultTests(unittest.TestCase):
    def test_display_image_skips_fits_and_tiff(self) -> None:
        self.assertTrue(album_is_stack_display_image("stacked.jpg"))
        self.assertTrue(album_is_stack_display_image("/session/stacked.PNG"))
        self.assertFalse(album_is_stack_display_image("stacked.fits"))
        self.assertFalse(album_is_stack_display_image("stacked.tif"))

    def test_folder_listing_prefers_stacked_jpeg(self) -> None:
        self.assertEqual(
            album_stack_image_name(["0.jpg", "frame.fits", "stacked.jpg"]),
            "stacked.jpg",
        )
        self.assertEqual(
            album_stack_image_name(["0.jpg", "DWARF3_TELE_stacked.jpg", "frame.fits"]),
            "DWARF3_TELE_stacked.jpg",
        )
        self.assertEqual(album_stack_image_name(["stacked.fits", "0.jpg"]), "0.jpg")
        self.assertEqual(album_stack_image_name(["stacked.fits", "frame.fit"]), "")

    def test_result_path_prefers_jpeg_file_over_fits(self) -> None:
        entry = _session(
            file_path="/DWARF3/Astronomy/s/stacked.fits",
            thumb="/DWARF3/Astronomy/s/stacked.jpg",
        )
        self.assertEqual(album_stack_result_path(entry), "/DWARF3/Astronomy/s/stacked.jpg")
        self.assertEqual(
            album_stack_result_path(
                _session(file_path="/DWARF3/Astronomy/s/stacked.fits", thumb=""),
                ["stacked.fits", "stacked.jpg", "0.jpg"],
            ),
            "/DWARF3/Astronomy/s/stacked.jpg",
        )

    def test_target_and_camera_from_entry(self) -> None:
        tele = _session(target="M31", cam_id=0)
        wide = _session(
            name="DWARF3_WIDE_2026-09-13",
            file_path="/DWARF3/Astronomy/DWARF3_WIDE_2026-09-13/stacked.jpg",
            cam_id=1,
        )
        self.assertEqual(album_stack_session_target(tele), "M31")
        self.assertEqual(album_stack_session_camera(tele), "tele")
        self.assertEqual(album_stack_session_camera(wide), "wide")

    def test_choose_newest_matching_target_and_camera(self) -> None:
        older = _session(target="M31", mtime=100, file_path="/DWARF3/Astronomy/old/stacked.jpg")
        newer = _session(target="M31", mtime=500, file_path="/DWARF3/Astronomy/new/stacked.jpg")
        other = _session(target="M42", mtime=900, file_path="/DWARF3/Astronomy/m42/stacked.jpg")
        wide = _session(
            target="M31",
            cam_id=1,
            mtime=800,
            file_path="/DWARF3/Astronomy/DWARF3_WIDE_2026/stacked.jpg",
        )
        chosen = choose_latest_astro_stack(
            [older, newer, other, wide],
            target="M31",
            camera="tele",
        )
        self.assertEqual(chosen, newer)

    def test_since_rejects_older_sessions(self) -> None:
        stale = _session(mtime=900)
        fresh = _session(
            name="DWARF3_TELE_fresh",
            file_path="/DWARF3/Astronomy/fresh/stacked.jpg",
            mtime=2000,
        )
        self.assertIsNone(choose_latest_astro_stack([stale], since=2000))
        self.assertEqual(choose_latest_astro_stack([stale, fresh], since=2000), fresh)

    def test_since_zero_picks_newest(self) -> None:
        older = _session(mtime=100)
        newer = _session(
            name="later",
            file_path="/DWARF3/Astronomy/later/stacked.jpg",
            mtime=400,
        )
        self.assertEqual(choose_latest_astro_stack([older, newer]), newer)


if __name__ == "__main__":
    unittest.main()
