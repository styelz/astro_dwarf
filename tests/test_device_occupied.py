from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_telemetry import (
    DEVICE_OCCUPIED_MESSAGE,
    classify_sdk_log,
    clear_device_occupied,
    device_occupied,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_occupied_refusal_is_one_warning() -> None:
    clear_device_occupied()
    raw = (
        "Dwarf refused the connection: DEVICE_OCCUPIED (close code 4409). "
        "Another client (likely the official Dwarflab app) is already connected "
        "to this device. Disconnect it there first, then retry."
    )
    first = classify_sdk_log(raw, "error")
    _assert(first == ("warning", DEVICE_OCCUPIED_MESSAGE), first)
    _assert(device_occupied(), "occupied latch should be set")
    _assert(classify_sdk_log(raw, "error") is None, "a second refusal should not repeat")
    _assert(classify_sdk_log("WebSocket connection is not open.", "error") is None, "dead-socket error")
    _assert(classify_sdk_log("Error WebSocket Disconnected.", "error") is None, "disconnect error")
    _assert(classify_sdk_log("Dwarf API: Dwarf Device not connected", "error") is None, "api error")
    _assert(classify_sdk_log("Client not started", "warning") is None, "client warning")
    kept = classify_sdk_log("Plate solve failed", "error")
    _assert(kept == ("error", "Plate solve failed"), kept)
    clear_device_occupied()
    _assert(not device_occupied(), "latch should clear")
    restored = classify_sdk_log("Dwarf API: Dwarf Device not connected", "error")
    _assert(restored == ("error", "Dwarf API: Dwarf Device not connected"), restored)


if __name__ == "__main__":
    test_occupied_refusal_is_one_warning()
    print("ok")
