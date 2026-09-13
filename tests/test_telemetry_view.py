import unittest

from astro_dwarf.telemetry_view import exposure_seconds_from_text, format_telemetry


class ExposureSecondsFromTextTests(unittest.TestCase):
    def test_firmware_names(self) -> None:
        self.assertEqual(exposure_seconds_from_text("15"), 15.0)
        self.assertEqual(exposure_seconds_from_text("15s"), 15.0)
        self.assertAlmostEqual(exposure_seconds_from_text("1/60"), 1 / 60)
        self.assertEqual(exposure_seconds_from_text(30), 30.0)

    def test_rejects_blank(self) -> None:
        self.assertIsNone(exposure_seconds_from_text("—"))
        self.assertIsNone(exposure_seconds_from_text(""))
        self.assertIsNone(exposure_seconds_from_text(None))


class FormatTelemetryExposureTests(unittest.TestCase):
    def test_capturing_uses_firmware_progress(self) -> None:
        view = format_telemetry(
            {
                "capture_active": True,
                "capture_current": 3,
                "capture_stacked": 2,
                "capture_total": 120,
                "exposure_text": "15",
                "exposure_elapsed_s": 8,
                "exposure_total_s": 15,
            },
            updated_at=1.0,
            now=1.0,
        )
        self.assertEqual(view["exposure_elapsed_s"], 8.0)
        self.assertEqual(view["exposure_total_s"], 15.0)
        self.assertAlmostEqual(view["exposure_progress"], 8 / 15)
        self.assertEqual(view["capture_current"], 3)
        self.assertTrue(view["capture_active"])

    def test_capturing_falls_back_to_exposure_text(self) -> None:
        view = format_telemetry(
            {"capture_active": True, "exposure_text": "30"},
            updated_at=1.0,
            now=1.0,
        )
        self.assertEqual(view["exposure_elapsed_s"], 0.0)
        self.assertEqual(view["exposure_total_s"], 30.0)
        self.assertEqual(view["exposure_progress"], 0.0)

    def test_milliseconds_are_normalized(self) -> None:
        view = format_telemetry(
            {
                "capture_active": True,
                "exposure_text": "15",
                "exposure_elapsed_s": 8000,
                "exposure_total_s": 15000,
            },
            updated_at=1.0,
            now=1.0,
        )
        self.assertEqual(view["exposure_elapsed_s"], 8.0)
        self.assertEqual(view["exposure_total_s"], 15.0)

    def test_idle_zeros_elapsed(self) -> None:
        view = format_telemetry(
            {
                "capture_active": False,
                "exposure_text": "15",
                "exposure_elapsed_s": 12,
                "exposure_total_s": 15,
            },
            updated_at=1.0,
            now=1.0,
        )
        self.assertEqual(view["exposure_elapsed_s"], 0.0)
        self.assertEqual(view["exposure_progress"], 0.0)
        self.assertEqual(view["exposure_total_s"], 15.0)

    def test_wide_capture_uses_wide_exposure(self) -> None:
        view = format_telemetry(
            {
                "capture_active": True,
                "capture_camera": "wide",
                "wide_exposure_text": "10",
                "exposure_text": "15",
            },
            updated_at=1.0,
            now=1.0,
        )
        self.assertEqual(view["exposure_total_s"], 10.0)
