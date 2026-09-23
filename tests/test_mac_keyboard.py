from __future__ import annotations

import unittest
from pathlib import Path

from astro_dwarf.mac_keyboard import find_named_view

ROOT = Path(__file__).resolve().parents[1]


class MacKeyboardTests(unittest.TestCase):
    def test_finds_a_nested_web_view(self):
        tree = {
            "id": 1,
            "class": "QNSView",
            "kids": [
                {"id": 2, "class": "NSView", "kids": []},
                {"id": 3, "class": "NSView", "kids": [
                    {"id": 4, "class": "WKWebView", "kids": []},
                ]},
            ],
        }

        def children(node):
            return node["kids"]

        found = find_named_view(tree, "WKWebView", children=children, class_name=lambda node: node["class"])
        self.assertEqual(found["id"], 4)
        self.assertIsNone(find_named_view(tree, "Missing", children=children, class_name=lambda node: node["class"]))

    def test_text_entry_keeps_shaping_on_macos(self):
        main = (ROOT / "astro_dwarf" / "qml" / "Main.qml").read_text(encoding="utf-8")
        field = (ROOT / "astro_dwarf" / "qml" / "components" / "HudField.qml").read_text(encoding="utf-8")
        spin = (ROOT / "astro_dwarf" / "qml" / "components" / "HudSpinBox.qml").read_text(encoding="utf-8")
        self.assertIn('font.preferShaping: Qt.platform.os !== "linux"', main)
        self.assertNotIn("font.preferShaping: false", main)
        self.assertIn("font.preferShaping: true", field)
        self.assertIn("font.preferShaping: true", spin)
        self.assertIn("setMacWebViewTyping", main)


if __name__ == "__main__":
    unittest.main()
