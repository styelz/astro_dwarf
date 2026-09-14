import unittest
from types import SimpleNamespace
from unittest import mock

from astro_dwarf.device_worker import (
    ble_wifi_mode,
    discover_nearby_dwarfs,
    nearby_dwarf_record,
)


class BleWifiModeTests(unittest.TestCase):
    def test_firmware_codes(self) -> None:
        self.assertEqual(ble_wifi_mode(1), "ap")
        self.assertEqual(ble_wifi_mode(2, "10.0.0.8", "Home"), "sta")

    def test_infers_ap_from_hotspot(self) -> None:
        self.assertEqual(ble_wifi_mode(None, "192.168.88.1", ""), "ap")
        self.assertEqual(ble_wifi_mode(None, "", "DWARF3_ABC"), "ap")

    def test_infers_sta_from_lan_ip(self) -> None:
        self.assertEqual(ble_wifi_mode(None, "10.0.0.5", "Home"), "sta")

    def test_unknown_stays_auto(self) -> None:
        self.assertEqual(ble_wifi_mode(None), "auto")


class NearbyDwarfRecordTests(unittest.TestCase):
    def test_maps_dwarf3_station(self) -> None:
        rec = nearby_dwarf_record(
            "DWARF3_ABC",
            "AA:BB",
            {"ip_address": "10.0.0.5", "wifi_mode": 2, "ssid": "HomeNet"},
        )
        self.assertEqual(rec["model"], "Dwarf 3")
        self.assertEqual(rec["wifi_mode"], "sta")
        self.assertEqual(rec["wifi_ssid"], "HomeNet")
        self.assertEqual(rec["ip_address"], "10.0.0.5")

    def test_drops_hotspot_ssid(self) -> None:
        rec = nearby_dwarf_record(
            "DWARF3_ABC",
            "AA:BB",
            {"ip_address": "192.168.88.1", "wifi_mode": 1, "ssid": "DWARF3_ABC"},
        )
        self.assertEqual(rec["wifi_mode"], "ap")
        self.assertEqual(rec["wifi_ssid"], "")

    def test_keeps_read_error(self) -> None:
        rec = nearby_dwarf_record("DWARF_MINI_1", "CC:DD", error="Bluetooth password rejected")
        self.assertEqual(rec["model"], "Dwarf Mini")
        self.assertIn("password", rec["error"])


class DiscoverNearbyDwarfsTests(unittest.TestCase):
    def test_reads_wifi_for_matching_model(self) -> None:
        dwarf = SimpleNamespace(name="DWARF3_ABC", address="11:22:33:44")
        calls: list[object] = []

        def fake_run(factory):
            calls.append(factory)
            if len(calls) == 1:
                return {"dwarf_devices": [dwarf]}
            return {"ip_address": "10.0.0.9", "ssid": "Home", "wifi_mode": 2}

        with mock.patch("astro_dwarf.device_worker._run_async", side_effect=fake_run):
            items = discover_nearby_dwarfs(model="Dwarf 3", on_log=lambda *_args, **_kwargs: None)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "DWARF3_ABC")
        self.assertEqual(items[0]["ip_address"], "10.0.0.9")
        self.assertEqual(items[0]["wifi_mode"], "sta")
        self.assertEqual(len(calls), 2)

    def test_keeps_device_when_wifi_read_fails(self) -> None:
        dwarf = SimpleNamespace(name="DWARF3_ABC", address="11:22:33:44")

        def fake_run(factory):
            if not hasattr(fake_run, "n"):
                fake_run.n = 0
            fake_run.n += 1
            if fake_run.n == 1:
                return {"dwarf_devices": [dwarf]}
            raise RuntimeError("Bluetooth password rejected")

        with mock.patch("astro_dwarf.device_worker._run_async", side_effect=fake_run):
            items = discover_nearby_dwarfs(on_log=lambda *_args, **_kwargs: None)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "DWARF3_ABC")
        self.assertIn("password", items[0]["error"])
        self.assertEqual(items[0]["ip_address"], "")

    def test_missing_devices_raise(self) -> None:
        with mock.patch("astro_dwarf.device_worker._run_async", return_value={"dwarf_devices": []}):
            with self.assertRaisesRegex(RuntimeError, "No Dwarf found"):
                discover_nearby_dwarfs(on_log=lambda *_args, **_kwargs: None)


if __name__ == "__main__":
    unittest.main()
