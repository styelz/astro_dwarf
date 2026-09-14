import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from astro_dwarf.runtime import package_root

PROBE_QML = """
import QtQuick
import QtQuick.Controls
import "."
import "dialogs"

ApplicationWindow {
    id: root
    objectName: "probeWindow"
    width: 640
    height: 480
    visible: true
    color: "#111"
    property string acceptedHex: ""
    property bool opened: colourPick.visible
    property bool pickerModal: colourPick.modal

    function openPick(hex) {
        colourPick.roleName = "ACCENT"
        colourPick.selectedColor = hex
        colourPick.open()
        return colourPick.currentHex
    }

    function currentHex() {
        return colourPick.currentHex
    }

    function planePick(nx, ny) {
        colourPick.pickAtNorm(nx, ny)
        return colourPick.currentHex
    }

    function huePick(ny) {
        colourPick.pickHueNorm(ny)
        return colourPick.currentHex
    }

    function applyPick() {
        colourPick.commit()
        return root.acceptedHex
    }

    ColorPickDialog {
        id: colourPick
        onAccepted: root.acceptedHex = colourPick.currentHex
    }
}
"""


def _app():
    return QGuiApplication.instance() or QGuiApplication([])


def _window_pos(item: QQuickItem, fx: float = 0.5, fy: float = 0.5) -> QPoint:
    pt = item.mapToScene(QPointF(item.width() * fx, item.height() * fy))
    return QPoint(int(pt.x()), int(pt.y()))


class ColorPickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        cls.app.setApplicationName("Astro Dwarf")
        cls.app.setOrganizationName("Astro Dwarf")
        qml_dir = package_root() / "qml"
        cls.engine = QQmlApplicationEngine()
        cls.engine.addImportPath(str(qml_dir))
        warnings = []
        cls.engine.warnings.connect(lambda batch: warnings.extend(str(w.toString()) for w in batch))
        cls.engine.loadData(
            PROBE_QML.encode("utf-8"),
            QUrl.fromLocalFile(str(qml_dir / "probe.qml")),
        )
        QTest.qWait(100)
        if not cls.engine.rootObjects():
            raise RuntimeError("colour pick probe failed to load: " + " | ".join(warnings))
        cls.win = cls.engine.rootObjects()[0]
        cls.warnings = warnings

    def setUp(self):
        pick = self.win.findChild(QQuickItem, "colourPick")
        if pick is not None and bool(pick.property("visible")):
            pick.setProperty("visible", False)
            QTest.qWait(30)
        self.win.setProperty("acceptedHex", "")

    def test_qml_loads_clean(self):
        self.assertFalse(self.warnings)
        joined = " ".join(self.warnings)
        self.assertNotIn("Keys property", joined)

    def test_picker_is_modal_with_eyedropper(self):
        self.assertTrue(bool(self.win.property("pickerModal")))
        sample = self.win.findChild(QQuickItem, "colourSample")
        self.assertIsNotNone(sample)
        self.assertEqual(str(sample.property("text")), "DROP")

    def test_clicking_the_plane_changes_colour(self):
        self.win.openPick("#333333")
        QTest.qWait(80)
        self.assertTrue(self.win.property("opened"))
        start = str(self.win.currentHex())
        plane = self.win.findChild(QQuickItem, "colourPlane")
        self.assertIsNotNone(plane)
        self.assertGreater(plane.width(), 20)
        self.assertGreater(plane.height(), 20)
        window = plane.window()
        QTest.mouseClick(
            window,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            _window_pos(plane, 0.9, 0.1),
        )
        QTest.qWait(50)
        current = str(self.win.currentHex())
        self.assertNotEqual(current, start)
        self.assertNotEqual(current, "#333333")
        self.assertTrue(current.startswith("#"))
        self.assertEqual(len(current), 7)

    def test_apply_commits_selected_colour(self):
        self.win.openPick("#111111")
        QTest.qWait(50)
        hex_value = self.win.planePick(0.85, 0.15)
        applied = self.win.applyPick()
        QTest.qWait(30)
        self.assertEqual(applied, hex_value)
        self.assertNotEqual(applied, "#111111")

    def test_hue_strip_changes_colour(self):
        self.win.openPick("#00A8C6")
        QTest.qWait(50)
        before = str(self.win.planePick(0.9, 0.2))
        after = str(self.win.huePick(0.08))
        self.assertNotEqual(after, before)


if __name__ == "__main__":
    unittest.main()
