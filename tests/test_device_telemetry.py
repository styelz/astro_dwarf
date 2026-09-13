import unittest

from dwarf_python_api.proto import notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_LONG_EXP_PROGRESS,
    CMD_NOTIFY_TELE_LONG_EXP_PROGRESS,
    CMD_NOTIFY_WIDE_LONG_EXP_PROGRESS,
    TYPE_NOTIFICATION,
    TelemetryTap,
    is_chatter,
)


class LongExpProgressTests(unittest.TestCase):
    def _tap(self) -> TelemetryTap:
        tap = TelemetryTap(lambda _payload: None)
        tap._notify = notify_pb2
        tap._base = object()
        return tap

    def _decode(self, cmd: int, elapsed: float, total: float) -> dict:
        message = notify_pb2.LongExpPhotoProgress()
        message.total_time = total
        message.exposured_time = elapsed
        tap = self._tap()
        return tap._decode(cmd, TYPE_NOTIFICATION, message.SerializeToString())

    def test_generic_long_exp_notify_updates_elapsed(self) -> None:
        changes = self._decode(CMD_NOTIFY_LONG_EXP_PROGRESS, 4.5, 15.0)
        self.assertEqual(changes["exposure_elapsed_s"], 4.5)
        self.assertEqual(changes["exposure_total_s"], 15.0)

    def test_tele_and_wide_long_exp_use_the_same_payload(self) -> None:
        tele = self._decode(CMD_NOTIFY_TELE_LONG_EXP_PROGRESS, 1.0, 10.0)
        wide = self._decode(CMD_NOTIFY_WIDE_LONG_EXP_PROGRESS, 2.0, 10.0)
        self.assertEqual(tele["exposure_elapsed_s"], 1.0)
        self.assertEqual(wide["exposure_elapsed_s"], 2.0)


class SdkLogChatterTests(unittest.TestCase):
    def test_set_success_code_is_chatter(self) -> None:
        self.assertTrue(is_chatter("SET EXPOSURE (V3) -> 0"))
        self.assertTrue(is_chatter("SET GAIN (V3) -> 0"))
        self.assertTrue(is_chatter("SET IMAGE PARAM (V3) 0x20108 -> 0"))

    def test_set_failure_stays_visible(self) -> None:
        self.assertFalse(is_chatter("SET EXPOSURE (V3) -> -1"))
        self.assertFalse(is_chatter("Set exposure 15 (tele): ok"))


class WorkerSetLogTests(unittest.TestCase):
    def test_label_includes_set_value_and_camera(self) -> None:
        from astro_dwarf.device_worker import _format_operation_label, _format_sdk_result

        self.assertEqual(
            _format_operation_label("set_exposure", "Set Exposure", ("15", "3", "tele")),
            "Set Exposure 15 (tele)",
        )
        self.assertEqual(_format_sdk_result(0), "ok")
        self.assertEqual(_format_sdk_result(False), "failed")


class PhotoCapturePrimeTests(unittest.TestCase):
    def test_handshake_skips_when_technique_already_matches(self) -> None:
        from astro_dwarf.device_worker import capture_handshake_needed, shooting_state_changes

        self.assertTrue(capture_handshake_needed({}, 1))
        self.assertTrue(capture_handshake_needed({"shooting_mode": 1}, 1))
        self.assertFalse(capture_handshake_needed({"shooting_mode": 1, "shooting_tech": 1}, 1))
        self.assertTrue(capture_handshake_needed({"shooting_mode": 1, "shooting_tech": 3}, 1))
        self.assertFalse(capture_handshake_needed({"shooting_mode": 1, "shooting_tech": 3}, 3))

        primed = shooting_state_changes({}, mode=1, tech=1, photo_primed=True)
        self.assertEqual(primed, {"shooting_mode": 1, "shooting_tech": 1, "photo_primed": True})
        self.assertEqual(
            shooting_state_changes({"photo_primed": True}, mode=2, tech=2),
            {"shooting_mode": 2, "shooting_tech": 2, "photo_primed": False},
        )
        self.assertEqual(
            shooting_state_changes({"shooting_mode": 1, "photo_primed": True}, tech=4),
            {"shooting_tech": 4, "photo_primed": False},
        )
        self.assertNotIn("photo_primed", shooting_state_changes({}, mode=1, tech=1))


class CameraParamSkipTests(unittest.TestCase):
    def test_skips_matching_exposure_gain_count_and_filter(self) -> None:
        from astro_dwarf.device_worker import camera_param_unchanged

        snap = {"exposure_text": "15", "gain": 80, "wide_exposure_text": "1", "wide_gain": 20}
        device = {"frame_count": 60, "ir_filter": "VIS Filter"}
        self.assertTrue(camera_param_unchanged("set_exposure", ["15", "3", "tele"], snap, device))
        self.assertTrue(camera_param_unchanged("set_exposure", ["15.0", "3", "tele"], snap, device))
        self.assertFalse(camera_param_unchanged("set_exposure", ["30", "3", "tele"], snap, device))
        self.assertFalse(camera_param_unchanged("set_exposure", ["15", "3", "tele"], {"exposure_text": "—"}, device))
        self.assertTrue(camera_param_unchanged("set_gain", [80, "tele"], snap, device))
        self.assertTrue(camera_param_unchanged("set_gain", [20, "3", "wide"], snap, device))
        self.assertFalse(camera_param_unchanged("set_gain", [40, "tele"], snap, device))
        self.assertTrue(camera_param_unchanged("set_count", [60, "tele"], snap, device))
        self.assertFalse(camera_param_unchanged("set_count", [40, "tele"], snap, device))
        self.assertTrue(camera_param_unchanged("set_ir", ["VIS"], snap, device))
        self.assertFalse(camera_param_unchanged("set_ir", ["Duo-Band Filter"], snap, device))

    def test_wide_exposure_uses_wide_telemetry(self) -> None:
        from astro_dwarf.device_worker import camera_param_unchanged

        snap = {"exposure_text": "15", "wide_exposure_text": "1"}
        self.assertTrue(camera_param_unchanged("set_exposure", ["1", "3", "wide"], snap, {}))
        self.assertFalse(camera_param_unchanged("set_exposure", ["15", "3", "wide"], snap, {}))


if __name__ == "__main__":
    unittest.main()
