from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from astro_dwarf.qt_fonts import (
    BUNDLED_ICON_FAMILY,
    HudFonts,
    apply_hud_fonts,
    bundled_font_dir,
    load_bundled_fonts,
    resolve_hud_fonts,
)


class ResolveHudFontsTests(unittest.TestCase):
    def test_bundled_icon_family_wins(self):
        fonts = resolve_hud_fonts(
            ["Liberation Sans", "Liberation Mono", "Astro Dwarf Icons"],
            probe_system=False,
        )
        self.assertEqual(fonts.ui, "Liberation Sans")
        self.assertEqual(fonts.mono, "Liberation Mono")
        self.assertEqual(fonts.icon, BUNDLED_ICON_FAMILY)
        self.assertTrue(fonts.has_icon_font)

    def test_missing_icon_does_not_claim_an_icon_font(self):
        fonts = resolve_hud_fonts(
            ["Segoe UI", "Cascadia Mono"],
            probe_system=False,
        )
        self.assertEqual(fonts.icon, "Segoe UI")
        self.assertFalse(fonts.has_icon_font)

    def test_apply_does_not_substitute_mdl2_onto_ui_sans(self):
        application = MagicMock()
        fonts = HudFonts(ui="Segoe UI", mono="Consolas", icon="Segoe UI", has_icon_font=False)
        with (
            patch("astro_dwarf.qt_fonts.load_bundled_fonts", return_value=[]),
            patch("PySide6.QtGui.QFont") as qfont_cls,
        ):
            qfont_cls.return_value = MagicMock()
            qfont_cls.StyleHint = MagicMock()
            qfont_cls.HintingPreference = MagicMock()
            qfont_cls.StyleStrategy = MagicMock()
            qfont_cls.StyleStrategy.PreferAntialias = 1
            qfont_cls.StyleStrategy.PreferNoShaping = 2
            apply_hud_fonts(application, fonts=fonts)
            names = [call.args[0] for call in qfont_cls.insertSubstitutions.call_args_list]
        self.assertIn("Segoe UI", names)
        self.assertIn("Cascadia Mono", names)
        self.assertNotIn("Segoe MDL2 Assets", names)
        self.assertNotIn("Segoe Fluent Icons", names)

    def test_apply_does_not_alias_mdl2_onto_another_face(self):
        application = MagicMock()
        fonts = HudFonts(
            ui="Liberation Sans",
            mono="Liberation Mono",
            icon=BUNDLED_ICON_FAMILY,
            has_icon_font=True,
        )
        with (
            patch("astro_dwarf.qt_fonts.load_bundled_fonts", return_value=[BUNDLED_ICON_FAMILY]),
            patch("PySide6.QtGui.QFont") as qfont_cls,
        ):
            qfont_cls.return_value = MagicMock()
            qfont_cls.StyleHint = MagicMock()
            qfont_cls.HintingPreference = MagicMock()
            qfont_cls.StyleStrategy = MagicMock()
            qfont_cls.StyleStrategy.PreferAntialias = 1
            qfont_cls.StyleStrategy.PreferNoShaping = 2
            apply_hud_fonts(application, fonts=fonts)
            names = [call.args[0] for call in qfont_cls.insertSubstitutions.call_args_list]
        self.assertIn("Segoe UI", names)
        self.assertIn("Cascadia Mono", names)
        self.assertNotIn("Segoe MDL2 Assets", names)
        self.assertNotIn("Segoe Fluent Icons", names)

    def test_no_shaping_is_linux_only(self):
        application = MagicMock()
        fonts = HudFonts(ui="Helvetica", mono="Menlo", icon="Helvetica", has_icon_font=False)

        def strategy_for(platform: str) -> int:
            with (
                patch("astro_dwarf.qt_fonts.sys.platform", platform),
                patch("astro_dwarf.qt_fonts.load_bundled_fonts", return_value=[]),
                patch("PySide6.QtGui.QFont") as qfont_cls,
            ):
                font = MagicMock()
                qfont_cls.return_value = font
                qfont_cls.StyleHint = MagicMock()
                qfont_cls.HintingPreference = MagicMock()
                qfont_cls.StyleStrategy = MagicMock()
                qfont_cls.StyleStrategy.PreferAntialias = 1
                qfont_cls.StyleStrategy.PreferNoShaping = 2
                apply_hud_fonts(application, fonts=fonts)
                return int(font.setStyleStrategy.call_args.args[0])

        self.assertEqual(strategy_for("linux"), 3)
        self.assertEqual(strategy_for("darwin"), 1)


class BundledIconFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtGui import QGuiApplication

        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_shipped_ttf_registers_and_covers_log_glyphs(self):
        from PySide6.QtGui import QFontDatabase, QRawFont
        import sys

        folder = bundled_font_dir()
        self.assertIsNotNone(folder)
        ttf = folder / "AstroDwarfIcons.ttf"
        self.assertTrue(ttf.is_file())
        raw = QRawFont(str(ttf), 16)
        self.assertTrue(raw.isValid())
        for code in (0xE71D, 0xE8CD, 0xE7BA, 0xE90F, 0xE8C8, 0xE74D, 0xE70D, 0xEF3C):
            self.assertTrue(raw.supportsCharacter(code), f"missing U+{code:04X}")
        families = load_bundled_fonts()
        if sys.platform == "win32":
            self.assertNotIn(BUNDLED_ICON_FAMILY, families)
            return
        self.assertIn(BUNDLED_ICON_FAMILY, families)
        live = resolve_hud_fonts()
        self.assertTrue(live.has_icon_font)
        self.assertEqual(live.icon, BUNDLED_ICON_FAMILY)
        self.assertTrue(QFontDatabase.hasFamily(BUNDLED_ICON_FAMILY))


if __name__ == "__main__":
    unittest.main()
