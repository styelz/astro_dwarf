import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from astro_dwarf.runtime import package_root

PROBE_QML = """
import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "components"

Window {
    id: root
    width: 720
    height: 480
    visible: true
    color: "#111"
    objectName: "layoutProbe"

    function idsOf(split) {
        const ids = []
        for (let i = 0; i < split.count; i++) {
            const it = split.itemAt(i)
            if (it && it.panelId)
                ids.push(it.panelId)
        }
        return ids.join(",")
    }

    function snapshot() {
        return idsOf(left) + "|" + idsOf(center) + "|" + idsOf(right)
    }

    function moveAIntoCenter() {
        PanelSwap.insertPanel(panelA, panelC, true)
        return snapshot()
    }

    function persistRestore() {
        const saved = snapshot()
        const ok = PanelSwap.persist()
        const json = PanelSwap.store.panelOrderJson
        PanelSwap.insertPanel(panelA, panelB, false)
        const scrambled = snapshot()
        PanelSwap.store.panelOrderJson = json
        const restored = PanelSwap.restore()
        return saved + ">" + scrambled + ">" + snapshot() + ">" + ok + ":" + restored
    }

    function resetLayout() {
        PanelSwap.resetToDefault()
        return snapshot()
    }

    function sizes() {
        return Math.round(left.width) + "," + Math.round(panelA.height)
    }

    function sizeRatios() {
        const colW = Math.max(1, columns.width)
        const leftH = Math.max(1, left.height)
        return (left.width / colW) + "," + (panelA.height / leftH)
    }

    function captureLocks() {
        columns.captureLocked()
        left.captureLocked()
        center.captureLocked()
        right.captureLocked()
    }

    function setNonFill(lw, ah) {
        left.SplitView.preferredWidth = lw
        panelA.SplitView.preferredHeight = ah
        columns.captureLocked()
        left.captureLocked()
        columns.applyLocked()
        left.applyLocked()
    }

    function corruptNonFill(lw, ah) {
        left.SplitView.preferredWidth = lw
        panelA.SplitView.preferredHeight = ah
    }

    HudSplitView {
        id: columns
        settingsKey: "controlColumns"
        autoRestore: false
        anchors.fill: parent
        orientation: Qt.Horizontal

        HudSplitView {
            id: left
            settingsKey: "controlLeft"
            autoRestore: false
            SplitView.preferredWidth: 180
            orientation: Qt.Vertical
            HudPanel { id: panelA; panelId: "a"; title: "A"; SplitView.preferredHeight: 120; SplitView.minimumHeight: 40 }
            HudPanel { id: panelB; panelId: "b"; title: "B"; SplitView.fillHeight: true; SplitView.minimumHeight: 40 }
        }
        HudSplitView {
            id: center
            settingsKey: "controlCenter"
            autoRestore: false
            SplitView.fillWidth: true
            orientation: Qt.Vertical
            HudPanel { id: panelC; panelId: "c"; title: "C"; SplitView.fillHeight: true; SplitView.minimumHeight: 40 }
        }
        HudSplitView {
            id: right
            settingsKey: "controlRight"
            autoRestore: false
            SplitView.preferredWidth: 180
            orientation: Qt.Vertical
            HudPanel { id: panelD; panelId: "d"; title: "D"; SplitView.fillHeight: true; SplitView.minimumHeight: 40 }
            HudPanel { visible: false; title: "hidden"; SplitView.preferredHeight: 0; SplitView.maximumHeight: 0 }
        }
    }

    Component.onCompleted: {
        PanelSwap.host = root.contentItem
        PanelSwap.registerSplit(columns)
        PanelSwap.registerSplit(left)
        PanelSwap.registerSplit(center)
        PanelSwap.registerSplit(right)
        PanelSwap.store.panelOrderJson = ""
        PanelSwap.captureDefaults()
    }
}
"""


def _app():
    QCoreApplication.setOrganizationName("AstroDwarfPanelLayoutTest")
    QCoreApplication.setApplicationName("PanelLayoutTest")
    return QGuiApplication.instance() or QGuiApplication([])


class PanelLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
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
            raise RuntimeError("panel layout probe failed to load: " + " | ".join(warnings))
        cls.win = cls.engine.rootObjects()[0]
        cls.warnings = warnings

    def setUp(self):
        self.win.setWidth(720)
        self.win.setHeight(480)
        if self.win.snapshot() != "a,b|c|d":
            self.win.resetLayout()
        self.assertEqual(self.win.snapshot(), "a,b|c|d")

    def test_qml_loads_clean(self):
        unexpected = [w for w in self.warnings if "SplitView state" in w or "Keys property" in w]
        self.assertEqual(unexpected, [])

    def test_insert_across_columns_round_trips(self):
        self.assertEqual(self.win.snapshot(), "a,b|c|d")
        self.assertEqual(self.win.moveAIntoCenter(), "b|c,a|d")
        result = str(self.win.persistRestore())
        self.assertEqual(result, "b|c,a|d>a,b|c|d>b|c,a|d>true:true")

    def test_reset_restores_stock_order(self):
        self.assertEqual(self.win.moveAIntoCenter(), "b|c,a|d")
        self.assertEqual(self.win.resetLayout(), "a,b|c|d")
        menu = self.win.findChild(QQuickItem, "resetControlLayout")
        self.assertIsNotNone(menu)

    def _parse_ratios(self):
        parts = str(self.win.sizeRatios()).split(",")
        return float(parts[0]), float(parts[1])

    def _parse_sizes(self):
        parts = str(self.win.sizes()).split(",")
        return int(parts[0]), int(parts[1])

    def _assert_ratios_close(self, actual, expected, tol=0.02):
        self.assertAlmostEqual(actual[0], expected[0], delta=tol, msg=f"width ratio {actual[0]} vs {expected[0]}")
        self.assertAlmostEqual(actual[1], expected[1], delta=tol, msg=f"height ratio {actual[1]} vs {expected[1]}")

    def _assert_sizes_close(self, actual, expected, tol=4):
        self.assertAlmostEqual(actual[0], expected[0], delta=tol, msg=f"width {actual[0]} vs {expected[0]}")
        self.assertAlmostEqual(actual[1], expected[1], delta=tol, msg=f"height {actual[1]} vs {expected[1]}")

    def test_pane_ratios_survive_window_resize(self):
        self.win.setNonFill(220, 180)
        QTest.qWait(80)
        self.win.captureLocks()
        original = self._parse_sizes()
        self._assert_sizes_close(original, (220, 180))
        ratios = self._parse_ratios()
        self.win.setWidth(1400)
        self.win.setHeight(900)
        QTest.qWait(80)
        grown = self._parse_sizes()
        self.assertGreater(grown[0], original[0] + 20)
        self.assertGreater(grown[1], original[1] + 20)
        self._assert_ratios_close(self._parse_ratios(), ratios)
        self.win.setWidth(720)
        self.win.setHeight(480)
        QTest.qWait(80)
        self._assert_sizes_close(self._parse_sizes(), original)
        self._assert_ratios_close(self._parse_ratios(), ratios)
        self.win.setWidth(1400)
        self.win.setHeight(900)
        QTest.qWait(80)
        self._assert_ratios_close(self._parse_ratios(), ratios)
        self.win.setWidth(720)
        self.win.setHeight(480)
        QTest.qWait(80)
        self._assert_sizes_close(self._parse_sizes(), original)

    def test_splitter_drag_ratios_survive_grow(self):
        self.win.setNonFill(220, 180)
        QTest.qWait(80)
        self.win.captureLocks()
        first = self._parse_ratios()
        self.win.setWidth(1400)
        self.win.setHeight(900)
        QTest.qWait(80)
        self._assert_ratios_close(self._parse_ratios(), first)
        self.win.setNonFill(300, 220)
        QTest.qWait(80)
        self.win.captureLocks()
        dragged = self._parse_ratios()
        self.assertGreater(abs(dragged[0] - first[0]), 0.01)
        self.win.setWidth(720)
        self.win.setHeight(480)
        QTest.qWait(80)
        self._assert_ratios_close(self._parse_ratios(), dragged)
        self.win.setWidth(1600)
        self.win.setHeight(1000)
        QTest.qWait(80)
        self._assert_ratios_close(self._parse_ratios(), dragged)

    def test_locked_ratios_reapplied_after_preferred_corruption(self):
        self.win.setNonFill(220, 180)
        QTest.qWait(80)
        self.win.captureLocks()
        original = self._parse_sizes()
        ratios = self._parse_ratios()
        self.win.corruptNonFill(360, 260)
        QTest.qWait(30)
        self.win.setWidth(1400)
        self.win.setHeight(900)
        QTest.qWait(80)
        grown = self._parse_sizes()
        self.assertNotAlmostEqual(grown[0], 360, delta=8)
        self._assert_ratios_close(self._parse_ratios(), ratios)
        self.win.setWidth(720)
        self.win.setHeight(480)
        QTest.qWait(80)
        self._assert_sizes_close(self._parse_sizes(), original)


if __name__ == "__main__":
    unittest.main()
