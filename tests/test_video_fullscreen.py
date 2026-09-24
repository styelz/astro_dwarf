from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

QML = ROOT / "astro_dwarf" / "qml"
MAIN = QML / "Main.qml"
CONTROL = QML / "pages" / "ControlPage.qml"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _function(source: str, name: str) -> str:
    match = re.search(rf"function {name}\(\) \{{(.*?)\n    \}}", source, re.S)
    _assert(match is not None, f"{name} missing from Main.qml")
    return f"function {name}() {{{match.group(1)}\n    }}"


def _method(source: str, name: str) -> str:
    match = re.search(rf"function {name}\([^)]*\) \{{(.*?)\n                    \}}", source, re.S)
    _assert(match is not None, f"{name} missing from ControlPage.qml")
    return match.group(1)


def _app() -> QGuiApplication:
    existing = QGuiApplication.instance()
    if existing is not None:
        return existing
    return QGuiApplication([])


def _wait(app: QGuiApplication, ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents()


def _as_int(value) -> int:
    return int(getattr(value, "value", value))


def _snapshot(win) -> dict[str, int]:
    return {
        "visibility": _as_int(win.property("visibility")),
        "restore": _as_int(win.property("videoFullscreenRestore")),
        "x": int(win.property("x")),
        "y": int(win.property("y")),
        "width": int(win.property("width")),
        "height": int(win.property("height")),
    }


def test_live_feed_fullscreen_uses_the_window() -> None:
    main = MAIN.read_text(encoding="utf-8")
    control = CONTROL.read_text(encoding="utf-8")
    enter = _function(main, "enterVideoFullscreen")
    leave = _function(main, "exitVideoFullscreen")
    _assert("showFullScreen()" in enter, "enter covers the monitor")
    _assert("visibility === Window.Maximized" in enter, "maximized is remembered")
    _assert("showNormal()" in leave, "fullscreen clears before restore")
    _assert("showMaximized()" in leave, "a maximized window is maximized again")
    _assert(leave.index("showNormal()") < leave.index("showMaximized()"), "normal runs before maximized")

    feed_enter = _method(control, "enterFeedFullscreen")
    feed_leave = _method(control, "exitFeedFullscreen")
    _assert(
        feed_enter.index("feedFullscreen = true") < feed_enter.index("root.enterVideoFullscreen()"),
        "the feed covers the window before the window covers the monitor",
    )
    _assert(
        feed_leave.index("root.exitVideoFullscreen()") < feed_leave.index("feedFullscreen = false"),
        "the monitor restores before the feed overlay leaves",
    )


def test_fullscreen_restores_the_previous_window() -> None:
    app = _app()
    main = MAIN.read_text(encoding="utf-8")
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    source = """
import QtQuick
import QtQuick.Window
Window {
    id: root
    width: 800
    height: 500
    x: 80
    y: 80
    visible: true
    title: "FS"
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint | Qt.WindowSystemMenuHint
    property int videoFullscreenRestore: Window.Windowed
    %s
    %s
}
""" % (_function(main, "enterVideoFullscreen"), _function(main, "exitVideoFullscreen"))
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML / "video_fullscreen_probe.qml")))
    win = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(component.status() == QQmlComponent.Status.Ready and win is not None, "; ".join(errors))
    try:
        _wait(app, 400)
        windowed = _snapshot(win)
        _assert(windowed["visibility"] == 2, f"starts windowed, got {windowed}")

        win.showMaximized()
        _wait(app, 400)
        maximized = _snapshot(win)
        _assert(maximized["visibility"] == 4, f"maximized, got {maximized}")

        win.enterVideoFullscreen()
        _wait(app, 400)
        covered = _snapshot(win)
        _assert(covered["visibility"] == 5, f"fullscreen, got {covered}")
        _assert(covered["restore"] == 4, "maximized window is the restore target")
        if covered["width"] != maximized["width"] or covered["height"] != maximized["height"]:
            _assert(covered["x"] == 0 and covered["y"] == 0, f"fullscreen origin, got {covered}")

        win.enterVideoFullscreen()
        _wait(app, 100)
        _assert(int(win.property("videoFullscreenRestore")) == 4, "a second enter keeps the restore target")

        win.exitVideoFullscreen()
        _wait(app, 400)
        restored = _snapshot(win)
        _assert(restored["visibility"] == 4, f"returns maximized, got {restored}")
        _assert(restored["width"] == maximized["width"] and restored["height"] == maximized["height"], restored)

        win.showNormal()
        _wait(app, 400)
        win.exitVideoFullscreen()
        stayed = _snapshot(win)
        _assert(stayed["visibility"] == 2, f"exit outside fullscreen leaves the window, got {stayed}")
        _assert(stayed["width"] == windowed["width"] and stayed["height"] == windowed["height"], stayed)

        win.enterVideoFullscreen()
        _wait(app, 400)
        _assert(_as_int(win.property("visibility")) == 5, "windowed enter covers the monitor")
        _assert(int(win.property("videoFullscreenRestore")) == 2, "windowed is the restore target")
        win.exitVideoFullscreen()
        _wait(app, 400)
        back = _snapshot(win)
        _assert(back["visibility"] == 2, f"returns windowed, got {back}")
        _assert(back["x"] == windowed["x"] and back["y"] == windowed["y"], back)
        _assert(back["width"] == windowed["width"] and back["height"] == windowed["height"], back)
    finally:
        win.close()
        app.processEvents()


if __name__ == "__main__":
    test_live_feed_fullscreen_uses_the_window()
    test_fullscreen_restores_the_previous_window()
    print("ok")
