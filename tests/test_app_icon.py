import unittest
from pathlib import Path

from astro_dwarf.app import _app_icon, _app_icon_candidates

ROOT = Path(__file__).resolve().parent.parent


class AppIconCandidateTests(unittest.TestCase):
    def test_frozen_looks_in_bundled_assets_and_meipass(self) -> None:
        resources = Path("/bundle")
        meipass = Path("/bundle")
        source = Path("/src")
        exe = Path("/bundle/AstroDwarf.exe")
        paths = _app_icon_candidates(
            resources,
            frozen=True,
            executable=exe,
            meipass=meipass,
            source_root=source,
        )
        self.assertIn(resources / "qml" / "assets" / "astro-dwarf.ico", paths)
        self.assertIn(resources / "qml" / "assets" / "astro-dwarf.png", paths)
        self.assertIn(meipass / "astro-dwarf.ico", paths)
        self.assertIn(meipass / "astro-dwarf.png", paths)
        self.assertIn(source / "packaging" / "icons" / "astro-dwarf.ico", paths)
        self.assertEqual(paths[-1], exe)

    def test_source_keeps_packaging_icons_and_skips_exe(self) -> None:
        resources = Path("/src/astro_dwarf")
        source = Path("/src")
        paths = _app_icon_candidates(
            resources,
            frozen=False,
            executable=Path("/Python/python.exe"),
            meipass=Path("/unused"),
            source_root=source,
        )
        self.assertIn(resources / "qml" / "assets" / "astro-dwarf.png", paths)
        self.assertIn(source / "packaging" / "icons" / "astro-dwarf.ico", paths)
        self.assertTrue(all(path.suffix.lower() != ".exe" for path in paths))

    def test_packaged_asset_icon_loads(self) -> None:
        from PySide6.QtGui import QGuiApplication

        from astro_dwarf.runtime import package_root

        QGuiApplication.instance() or QGuiApplication([])
        icon = _app_icon(package_root())
        self.assertFalse(icon.isNull())
        self.assertTrue(any(size.width() > 0 for size in icon.availableSizes()))

    def test_linux_desktop_file_matches_icon_name(self) -> None:
        lines = (ROOT / "packaging" / "linux" / "astro-dwarf.desktop").read_text(encoding="utf-8").splitlines()
        self.assertIn("Icon=astro-dwarf", lines)
        self.assertIn("StartupWMClass=astro-dwarf", lines)

    def test_linux_packages_install_standard_icon_sizes(self) -> None:
        nfpm = (ROOT / "packaging" / "linux" / "nfpm.yaml").read_text(encoding="utf-8")
        self.assertIn("packaging/icons/hicolor", nfpm)
        self.assertIn("/usr/share/pixmaps/astro-dwarf.png", nfpm)
        self.assertNotIn("1024x1024", nfpm)
        self.assertTrue((ROOT / "packaging" / "linux" / "postinstall.sh").is_file())


if __name__ == "__main__":
    unittest.main()
