import unittest

from astro_dwarf.domain import (
    Device,
    default_device_name,
    device_name_model,
    is_first_device_setup,
)


class DeviceNameTests(unittest.TestCase):
    def test_default_uses_next_index(self) -> None:
        self.assertEqual(default_device_name(0), "DWARF #1")
        self.assertEqual(default_device_name(1), "DWARF #2")
        self.assertEqual(default_device_name(2), "DWARF #3")

    def test_default_is_not_a_model_token(self) -> None:
        self.assertEqual(device_name_model(default_device_name(1)), "")
        self.assertEqual(device_name_model("DWARF #2"), "")


class FirstDeviceSetupTests(unittest.TestCase):
    def test_seed_without_location_is_first_setup(self) -> None:
        self.assertTrue(is_first_device_setup([Device(name="Dwarf 3")]))

    def test_configured_or_multiple_devices_are_not_first_setup(self) -> None:
        self.assertFalse(is_first_device_setup([]))
        self.assertFalse(is_first_device_setup([
            Device(name="Dwarf 3", latitude=51.5, longitude=-0.1, location_configured=True),
        ]))
        self.assertFalse(is_first_device_setup([
            Device(name="Dwarf 3"),
            Device(name="DWARF #2"),
        ]))
