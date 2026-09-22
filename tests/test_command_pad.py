"""Command pad: the stop chip is centered on the right, and its click does not arm the pad."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent
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
    from PySide6.QtQml import QQmlEngine

    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    warnings: list[str] = []
    engine.warnings.connect(lambda entries: warnings.extend(str(entry.toString()) for entry in entries))
    source = """
import QtQuick
import QtQuick.Window
import "."
import "components"
Window {
    id: host
    objectName: "padHost"
    width: 360
    height: 80
    visible: true
    property int activations: 0
    property int stops: 0
    property int expectedWidth: Theme.px(120)
    property int expectedInset: Theme.s2
    property int expectedStopMargin: Theme.s1 + Theme.px(10)
    HudCommandPad {
        id: pad
        objectName: "pad-timelapse_start"
        anchors.fill: parent
        anchors.margins: 4
        text: "TIMELAPSE"
        glyph: "◷"
        detail: "00:00 / 15:00 · OUT 00:00 / 00:30"
        canStop: true
        primed: true
        onClicked: host.activations += 1
        onStopClicked: host.stops += 1
    }
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "pad_probe.qml")))
    window = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(component.status() == QQmlComponent.Status.Ready and window is not None,
            "HudCommandPad probe failed: " + "; ".join(errors + warnings))
    QQmlEngine.setObjectOwnership(window, QQmlEngine.ObjectOwnership.CppOwnership)
    app.processEvents()
    return app, engine, component, window


def _find(root: QObject, kind: type, name: str):
    child = root.findChild(kind, name)
    _assert(child is not None, "missing " + name)
    return child


def _click_item(window: QQuickWindow, item: QQuickItem) -> None:
    center = item.mapToScene(QPointF(item.width() / 2.0, item.height() / 2.0))
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(center.x()), int(center.y())))
    QGuiApplication.processEvents()


def test_stop_chip_is_centered_on_the_right_and_does_not_widen_the_pad() -> None:
    app, _engine, _component, window = _create_host()
    try:
        window.show()
        QTest.qWait(60)
        app.processEvents()
        pad = _find(window, QQuickItem, "pad-timelapse_start")
        stop = _find(window, QQuickItem, "pad-timelapse_start-stop")
        expected = int(window.property("expectedWidth") or 0)
        inset = int(window.property("expectedInset") or 0)
        stop_margin = int(window.property("expectedStopMargin") or 0)
        implicit = float(pad.property("implicitWidth") or 0)
        _assert(abs(implicit - expected) < 1.5, "long clock widened the pad: implicit %s expected %s" % (implicit, expected))
        origin = stop.mapToItem(pad, QPointF(0, 0))
        stop_right = float(origin.x()) + float(stop.width())
        # Content padding plus the chip's own right margin.
        right_inset = inset + stop_margin
        _assert(abs(float(pad.width()) - stop_right - right_inset) <= 1.5, "stop right edge %s, pad %s, inset %s" % (stop_right, pad.width(), right_inset))
        stop_mid = float(origin.y()) + float(stop.height()) / 2.0
        _assert(abs(stop_mid - float(pad.height()) / 2.0) <= 1.5, "stop is not vertically centered: mid %s pad %s" % (stop_mid, pad.height()))
        lead = float(pad.property("stopLead") or 0)
        _assert(lead > inset + 8, "stop is still against the title, lead %s" % lead)

        _click_item(window, stop)
        QTest.qWait(30)
        _assert(int(window.property("stops") or 0) == 1, "stop click count " + str(window.property("stops")))
        _assert(int(window.property("activations") or 0) == 0, "stop click also armed the pad")

        QTest.qWait(120)
        body = QPoint(int(pad.width() * 0.35), int(pad.height() * 0.72))
        scene = pad.mapToScene(QPointF(body.x(), body.y()))
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(int(scene.x()), int(scene.y())))
        QGuiApplication.processEvents()
        detail = "activations %s stops %s pressed %s handled %s scene %s,%s pad %sx%s" % (
            window.property("activations"),
            window.property("stops"),
            pad.property("stopPressed"),
            pad.property("stopHandled"),
            scene.x(),
            scene.y(),
            pad.width(),
            pad.height(),
        )
        _assert(int(window.property("activations") or 0) == 1, "pad body did not arm: " + detail)
        _assert(int(window.property("stops") or 0) == 1, "pad body also hit stop: " + detail)
    finally:
        window.close()
        app.processEvents()


if __name__ == "__main__":
    test_stop_chip_is_centered_on_the_right_and_does_not_widen_the_pad()
    print("ok")
