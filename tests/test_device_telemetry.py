import unittest

from dwarf_python_api.proto import notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_LONG_EXP_PROGRESS,
    CMD_NOTIFY_TELE_LONG_EXP_PROGRESS,
    CMD_NOTIFY_WIDE_LONG_EXP_PROGRESS,
    TYPE_NOTIFICATION,
    TelemetryTap,
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


if __name__ == "__main__":
    unittest.main()
