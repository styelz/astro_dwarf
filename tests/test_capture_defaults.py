import json
import tempfile
import unittest
from pathlib import Path

from astro_dwarf.domain import (
    DEFAULT_EXPOSURE_SECONDS,
    DEFAULT_FRAME_COUNT,
    DEFAULT_GAIN,
    CaptureDefaults,
    Device,
    camera_settings_from_capture,
    capture_defaults_from_dict,
    device_from_dict,
    to_dict,
)
from astro_dwarf.storage import SessionStore


class CaptureDefaultsTests(unittest.TestCase):
    def test_missing_values_use_stock_defaults(self) -> None:
        defaults = capture_defaults_from_dict({})
        self.assertEqual(defaults.exposure_seconds, DEFAULT_EXPOSURE_SECONDS)
        self.assertEqual(defaults.gain, DEFAULT_GAIN)
        self.assertEqual(defaults.frame_count, DEFAULT_FRAME_COUNT)

    def test_rejects_invalid_and_non_positive_values(self) -> None:
        defaults = capture_defaults_from_dict({
            "exposure_seconds": "nope",
            "gain": -4,
            "frame_count": 0,
        })
        self.assertEqual(defaults.exposure_seconds, DEFAULT_EXPOSURE_SECONDS)
        self.assertEqual(defaults.gain, DEFAULT_GAIN)
        self.assertEqual(defaults.frame_count, DEFAULT_FRAME_COUNT)

    def test_keeps_zero_gain(self) -> None:
        defaults = capture_defaults_from_dict({"gain": 0})
        self.assertEqual(defaults.gain, 0)

    def test_device_json_without_capture_defaults_still_loads(self) -> None:
        device = device_from_dict({"name": "Dwarf 3"})
        self.assertEqual(device.capture_defaults.exposure_seconds, DEFAULT_EXPOSURE_SECONDS)
        self.assertEqual(device.capture_defaults.gain, DEFAULT_GAIN)
        self.assertEqual(device.capture_defaults.frame_count, DEFAULT_FRAME_COUNT)

    def test_device_roundtrip_keeps_custom_capture_defaults(self) -> None:
        original = Device(
            name="Dwarf 3",
            capture_defaults=CaptureDefaults(exposure_seconds=30, gain=60, frame_count=200),
        )
        loaded = device_from_dict(to_dict(original))
        self.assertEqual(loaded.capture_defaults.exposure_seconds, 30)
        self.assertEqual(loaded.capture_defaults.gain, 60)
        self.assertEqual(loaded.capture_defaults.frame_count, 200)

    def test_camera_settings_from_capture(self) -> None:
        camera = camera_settings_from_capture(CaptureDefaults(30, 100, 48))
        self.assertEqual(camera.exposure_seconds, 30)
        self.assertEqual(camera.gain, 100)
        self.assertEqual(camera.frame_count, 48)

    def test_resolved_frame_count_prefers_explicit_then_defaults(self) -> None:
        from astro_dwarf.domain import resolved_frame_count

        defaults = CaptureDefaults(frame_count=200)
        self.assertEqual(resolved_frame_count(90, defaults), 90)
        self.assertEqual(resolved_frame_count(None, defaults), 200)
        self.assertEqual(resolved_frame_count(0, defaults), 200)
        self.assertEqual(resolved_frame_count("nope"), DEFAULT_FRAME_COUNT)

    def test_legacy_import_uses_device_defaults_when_camera_missing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            payload = {
                "command": {
                    "id_command": {"date": "2026-01-01", "time": "22:00:00", "description": "M42"},
                    "goto_manual": {"target": "M42", "ra_coord": 5.5, "dec_coord": -5.4, "do_action": True},
                    "setup_camera": {},
                }
            }
            source = root / "old.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            store = SessionStore(root / "data")
            count, failed = store.import_old_sessions(
                [source],
                "device-1",
                CaptureDefaults(exposure_seconds=20, gain=50, frame_count=90),
            )
            self.assertEqual((count, failed), (1, 0))
            session = store.sessions.all()[0]
            self.assertEqual(session.camera.exposure_seconds, 20)
            self.assertEqual(session.camera.gain, 50)
            self.assertEqual(session.camera.frame_count, 90)


if __name__ == "__main__":
    unittest.main()
