from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import protocol_pb2

from astro_dwarf.domain import solar_system_target_id, solar_system_targets


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_list_matches_api_enum() -> None:
    expected = [
        name
        for name, value in protocol_pb2.SolarSystemTarget.items()
        if int(value) > 0 and name != "Unknown"
    ]
    names = solar_system_targets()
    _assert(names == expected, names)
    _assert("Unknown" not in names, names)
    _assert(names[0] == "Mercury" and names[-1] == "Sun", names)


def test_ids_match_api_enum() -> None:
    for name, value in protocol_pb2.SolarSystemTarget.items():
        if int(value) <= 0:
            continue
        _assert(solar_system_target_id(name) == int(value), name)
        _assert(solar_system_target_id(name.lower()) == int(value), name)
    _assert(solar_system_target_id("Unknown") is None, "unknown")
    _assert(solar_system_target_id("") is None, "empty")
    _assert(solar_system_target_id("M31") is None, "dso")


def test_session_dialog_uses_api_list() -> None:
    qml = (ROOT / "astro_dwarf" / "qml" / "dialogs" / "SessionDialog.qml").read_text(encoding="utf-8")
    _assert('objectName: "session-solar-target"' in qml, "solar combo")
    _assert("model: backend.solarSystemTargets" in qml, "api model")
    _assert("visible: sessionDialog.solarKind" in qml, "solar replaces name")
    _assert("visible: !sessionDialog.solarKind" in qml, "name hidden for solar")


if __name__ == "__main__":
    test_list_matches_api_enum()
    test_ids_match_api_enum()
    test_session_dialog_uses_api_list()
    print("ok")
