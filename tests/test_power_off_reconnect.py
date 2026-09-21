from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_telemetry import TelemetryTap, link_telemetry
from astro_dwarf.telemetry_view import AlertEngine


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_link_telemetry_strips_stale_power_off() -> None:
    cleaned = link_telemetry({"power_off": True, "battery_percent": 64})
    _assert("power_off" not in cleaned, cleaned)
    _assert(cleaned["battery_percent"] == 64, cleaned)
    _assert(link_telemetry(None) == {}, "empty snapshot")


def test_power_off_is_ignored_until_the_link_is_accepted() -> None:
    events: list[dict] = []
    tap = TelemetryTap(lambda message: events.append(message))
    tap.update({"power_off": True, "battery_percent": 50}, force=True)
    snap = tap.snapshot()
    _assert("power_off" not in snap, snap)
    _assert(snap["battery_percent"] == 50, snap)
    _assert(all("power_off" not in (item.get("data") or {}) for item in events), events)

    tap.accept_power_off()
    tap.update({"power_off": True}, force=True)
    _assert(tap.snapshot().get("power_off") is True, tap.snapshot())


def test_reconnect_reset_forgets_reboot_power_off() -> None:
    events: list[dict] = []
    tap = TelemetryTap(lambda message: events.append(message))
    tap.accept_power_off()
    tap.update({"power_off": True, "battery_percent": 22}, force=True)
    _assert(tap.snapshot().get("power_off") is True, tap.snapshot())

    # Reboot marks the worker disconnected, then POWER_OFF can arrive again.
    tap.reset()
    tap.update({"power_off": True}, force=True)
    _assert("power_off" not in tap.snapshot(), tap.snapshot())
    _assert("power_off" not in link_telemetry(tap.snapshot()), "handshake result")

    tap.accept_power_off()
    tap.update({"battery_percent": 80}, force=True)
    _assert("power_off" not in tap.snapshot(), tap.snapshot())


def test_power_off_toast_only_on_live_transition() -> None:
    alerts = AlertEngine().evaluate({}, {"power_off": True})
    _assert(any(item["message"] == "Telescope is powering off" for item in alerts), alerts)
    held = AlertEngine().evaluate({"power_off": True}, {"power_off": True})
    _assert(held == [], held)


def main() -> int:
    test_link_telemetry_strips_stale_power_off()
    test_power_off_is_ignored_until_the_link_is_accepted()
    test_reconnect_reset_forgets_reboot_power_off()
    test_power_off_toast_only_on_live_transition()
    print("power-off reconnect tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
