import unittest

from astro_dwarf.domain import (
    album_apply_listing_preview,
    album_http_url,
    album_join_path,
    album_listing_names,
    album_media_kind,
    album_needs_preview_check,
    album_preview_name,
    album_session_dir,
)

EMPTY_BURST_INDEX = """<html>
<head><title>Index of /DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702/</title></head>
<body>
<h1>Index of /DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702/</h1><hr><pre><a href="../">../</a>
</pre><hr></body>
</html>
"""

INTACT_BURST_INDEX = """<html>
<head><title>Index of /DWARF3/Burst/DWARF3_TELE_BURST_2026-09-12-23-27-25-972/</title></head>
<body>
<h1>Index of /DWARF3/Burst/DWARF3_TELE_BURST_2026-09-12-23-27-25-972/</h1><hr><pre><a href="../">../</a>
<a href="0.jpg">0.jpg</a>
<a href="1.jpg">1.jpg</a>
<a href="burst_thumbnail.jpg">burst_thumbnail.jpg</a>
</pre><hr></body>
</html>
"""


class AlbumPreviewTests(unittest.TestCase):
    def test_burst_kind_from_path_and_type(self) -> None:
        path = "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702/0.jpg"
        self.assertEqual(album_media_kind(path, "DWARF3_TELE_BURST_2026-09-07-06-43-33-702", 3), "burst")
        self.assertTrue(album_needs_preview_check(path, "session", 3))
        self.assertFalse(album_needs_preview_check(
            "/DWARF3/Normal_Photos/DWARF3_WIDE_2026-09-13.jpg",
            "Normal_Photos",
            1,
        ))

    def test_session_dir_strips_image_name(self) -> None:
        self.assertEqual(
            album_session_dir("/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702/burst_thumbnail.jpg"),
            "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702",
        )
        self.assertEqual(
            album_join_path("/DWARF3/Burst/session", "burst_thumbnail.jpg"),
            "/DWARF3/Burst/session/burst_thumbnail.jpg",
        )

    def test_listing_prefers_burst_thumbnail(self) -> None:
        names = album_listing_names(INTACT_BURST_INDEX)
        self.assertEqual(names, ["0.jpg", "1.jpg", "burst_thumbnail.jpg"])
        self.assertEqual(album_preview_name(names), "burst_thumbnail.jpg")

    def test_empty_burst_listing_has_no_preview(self) -> None:
        names = album_listing_names(EMPTY_BURST_INDEX)
        self.assertEqual(names, [])
        self.assertEqual(album_preview_name(names), "")
        entry = album_apply_listing_preview(
            {
                "fileName": "DWARF3_TELE_BURST_2026-09-07-06-43-33-702",
                "filePath": "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702/0.jpg",
                "thumbnailPath": "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702/burst_thumbnail.jpg",
                "mediaType": 3,
            },
            names,
        )
        self.assertEqual(entry["thumbnailPath"], "")
        self.assertFalse(entry["fileAvailable"])
        self.assertEqual(
            entry["filePath"],
            "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-07-06-43-33-702/0.jpg",
        )

    def test_intact_burst_keeps_thumbnail(self) -> None:
        entry = album_apply_listing_preview(
            {
                "fileName": "DWARF3_TELE_BURST_2026-09-12-23-27-25-972",
                "filePath": "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-12-23-27-25-972/0.jpg",
                "thumbnailPath": "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-12-23-27-25-972/burst_thumbnail.jpg",
                "mediaType": 3,
            },
            album_listing_names(INTACT_BURST_INDEX),
        )
        self.assertEqual(
            entry["thumbnailPath"],
            "/DWARF3/Burst/DWARF3_TELE_BURST_2026-09-12-23-27-25-972/burst_thumbnail.jpg",
        )
        self.assertTrue(entry["fileAvailable"])
        self.assertTrue(album_http_url("192.168.1.42", entry["thumbnailPath"]).endswith("/burst_thumbnail.jpg"))

    def test_falls_back_to_first_frame_when_thumb_missing(self) -> None:
        entry = album_apply_listing_preview(
            {
                "filePath": "/DWARF3/Burst/session/0.jpg",
                "thumbnailPath": "/DWARF3/Burst/session/burst_thumbnail.jpg",
                "mediaType": 3,
            },
            ["0.jpg", "1.jpg"],
        )
        self.assertEqual(entry["thumbnailPath"], "/DWARF3/Burst/session/0.jpg")
        self.assertTrue(entry["fileAvailable"])


if __name__ == "__main__":
    unittest.main()
