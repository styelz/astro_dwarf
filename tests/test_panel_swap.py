import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

from PySide6.QtCore import QCoreApplication, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from astro_dwarf.runtime import package_root

PROBE_QML = """
import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "components"

Window {
    id: root
    width: 420
    height: 640
    visible: true
    color: "#111"
    objectName: "probeWindow"
    property string parentChain: ""
    property string afterIds: ""
    property bool swapOk: false
    property bool hoverHit: false

    HudSplitView {
        id: split
        objectName: "probeSplit"
        settingsKey: "probeSplit"
        anchors.fill: parent
        orientation: Qt.Vertical

        HudPanel {
            id: panelA
            objectName: "panelA"
            panelId: "a"
            title: "ALPHA"
            SplitView.preferredHeight: 220
            SplitView.minimumHeight: 80
            Text { text: "body A"; color: "#fff" }
        }
        HudPanel {
            id: panelB
            objectName: "panelB"
            panelId: "b"
            title: "BETA"
            SplitView.fillHeight: true
            SplitView.minimumHeight: 80
            Text { text: "body B"; color: "#fff" }
        }
        HudPanel {
            id: panelC
            objectName: "panelC"
            panelId: "c"
            title: "GAMMA"
            SplitView.preferredHeight: 120
            SplitView.minimumHeight: 60
            Text { text: "body C"; color: "#fff" }
        }
    }

    Component.onCompleted: {
        PanelSwap.host = root.contentItem
        PanelSwap.registerSplit(split)
        const names = []
        for (let n = panelA.parent; n; n = n.parent) {
            names.push(String(n) + " key=" + (n.settingsKey || "") + " add=" + !!(n.addItem))
        }
        parentChain = names.join(" || ")
    }

    function idsInSplit() {
        const ids = []
        for (let i = 0; i < split.count; i++) {
            const it = split.itemAt(i)
            ids.push(it && it.panelId ? it.panelId : "?")
        }
        return ids.join(",")
    }

    function swapAB() {
        PanelSwap.swapPanels(panelA, panelB)
        afterIds = idsInSplit()
        swapOk = afterIds === "b,a,c"
        return afterIds
    }

    function resetOrder() {
        const items = [panelA, panelB, panelC]
        for (let i = 0; i < items.length; i++) {
            const idx = PanelSwap.indexOfItem(split, items[i])
            if (idx >= 0 && idx !== i)
                split.moveItem(idx, i)
        }
        return idsInSplit()
    }

    function insertAAfterC() {
        PanelSwap.insertPanel(panelA, panelC, true)
        return idsInSplit()
    }

    function insertABeforeC() {
        PanelSwap.insertPanel(panelA, panelC, false)
        return idsInSplit()
    }

    function dropKindOn(item, fx, fy) {
        const p = item.mapToItem(root.contentItem, item.width * fx, item.height * fy)
        return PanelSwap.dropKind(item, p)
    }

    function simulateDropById(srcId, dstId, fx, fy) {
        const src = srcId === "a" ? panelA : srcId === "b" ? panelB : panelC
        const dst = dstId === "a" ? panelA : dstId === "b" ? panelB : panelC
        PanelSwap.begin(src, src.mapToItem(root.contentItem, 16, 8))
        PanelSwap.finish(dst.mapToItem(root.contentItem, dst.width * fx, dst.height * fy))
        return idsInSplit()
    }

    function hoverB() {
        const p = panelB.mapToItem(root.contentItem, panelB.width / 2, panelB.height / 2)
        PanelSwap.begin(panelA, Qt.point(0, 0))
        const hit = PanelSwap.panelAt(p)
        hoverHit = !!(hit && hit.panelId === "b")
        PanelSwap.cancel()
        return hoverHit
    }

    function restoreCorrupt() {
        PanelSwap.store.panelOrderJson = '{"controlLeft":[{"id":"a"}],"controlCenter":[{"id":"a"},{"id":"b"}],"controlRight":[]}'
        PanelSwap.restore()
        return idsInSplit()
    }
}
"""


def _app():
    QCoreApplication.setOrganizationName("AstroDwarfPanelSwapTest")
    QCoreApplication.setApplicationName("PanelSwapTest")
    return QGuiApplication.instance() or QGuiApplication([])


def _window_pos(item: QQuickItem, fx: float = 0.5, fy: float = 0.5) -> QPoint:
    pt = item.mapToScene(QPointF(item.width() * fx, item.height() * fy))
    return QPoint(int(pt.x()), int(pt.y()))


class PanelSwapTests(unittest.TestCase):
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
            raise RuntimeError("panel swap probe failed to load: " + " | ".join(warnings))
        cls.win = cls.engine.rootObjects()[0]
        cls.warnings = warnings

    def setUp(self):
        if self.win.idsInSplit() != "a,b,c":
            self.win.resetOrder()
        self.assertEqual(self.win.idsInSplit(), "a,b,c")

    def test_qml_loads_clean(self):
        self.assertFalse(self.warnings)

    def test_splitview_parent_is_not_the_split(self):
        # Documents why swap must walk ancestors: SplitView parents items to contentItem.
        chain = str(self.win.property("parentChain") or "")
        self.assertIn("add=true", chain)

    def test_swap_panels_exchanges_split_order(self):
        self.assertEqual(self.win.idsInSplit(), "a,b,c")
        self.assertEqual(self.win.swapAB(), "b,a,c")
        self.assertTrue(self.win.property("swapOk"))
        self.assertEqual(self.win.swapAB(), "a,b,c")

    def test_hover_hits_other_panel(self):
        self.assertTrue(self.win.hoverB())
        self.assertTrue(self.win.property("hoverHit"))

    def test_drop_kind_uses_edges_for_insert(self):
        b = self.win.findChild(QQuickItem, "panelB")
        self.assertEqual(self.win.dropKindOn(b, 0.5, 0.08), "before")
        self.assertEqual(self.win.dropKindOn(b, 0.5, 0.5), "swap")
        self.assertEqual(self.win.dropKindOn(b, 0.5, 0.92), "after")

    def test_insert_after_moves_without_swap(self):
        self.assertEqual(self.win.insertAAfterC(), "b,c,a")

    def test_insert_before_moves_without_swap(self):
        self.assertEqual(self.win.insertABeforeC(), "b,a,c")

    def test_corrupt_saved_order_is_ignored(self):
        self.assertEqual(self.win.restoreCorrupt(), "a,b,c")
        self.assertEqual(self.win.idsInSplit(), "a,b,c")

    def test_header_drag_swaps_panels(self):
        self.win.simulateDropById("a", "b", 0.5, 0.5)
        QTest.qWait(50)
        self.assertEqual(self.win.idsInSplit(), "b,a,c")

    def test_header_drag_inserts_on_edge(self):
        handle = self.win.findChild(QQuickItem, "panelDrag-a")
        target = self.win.findChild(QQuickItem, "panelC")
        window = handle.window()
        start = _window_pos(handle)
        end = _window_pos(target, 0.5, 0.92)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
        QTest.mouseMove(window, start + QPoint(0, 24))
        QTest.qWait(30)
        QTest.mouseMove(window, end)
        QTest.qWait(30)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
        QTest.qWait(100)
        self.assertEqual(self.win.idsInSplit(), "b,c,a")


if __name__ == "__main__":
    unittest.main()
