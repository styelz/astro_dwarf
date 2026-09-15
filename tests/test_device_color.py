import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import Property, QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

from astro_dwarf.domain import (
    DEVICE_COLORS,
    Device,
    device_from_dict,
    next_device_color,
    normalize_device_color,
    parse_device_color,
    to_dict,
)
from astro_dwarf.runtime import package_root

PROBE_QML = """
import QtQuick
import QtQuick.Controls
import "."
import "components"

ApplicationWindow {
    id: root
    objectName: "probeWindow"
    width: 640
    height: 200
    visible: true
    color: "#111"
    property alias colorHex: colorField.colorHex

    function setPreset(hex) {
        colorField.setHex(hex)
        return colorField.colorHex
    }

    function unusedOf(used) {
        colorField.assignUnused(used)
        return colorField.colorHex
    }

    DeviceColorField {
        id: colorField
        anchors.centerIn: parent
        width: 420
        height: 34
    }
}
"""


class _StubBackend(QObject):
    @Property("QVariantList", constant=True)
    def deviceColorPresets(self) -> list[str]:
        return list(DEVICE_COLORS)

    @Property("QVariantList", constant=True)
    def devices(self) -> list[dict[str, str]]:
        return [{"color": DEVICE_COLORS[0]}]

    @Property(QObject, constant=True)
    def screenColor(self) -> QObject | None:
        return None


def _app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])



class DeviceColorTests(unittest.TestCase):
    def test_parse_accepts_short_and_long_hex(self) -> None:
        self.assertEqual(parse_device_color("#62a0ff"), "#62A0FF")
        self.assertEqual(parse_device_color("e87"), "#EE8877")
        self.assertEqual(parse_device_color("not-a-color"), "")

    def test_normalize_falls_back(self) -> None:
        self.assertEqual(normalize_device_color(""), DEVICE_COLORS[0])
        self.assertEqual(normalize_device_color("nope", "#6C8CFF"), "#6C8CFF")
        self.assertEqual(normalize_device_color("  #fb7185  "), "#FB7185")

    def test_next_color_skips_used_presets(self) -> None:
        self.assertEqual(next_device_color([]), DEVICE_COLORS[0])
        self.assertEqual(next_device_color([DEVICE_COLORS[0]]), DEVICE_COLORS[1])
        self.assertEqual(next_device_color(DEVICE_COLORS), DEVICE_COLORS[0])

    def test_device_roundtrip_keeps_custom_color(self) -> None:
        original = Device(name="Yard", color="#C45C26")
        loaded = device_from_dict(to_dict(original))
        self.assertEqual(loaded.color, "#C45C26")

    def test_missing_color_keeps_device_default(self) -> None:
        loaded = device_from_dict({"name": "Dwarf 3"})
        self.assertEqual(loaded.color, Device.__dataclass_fields__["color"].default)


class DeviceColorFieldQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.app.setApplicationName("Astro Dwarf")
        cls.app.setOrganizationName("Astro Dwarf")
        qml_dir = package_root() / "qml"
        cls.backend = _StubBackend()
        cls.engine = QQmlApplicationEngine()
        cls.engine.addImportPath(str(qml_dir))
        cls.engine.rootContext().setContextProperty("backend", cls.backend)
        warnings = []
        cls.engine.warnings.connect(lambda batch: warnings.extend(str(w.toString()) for w in batch))
        cls.engine.loadData(
            PROBE_QML.encode("utf-8"),
            QUrl.fromLocalFile(str(qml_dir / "probe.qml")),
        )
        QTest.qWait(100)
        if not cls.engine.rootObjects():
            raise RuntimeError("device colour field probe failed to load: " + " | ".join(warnings))
        cls.win = cls.engine.rootObjects()[0]
        cls.warnings = warnings

    def test_qml_loads_clean(self):
        self.assertFalse(self.warnings)

    def test_set_hex_normalizes(self) -> None:
        self.assertEqual(self.win.setPreset("#fb7185"), "#FB7185")
        self.assertEqual(self.win.property("colorHex"), "#FB7185")

    def test_assign_unused_skips_taken_preset(self) -> None:
        self.assertEqual(self.win.unusedOf([DEVICE_COLORS[0]]), DEVICE_COLORS[1])


if __name__ == "__main__":
    unittest.main()
