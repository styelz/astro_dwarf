import unittest

from astro_dwarf.image_enhance import enhance_cache_key, enhance_levels, set_enhance_levels


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


if __name__ == "__main__":
    unittest.main()
