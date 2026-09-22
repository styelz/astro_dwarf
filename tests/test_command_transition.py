"""Command pads stay dark during stop, cancel, and firmware state changes."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QML_DIR = ROOT / "astro_dwarf" / "qml"


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _probe() -> tuple[QGuiApplication, QQmlEngine, QQmlComponent, object]:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(QML_DIR))
    warnings: list[str] = []
    engine.warnings.connect(lambda entries: warnings.extend(str(entry.toString()) for entry in entries))
    source = """
import QtQuick
import "."
QtObject {
    property string op: ""
    property string pending: ""
    property var telemetry: ({})
    readonly property bool locked: Util.commandTransitionLocked(op, pending, telemetry)
}
"""
    component = QQmlComponent(engine)
    component.setData(source.encode("utf-8"), QUrl.fromLocalFile(str(QML_DIR / "transition_probe.qml")))
    probe = component.create()
    errors = [err.toString() for err in component.errors()]
    _assert(probe is not None, "transition probe failed: " + "; ".join(errors + warnings))
    QQmlEngine.setObjectOwnership(probe, QQmlEngine.ObjectOwnership.CppOwnership)
    return app, engine, component, probe


def _locked(probe, op: str, pending: str = "", **telemetry) -> bool:
    probe.setProperty("op", op)
    probe.setProperty("pending", pending)
    probe.setProperty("telemetry", telemetry)
    return bool(probe.property("locked"))


def test_stop_and_cancel_stay_locked_until_the_state_settles() -> None:
    _app, _qml_engine, _component, probe = _probe()
    _assert(not _locked(probe, "stop_astro", "", capture_state="running"), "a running stack must still stop")
    _assert(_locked(probe, "stop_astro", "stack"), "stack start must not be interrupted by stop")
    _assert(_locked(probe, "stop_astro", "", capture_state="stopping"), "stack stop must not be pressed again while stopping")
    _assert(_locked(probe, "stack", "", capture_state="stopping"), "stack must not restart while the capture is stopping")

    _assert(not _locked(probe, "cancel_prime", "", burst_state="running"), "a running burst can be stopped and cancelled")
    _assert(_locked(probe, "cancel_prime", "cancel_prime"), "cancel must not be pressed again")
    _assert(_locked(probe, "cancel_prime", "burst_stop"), "cancel must wait out the burst stop")
    _assert(_locked(probe, "burst_stop", "cancel_prime"), "burst stop must wait out cancel")
    _assert(_locked(probe, "burst_stop", "", burst_state="stopping"), "burst stop must not be pressed again while stopping")
    _assert(not _locked(probe, "burst_stop", "", burst_state="running"), "a running burst must still stop")

    _assert(not _locked(probe, "stop_goto", "", goto_state="running"), "a slew must still stop")
    _assert(_locked(probe, "stop_goto", "track"), "track start must not be interrupted by stop")
    _assert(_locked(probe, "stop_goto", "", goto_state="stopping"), "goto stop must not be pressed again while stopping")
    _assert(_locked(probe, "track", "", goto_state="stopping"), "track must not restart while goto is stopping")

    _assert(_locked(probe, "stop_autofocus", "infinity"), "infinity start must not be interrupted by stop")
    _assert(_locked(probe, "autofocus", "", autofocus_state="stopping"), "focus must not restart while stopping")
    _assert(_locked(probe, "stop_calibrate", "calibrate"), "calibration start must not be interrupted by stop")
    _assert(
        not _locked(probe, "stop_polar_position", "polar_position"),
        "polar positioning must stay stoppable while the slew is in flight",
    )
    _assert(_locked(probe, "lights_off", "lights_on"), "lights must not be toggled again while turning on")
    _assert(not _locked(probe, "photo", "", photo_state="running"), "a settled photo command is not a stop transition")
    _assert(_locked(probe, "photo", "", photo_state="stopping"), "photo must stay dark while the shot is stopping")
    _assert(not _locked(probe, "set_gain", "stack"), "camera settings are not command-pad transitions")


if __name__ == "__main__":
    test_stop_and_cancel_stay_locked_until_the_state_settles()
    print("ok")
