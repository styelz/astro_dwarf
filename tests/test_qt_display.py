import os
import unittest

from astro_dwarf.qt_display import (
    apply_software_qt_env,
    configure_qt_display,
    needs_software_qt,
)


class NeedsSoftwareQtTests(unittest.TestCase):
    def test_frozen_linux_needs_software(self) -> None:
        self.assertTrue(
            needs_software_qt(
                os_name="posix",
                platform="linux",
                frozen=True,
                wsl=False,
                system_qt=False,
            )
        )

    def test_source_linux_keeps_host_gl(self) -> None:
        self.assertFalse(
            needs_software_qt(
                os_name="posix",
                platform="linux",
                frozen=False,
                wsl=False,
                system_qt=False,
            )
        )

    def test_wsl_needs_software_even_from_source(self) -> None:
        self.assertTrue(
            needs_software_qt(
                os_name="posix",
                platform="linux",
                frozen=False,
                wsl=True,
                system_qt=False,
            )
        )

    def test_system_qt_opt_out(self) -> None:
        self.assertFalse(
            needs_software_qt(
                os_name="posix",
                platform="linux",
                frozen=True,
                wsl=True,
                system_qt=True,
            )
        )

    def test_windows_and_macos_frozen_keep_host_gl(self) -> None:
        self.assertFalse(
            needs_software_qt(
                os_name="nt",
                platform="win32",
                frozen=True,
                wsl=False,
                system_qt=False,
            )
        )
        self.assertFalse(
            needs_software_qt(
                os_name="posix",
                platform="darwin",
                frozen=True,
                wsl=False,
                system_qt=False,
            )
        )


class ConfigureQtDisplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in (
                "QT_QPA_PLATFORM",
                "QT_XCB_GL_INTEGRATION",
                "QT_QUICK_BACKEND",
                "QSG_RHI_BACKEND",
                "ASTRO_DWARF_QT_SYSTEM",
            )
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_apply_software_qt_env_fills_defaults(self) -> None:
        apply_software_qt_env()
        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "xcb")
        self.assertEqual(os.environ["QT_XCB_GL_INTEGRATION"], "none")
        self.assertEqual(os.environ["QT_QUICK_BACKEND"], "software")
        self.assertEqual(os.environ["QSG_RHI_BACKEND"], "software")

    def test_apply_software_qt_env_preserves_existing(self) -> None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        apply_software_qt_env()
        self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")

    def test_configure_respects_system_qt_opt_out(self) -> None:
        os.environ["ASTRO_DWARF_QT_SYSTEM"] = "1"
        configure_qt_display()
        self.assertNotIn("QT_QUICK_BACKEND", os.environ)


if __name__ == "__main__":
    unittest.main()
