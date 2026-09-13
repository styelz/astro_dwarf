import unittest

from astro_dwarf.telemetry_view import camera_params_to_telemetry, exposure_seconds_from_text, format_telemetry


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


class CameraParamsToTelemetryTests(unittest.TestCase):
    def test_reads_named_exposure_and_gain(self) -> None:
        changes = camera_params_to_telemetry(
            {
                "cameras": {
                    0: {
                        "exposure": {"name": "0.5", "value": 111},
                        "gain": {"value": 50},
                        "hue": -88,
                    },
                    1: {
                        "exposure": {"name": "1/60", "value": 20},
                        "gain": {"value": 0},
                    },
                }
            }
        )
        self.assertEqual(changes["exposure_text"], "0.5")
        self.assertEqual(changes["gain"], 50)
        self.assertEqual(changes["hue"], -88)
        self.assertEqual(changes["wide_exposure_text"], "1/60")
        self.assertEqual(changes["wide_gain"], 0)

    def test_json_string_camera_keys(self) -> None:
        changes = camera_params_to_telemetry(
            {
                "cameras": {
                    "0": {"exposure": {"name": "15"}, "gain": {"value": 80}},
                    "1": {"exposure": {"name": "10"}, "gain": {"value": 40}},
                }
            }
        )
        self.assertEqual(changes["exposure_text"], "15")
        self.assertEqual(changes["gain"], 80)
        self.assertEqual(changes["wide_exposure_text"], "10")
        self.assertEqual(changes["wide_gain"], 40)

    def test_bare_values_and_empty_results(self) -> None:
        self.assertEqual(camera_params_to_telemetry(False), {})
        self.assertEqual(camera_params_to_telemetry(None), {})
        changes = camera_params_to_telemetry(
            {"cameras": {"0": {"exposure": "1/30", "gain": 25}}}
        )
        self.assertEqual(changes["exposure_text"], "1/30")
        self.assertEqual(changes["gain"], 25)

    def test_reads_astro_auto_calibration(self) -> None:
        on = camera_params_to_telemetry({"cameras": {}, "shooting_mode": {"autoCalibration": True}})
        off = camera_params_to_telemetry({"cameras": {}, "shooting_mode": {"autoCalibration": False}})
        named = camera_params_to_telemetry({"cameras": {}, "shooting_mode": {"auto_calibration": "on"}})
        missing = camera_params_to_telemetry({"cameras": {"0": {"gain": 10}}})
        self.assertTrue(on["auto_calibration"])
        self.assertFalse(off["auto_calibration"])
        self.assertTrue(named["auto_calibration"])
        self.assertNotIn("auto_calibration", missing)

    def test_reads_burst_timelapse_and_stack_format(self) -> None:
        changes = camera_params_to_telemetry(
            {
                "cameras": {
                    "0": {
                        "count": 40,
                        "burst": {"count": 8, "interval": "2s"},
                        "timeLapse": {"interval": 10, "duration": {"name": "300"}},
                    }
                },
                "shooting_mode": {"stackFormat": 1},
            }
        )
        self.assertEqual(changes["stack_count"], 40)
        self.assertEqual(changes["burst_count"], 8)
        self.assertEqual(changes["burst_interval"], "2s")
        self.assertEqual(changes["timelapse_interval"], "10")
        self.assertEqual(changes["timelapse_duration"], "300")
        self.assertEqual(changes["stack_format"], 1)
        view = format_telemetry(changes, updated_at=1.0, now=1.0)
        self.assertEqual(view["stack_count"], 40)
        self.assertEqual(view["burst_count"], 8)
        self.assertEqual(view["burst_interval"], "2s")
        self.assertEqual(view["timelapse_interval"], "10")
        self.assertEqual(view["timelapse_duration"], "300")
        self.assertEqual(view["stack_format"], 1)


class PhotoPrimedViewTests(unittest.TestCase):
    def test_primed_after_still_in_photo_mode(self) -> None:
        view = format_telemetry(
            {"shooting_mode": 1, "shooting_tech": 1, "photo_primed": True},
            updated_at=1.0,
            now=1.0,
        )
        self.assertTrue(view["photo_primed"])
        self.assertEqual(view["shooting_mode_text"], "PHOTO")

    def test_photo_mode_without_a_still_is_not_primed(self) -> None:
        view = format_telemetry(
            {"shooting_mode": 1, "shooting_tech": 1},
            updated_at=1.0,
            now=1.0,
        )
        self.assertFalse(view["photo_primed"])

    def test_dso_or_burst_clears_primed(self) -> None:
        dso = format_telemetry(
            {"shooting_mode": 2, "shooting_tech": 2, "photo_primed": True},
            updated_at=1.0,
            now=1.0,
        )
        burst = format_telemetry(
            {"shooting_mode": 1, "shooting_tech": 3, "photo_primed": True},
            updated_at=1.0,
            now=1.0,
        )
        self.assertFalse(dso["photo_primed"])
        self.assertFalse(burst["photo_primed"])
