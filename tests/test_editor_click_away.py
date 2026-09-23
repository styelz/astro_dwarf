"""A press on a panel clears a text field without stealing the panel's click."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QML_DIR = ROOT / "astro_dwarf" / "qml"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _app() -> QGuiApplication:
    existing = QGuiApplication.instance()
    if existing is not None:
        return existing
    return QGuiApplication([])


def _create_host():
    app = _app()
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    warnings: list[str] = []
    engine.warnings.connect(lambda entries: warnings.extend(str(entry.toString()) for entry in entries))
    source = """
import QtQuick
import QtQuick.Controls
import QtQuick.Window

ApplicationWindow {
    id: host
    objectName: "clickAwayHost"
    width: 420
    height: 280
    visible: true
    property int panelClicks: 0
    property int otherClicks: 0
    property int commits: 0
    property int handlerPresses: 0

    function isTextEditor(item) {
        return !!(item && (item instanceof TextInput || item instanceof TextEdit))
    }

    function editorChrome(item) {
        let node = item
        while (node) {
            if (node instanceof TextField)
                return node
            node = node.parent
        }
        return item
    }

    function releaseEditorFocusAt(scenePos) {
        const focused = host.activeFocusItem
        if (!host.isTextEditor(focused))
            return
        const chrome = host.editorChrome(focused)
        if (!chrome)
            return
        const local = chrome.mapFromItem(null, scenePos.x, scenePos.y)
        if (local.x >= -2 && local.y >= -2 && local.x <= chrome.width + 2 && local.y <= chrome.height + 2)
            return
        focused.focus = false
        if (chrome.focus)
            chrome.focus = false
    }

    component EditorClickAway: PointHandler {
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad | PointerDevice.TouchScreen
        onActiveChanged: {
            if (!active)
                return
            host.handlerPresses += 1
            host.releaseEditorFocusAt(point.scenePosition)
        }
    }

    Item {
        anchors.fill: parent
        TextField {
            id: field
            objectName: "field"
            x: 16
            y: 16
            width: 140
            height: 32
            text: "120"
            onEditingFinished: host.commits += 1
        }
        MouseArea {
            id: panel
            objectName: "panel"
            x: 180
            y: 16
            width: 200
            height: 100
            hoverEnabled: true
            onPressed: host.panelClicks += 1
        }
        MouseArea {
            id: other
            objectName: "otherPanel"
            x: 180
            y: 140
            width: 200
            height: 80
            onPressed: host.otherClicks += 1
        }
        MouseArea {
            anchors.fill: parent
            z: -1
            acceptedButtons: Qt.LeftButton
            onPressed: mouse => {
                host.releaseEditorFocusAt(mapToItem(null, mouse.x, mouse.y))
                mouse.accepted = false
            }
        }
    }

    Item {
        parent: Overlay.overlay
        anchors.fill: parent
        z: -1
        EditorClickAway { }
    }
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "click_away_probe.qml")))
    window = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(
        component.status() == QQmlComponent.Status.Ready and window is not None,
        "click-away probe failed: " + "; ".join(errors + warnings),
    )
    QQmlEngine.setObjectOwnership(window, QQmlEngine.ObjectOwnership.CppOwnership)
    app.processEvents()
    return app, engine, component, window


def _find(root, name: str) -> QQuickItem:
    child = root.findChild(QQuickItem, name)
    _assert(child is not None, "missing " + name)
    return child


def _click(window: QQuickWindow, item: QQuickItem) -> None:
    center = item.mapToScene(QPointF(item.width() / 2.0, item.height() / 2.0))
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(int(center.x()), int(center.y())),
    )
    QGuiApplication.processEvents()


def test_panel_click_clears_field_and_still_lands() -> None:
    app, _engine, _component, window = _create_host()
    try:
        window.show()
        QTest.qWait(60)
        app.processEvents()
        field = _find(window, "field")
        panel = _find(window, "panel")
        other = _find(window, "otherPanel")
        field.forceActiveFocus()
        QGuiApplication.processEvents()
        _assert(bool(field.property("activeFocus")), "field did not take focus")

        center = panel.mapToScene(QPointF(panel.width() / 2.0, panel.height() / 2.0))
        QTest.mouseMove(window, QPoint(int(center.x()), int(center.y())))
        QGuiApplication.processEvents()
        _assert(bool(panel.property("containsMouse")), "panel no longer sees hover")

        _click(window, panel)
        detail = "focus %s panel %s commits %s presses %s" % (
            field.property("activeFocus"),
            window.property("panelClicks"),
            window.property("commits"),
            window.property("handlerPresses"),
        )
        _assert(int(window.property("handlerPresses") or 0) >= 1, "click-away handler did not see the press: " + detail)
        _assert(not bool(field.property("activeFocus")), "panel click left the field focused: " + detail)
        _assert(int(window.property("panelClicks") or 0) == 1, "panel did not receive the click: " + detail)
        _assert(int(window.property("commits") or 0) == 1, "leaving the field did not commit: " + detail)

        field.forceActiveFocus()
        QGuiApplication.processEvents()
        _click(window, field)
        _assert(bool(field.property("activeFocus")), "clicking the field cleared it")
        _assert(int(window.property("commits") or 0) == 1, "clicking the field committed again")

        _click(window, other)
        _assert(not bool(field.property("activeFocus")), "other panel left the field focused")
        _assert(int(window.property("otherClicks") or 0) == 1, "other panel did not receive the click")
        _assert(int(window.property("commits") or 0) == 2, "second click-away did not commit")
    finally:
        window.close()
        app.processEvents()


def test_main_window_uses_point_handler_for_click_away() -> None:
    source = (QML_DIR / "Main.qml").read_text(encoding="utf-8")
    start = source.find("component EditorClickAway:")
    _assert(start >= 0, "EditorClickAway is missing")
    block = source[start:source.find("}", start)]
    _assert("PointHandler" in block, block)
    _assert("HoverHandler" not in block, block)
    _assert("parent: Overlay.overlay" in source, "click-away pane is not on the overlay")


if __name__ == "__main__":
    test_panel_click_clears_field_and_still_lands()
    test_main_window_uses_point_handler_for_click_away()
    print("ok")
