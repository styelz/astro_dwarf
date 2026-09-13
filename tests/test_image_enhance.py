import tempfile
import unittest
from pathlib import Path

from PySide6.QtGui import QImage

from astro_dwarf.image_enhance import (
    enhance_cache_key,
    enhance_levels,
    is_enhance_cache_valid,
    set_enhance_levels,
)


class EnhanceLevelTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_enhance_levels(1.0, 1.0)

    def test_cache_key_includes_levels(self) -> None:
        set_enhance_levels(1.0, 1.0)
        full = enhance_cache_key("file:///tmp/stack.jpg", "std")
        set_enhance_levels(0.4, 0.8)
        scaled = enhance_cache_key("file:///tmp/stack.jpg", "std")
        self.assertNotEqual(full, scaled)
        self.assertEqual(enhance_levels(), (0.4, 0.8))


class EnhanceCacheValidTests(unittest.TestCase):
    def test_rejects_missing(self) -> None:
        self.assertFalse(is_enhance_cache_valid("/no/such/enhance-cache.jpg"))

    def test_accepts_display_sized_jpeg(self) -> None:
        image = QImage(400, 300, QImage.Format.Format_RGB888)
        image.fill(0)
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "cache.jpg"
            self.assertTrue(image.save(str(dest), "JPG", 90))
            self.assertTrue(is_enhance_cache_valid(dest))

    def test_rejects_oversize_jpeg(self) -> None:
        image = QImage(2000, 40, QImage.Format.Format_RGB888)
        image.fill(0)
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "full.jpg"
            self.assertTrue(image.save(str(dest), "JPG", 90))
            self.assertFalse(is_enhance_cache_valid(dest))


if __name__ == "__main__":
    unittest.main()
