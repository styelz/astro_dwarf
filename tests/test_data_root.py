from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.runtime import data_root


class DataRootTests(unittest.TestCase):
    def test_source_checkout_honors_data_override(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "library"
            with patch.dict(os.environ, {"ASTRO_DWARF_DATA": str(target)}):
                with patch("astro_dwarf.runtime.is_frozen", return_value=False):
                    resolved = data_root()
            self.assertEqual(resolved, target)
            self.assertTrue(target.is_dir())

    def test_frozen_build_ignores_data_override(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {"ASTRO_DWARF_DATA": folder}):
                with patch("astro_dwarf.runtime.is_frozen", return_value=True):
                    with patch("astro_dwarf.runtime.QStandardPaths.writableLocation", return_value=""):
                        resolved = data_root()
            self.assertEqual(resolved, Path.home() / ".astro-dwarf")
            self.assertNotEqual(resolved, Path(folder))


if __name__ == "__main__":
    unittest.main()
