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


if __name__ == "__main__":
    unittest.main()
