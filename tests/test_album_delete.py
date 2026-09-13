import tempfile
import unittest
from pathlib import Path

from astro_dwarf.domain import album_delete_payload, album_local_file_in_dir


class AlbumDeletePayloadTests(unittest.TestCase):
    def test_wraps_items_in_datas(self) -> None:
        payload = album_delete_payload([
            {
                "file_path": "/DWARF3/Astronomy-M31/stacked.jpg",
                "file_name": "stacked.jpg",
                "media_type": 6,
                "sub_type": 1,
            }
        ])
        self.assertEqual(list(payload.keys()), ["datas"])
        self.assertEqual(payload["datas"], [{
            "mediaType": 6,
            "filePath": "/DWARF3/Astronomy-M31/stacked.jpg",
            "fileName": "stacked.jpg",
            "subType": 1,
        }])

    def test_skips_empty_paths_and_uses_parent_folder_name(self) -> None:
        payload = album_delete_payload([
            {"filePath": ""},
            {"filePath": "/DWARF3/Normal_Photos/shot.jpg"},
        ])
        self.assertEqual(payload["datas"], [{
            "mediaType": 0,
            "filePath": "/DWARF3/Normal_Photos/shot.jpg",
            "fileName": "Normal_Photos",
            "subType": 0,
        }])

    def test_empty_list_is_still_object_body(self) -> None:
        self.assertEqual(album_delete_payload([]), {"datas": []})
        self.assertEqual(album_delete_payload(None), {"datas": []})


class AlbumLocalFileInDirTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.album = Path(self._temp.name)
        self.inside = self.album / "stack.jpg"
        self.inside.write_bytes(b"jpeg")

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_accepts_files_inside_the_album_dir(self) -> None:
        self.assertEqual(album_local_file_in_dir(self.album, str(self.inside)), self.inside.resolve())
        self.assertEqual(album_local_file_in_dir(self.album, "stack.jpg"), self.inside.resolve())

    def test_rejects_missing_outside_and_unsupported_files(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other) / "secret.jpg"
            outside.write_bytes(b"jpeg")
            self.assertIsNone(album_local_file_in_dir(self.album, str(outside)))
        self.assertIsNone(album_local_file_in_dir(self.album, "../secret.jpg"))
        self.assertIsNone(album_local_file_in_dir(self.album, "missing.jpg"))
        other = self.album / "notes.txt"
        other.write_text("nope", encoding="utf-8")
        self.assertIsNone(album_local_file_in_dir(self.album, str(other)))


if __name__ == "__main__":
    unittest.main()
