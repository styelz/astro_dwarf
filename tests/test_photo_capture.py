from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_BURST_PROGRESS,
    CMD_NOTIFY_BURST_STATE,
    CMD_NOTIFY_RECORD_TIME,
    CMD_NOTIFY_TELE_RECORD_TIME,
    CMD_NOTIFY_TELE_TIMELAPSE_OUT_TIME,
    CMD_NOTIFY_TIMELAPSE_OUT_TIME,
    CMD_NOTIFY_TIMELAPSE_STATE,
    TYPE_NOTIFICATION,
    TelemetryTap,
)
from astro_dwarf.device_worker import (
    camera_param_unchanged,
    capture_prime_needs_mode_reset,
    running_photo_capture_stop,
    shooting_state_changes,
)
from astro_dwarf.telemetry_view import (
    AlertEngine,
    camera_params_to_telemetry,
    derive_activity,
    photo_capture_seconds,
    timelapse_shoot_seconds,
    timelapse_video_seconds,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_photo_capture_seconds_keeps_hud_seconds() -> None:
    _assert(photo_capture_seconds("30") == 30, "HUD 30 is 30 seconds, not 30 minutes")
    _assert(photo_capture_seconds("1") == 1, "interval 1 is 1 second")
    _assert(photo_capture_seconds("60") == 60, "HUD 60 is 60 seconds")
    _assert(photo_capture_seconds("2 min") == 120, "firmware 2 min stays 120 seconds")
    _assert(photo_capture_seconds("1 s") == 1, "1 s strips the unit")
    _assert(photo_capture_seconds("Off") == 0, "Off is unlimited/zero")
    _assert(photo_capture_seconds("∞") == 0, "infinity is unlimited")


def test_timelapse_video_length_uses_thirty_fps() -> None:
    _assert(timelapse_shoot_seconds(30, 1) == 900, "30 s video at 1 fps is a 15 min shoot")
    _assert(timelapse_video_seconds(900, 1) == 30, "900 s at 1 fps plays as 30 s")
    _assert(timelapse_shoot_seconds(4, 5) == 600, "manual example: 4 s video, 5 s interval, 10 min shoot")
    _assert(timelapse_video_seconds(600, 5) == 4, "10 min at 5 s is a 4 s video")
    _assert(timelapse_shoot_seconds(30, 2) == 1800, "same video at 2 s between frames shoots twice as long")


def test_camera_params_report_video_length_not_shoot_time() -> None:
    changes = camera_params_to_telemetry(
        {"cameras": [{"timelapse": {"interval": 1, "duration": 900}}]},
    )
    _assert(changes.get("timelapse_interval") == "1", changes)
    _assert(changes.get("timelapse_shoot_s") == 900, changes)
    _assert(changes.get("timelapse_duration") == "30", changes)


def test_sdk_duration_by_name_would_have_sent_minutes() -> None:
    from dwarf_python_api.lib.data_utils import get_timelapse_totaltime_seconds_by_name

    _assert(
        get_timelapse_totaltime_seconds_by_name("30") == 1800,
        "SDK by-name still treats 30 as 30 minutes; we must not call it",
    )
    _assert(photo_capture_seconds("30") != get_timelapse_totaltime_seconds_by_name("30"), "HUD seconds vs SDK minutes")


def test_derive_activity_unlatches_burst_and_timelapse() -> None:
    _assert(derive_activity({"burst_state": "running", "burst_count": 3}) == ("burst", "3 SHOTS"), "running burst")
    _assert(derive_activity({"burst_state": "idle"}) == ("", ""), "idle burst does not stay latched")
    _assert(
        derive_activity({"timelapse_state": "running", "timelapse_elapsed_s": 12, "timelapse_total_s": 30})
        == ("timelapse", "00:12 / 00:30"),
        "running timelapse shows elapsed/total",
    )
    _assert(derive_activity({"timelapse_state": "idle"}) == ("", ""), "idle timelapse does not stay latched")


def test_burst_and_timelapse_complete_toasts() -> None:
    engine = AlertEngine()
    burst = engine.evaluate({"burst_state": "running"}, {"burst_state": "idle", "burst_count": 3})
    _assert(any(item["message"] == "Burst complete" for item in burst), burst)
    lapse = engine.evaluate({"timelapse_state": "running"}, {"timelapse_state": "idle"})
    _assert(any(item["message"] == "Timelapse complete" for item in lapse), lapse)


def test_notify_decodes_burst_idle_and_timelapse_progress() -> None:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0)
    tap._notify = notify_pb2
    tap._base = object()

    burst = notify_pb2.BurstState()
    burst.state = 0
    changes = tap._decode(CMD_NOTIFY_BURST_STATE, TYPE_NOTIFICATION, burst.SerializeToString())
    _assert(changes.get("burst_state") == "idle", changes)

    running = notify_pb2.TimeLapseState()
    running.state = 1
    changes = tap._decode(CMD_NOTIFY_TIMELAPSE_STATE, TYPE_NOTIFICATION, running.SerializeToString())
    _assert(changes.get("timelapse_state") == "running", changes)

    progress = notify_pb2.TimeLapseOutTime()
    progress.interval = 1
    progress.out_time = 12
    progress.total_time = 30
    changes = tap._decode(CMD_NOTIFY_TIMELAPSE_OUT_TIME, TYPE_NOTIFICATION, progress.SerializeToString())
    _assert(changes.get("timelapse_state") == "running", changes)
    _assert("timelapse_elapsed_s" not in changes, changes)
    _assert(changes.get("timelapse_out_s") == 12, changes)
    _assert(changes.get("timelapse_total_s") == 30, changes)


def test_notify_decodes_v3_record_and_burst_progress() -> None:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0)
    tap._notify = notify_pb2
    tap._base = object()

    rec = notify_pb2.RecordTime()
    rec.record_time = 9
    changes = tap._decode(CMD_NOTIFY_RECORD_TIME, TYPE_NOTIFICATION, rec.SerializeToString())
    _assert(changes.get("record_seconds") == 9, changes)
    _assert(changes.get("record_state") == "running", changes)

    tele = notify_pb2.RecordTime()
    tele.record_time = 4
    changes = tap._decode(CMD_NOTIFY_TELE_RECORD_TIME, TYPE_NOTIFICATION, tele.SerializeToString())
    _assert(changes.get("record_seconds") == 4, changes)

    lapse = notify_pb2.TimeLapseOutTime()
    lapse.interval = 5
    lapse.out_time = 1
    lapse.total_time = 30
    changes = tap._decode(CMD_NOTIFY_TELE_TIMELAPSE_OUT_TIME, TYPE_NOTIFICATION, lapse.SerializeToString())
    _assert(changes.get("timelapse_state") == "running", changes)
    _assert(changes.get("timelapse_out_s") == 1, changes)
    _assert(changes.get("timelapse_total_s") == 30, changes)

    burst = notify_pb2.BurstProgress()
    burst.total_count = 3
    burst.completed_count = 2
    changes = tap._decode(CMD_NOTIFY_BURST_PROGRESS, TYPE_NOTIFICATION, burst.SerializeToString())
    _assert(changes.get("burst_state") == "running", changes)
    _assert(changes.get("burst_completed") == 2, changes)
    _assert(changes.get("burst_total") == 3, changes)


def test_record_and_timelapse_clocks_tick_from_start_stamp() -> None:
    now = 1_800_000_000.0
    _assert(
        derive_activity({"record_state": "running", "record_seconds": 0, "record_started_at": now - 11}, now)
        == ("record", "00:11"),
        "record pad interpolates elapsed when V3 progress is missing",
    )
    _assert(
        derive_activity(
            {
                "timelapse_state": "running",
                "timelapse_elapsed_s": 1,
                "timelapse_out_s": 1,
                "timelapse_total_s": 30,
                "timelapse_duration": "30",
                "timelapse_started_at": now - 12,
            },
            now,
        )
        == ("timelapse", "00:12 / 15:00 · OUT 00:01 / 00:30"),
        "timelapse shows capture elapsed against the shoot and the 30 fps file separately",
    )
    _assert(
        derive_activity(
            {
                "timelapse_state": "running",
                "timelapse_elapsed_s": 0,
                "timelapse_total_s": 1800,
                "timelapse_duration": "30",
                "timelapse_interval": "1",
                "timelapse_started_at": now - 8,
            },
            now,
        )
        == ("timelapse", "00:08 / 15:00 · OUT 00:00 / 00:30"),
        "a 30 s video at 1 fps shoots for 15 min, not the leftover 30 min total",
    )
    _assert(
        derive_activity(
            {
                "timelapse_state": "running",
                "timelapse_elapsed_s": 8,
                "timelapse_total_s": 14,
                "timelapse_duration": "30",
                "timelapse_interval": "1",
                "timelapse_started_at": now - 8,
            },
            now,
        )
        == ("timelapse", "00:08 / 15:00 · OUT 00:00 / 00:30"),
        "firmware total_time must not replace the video length",
    )


def test_record_activity_beats_stale_stack() -> None:
    _assert(
        derive_activity({"record_state": "running", "record_seconds": 3, "capture_active": True})
        == ("record", "00:03"),
        "leftover stacking telemetry must not hide a live recording",
    )
    _assert(
        derive_activity({"burst_state": "running", "burst_completed": 1, "burst_total": 3})
        == ("burst", "1/3"),
        "burst pad shows completed/total",
    )


def test_camera_param_skips_matching_timelapse_duration() -> None:
    _assert(
        camera_param_unchanged("set_timelapse_duration", [30], {"timelapse_duration": "30"}, {}),
        "30 s of video already selected must not be sent again",
    )
    _assert(
        not camera_param_unchanged("set_timelapse_duration", [30], {"timelapse_duration": "1800"}, {}),
        "a leftover shoot time is not the 30 s video",
    )
    _assert(
        camera_param_unchanged("set_burst_count", [3], {"burst_count": 3}, {}),
        "matching burst count is skipped",
    )


def test_cancel_prime_clears_stills_and_flags_burst_reset() -> None:
    cleared = shooting_state_changes(
        {"shooting_mode": 1, "shooting_tech": 1, "photo_primed": True},
        photo_primed=False,
    )
    _assert(cleared.get("photo_primed") is False, cleared)
    _assert(
        not capture_prime_needs_mode_reset({"shooting_mode": 1, "shooting_tech": 1, "photo_primed": True}),
        "stills priming is HUD-only",
    )
    _assert(capture_prime_needs_mode_reset({"shooting_mode": 1, "shooting_tech": 3}), "burst technique")
    _assert(capture_prime_needs_mode_reset({"shooting_mode": 1, "shooting_tech": 4}), "record technique")
    _assert(capture_prime_needs_mode_reset({"shooting_mode": 1, "shooting_tech": 5}), "timelapse technique")
    _assert(not capture_prime_needs_mode_reset({"shooting_mode": 2, "shooting_tech": 0}), "DSO is not capture-primed")
    _assert(running_photo_capture_stop({"burst_state": "running"}) == "burst_stop", "running burst")
    _assert(running_photo_capture_stop({"record_state": "running"}) == "record_stop", "running record")
    _assert(running_photo_capture_stop({"timelapse_state": "running"}) == "timelapse_stop", "running timelapse")
    _assert(running_photo_capture_stop({}, "burst") == "burst_stop", "activity latch")
    _assert(running_photo_capture_stop({"shooting_tech": 3, "burst_state": "idle"}) == "", "primed burst is not running")
    _assert(running_photo_capture_stop({"capture_active": True}, "imaging") == "", "stack is not a capture prime")


def test_burst_start_packet_is_empty() -> None:
    from dwarf_python_api.proto import camera_pb2

    empty = camera_pb2.ReqBurstPhoto()
    stuffed = camera_pb2.ReqBurstPhoto()
    stuffed.count = 3
    _assert(not empty.SerializeToString(), "official burst start omits count")
    _assert(stuffed.SerializeToString(), "setting count would serialize a field firmware does not expect on start")
    _assert(list(empty.DESCRIPTOR.fields_by_name) == ["count"], empty.DESCRIPTOR.fields_by_name)


def test_tap_stamps_record_start_clock() -> None:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0)
    tap.update({"record_state": "running"}, force=True)
    snap = tap.snapshot()
    _assert(snap.get("record_state") == "running", snap)
    _assert(float(snap.get("record_started_at") or 0) > 1_000_000_000, snap)
    tap.update({"record_state": "running", "record_seconds": 4}, force=True)
    later = tap.snapshot()
    _assert(later.get("record_started_at") == snap.get("record_started_at"), later)


def test_wide_tap_autofocus_follows_firmware_state_not_focus_position() -> None:
    import time

    from astro_dwarf import device_worker

    class Tap:
        def __init__(self, snap: dict) -> None:
            self.data = dict(snap)
            self._hold_photo_autofocus = False

        def snapshot(self) -> dict:
            return dict(self.data)

        def update(self, changes: dict, force: bool = False) -> None:
            self.data.update(changes)

    previous = device_worker._tap
    device_worker._reset_linkage_autofocus_watch()
    device_worker._reset_photo_autofocus_watch()
    try:
        photo = Tap({"shooting_mode": 1, "focus_position": 1000, "autofocus_state": "idle"})
        device_worker._tap = photo
        device_worker._arm_linkage_autofocus_watch()
        now = time.monotonic()
        _assert(device_worker._linkage_af_until > now, "photo tap polls focus state")
        _assert(device_worker._state_refresh_seconds(photo.snapshot(), now) == device_worker._LINKAGE_AF_POLL_S, "fast poll")
        device_worker._maybe_poll_linkage_autofocus(now, {"focus_position": 1400, "autofocus_state": "idle"})
        _assert(photo.data.get("autofocus_state") == "idle", photo.data)
        _assert(not photo._hold_photo_autofocus, "a finished position must not hold the pad")
        _assert(device_worker._linkage_af_until > now, "position jump does not end the watch")

        running = {"focus_position": 1400, "autofocus_state": "running"}
        device_worker._maybe_poll_linkage_autofocus(now, running)
        _assert(device_worker._linkage_af_until == 0.0, "firmware running owns the pad")
        activity, _detail = derive_activity(running)
        _assert(activity == "autofocus", activity)

        device_worker._reset_photo_autofocus_watch()
        dso = Tap({"shooting_mode": 2, "focus_position": 1000, "autofocus_state": "idle"})
        device_worker._tap = dso
        device_worker._arm_linkage_autofocus_watch()
        _assert(device_worker._linkage_af_until > time.monotonic(), "dso tap also polls")
        device_worker._maybe_poll_linkage_autofocus(
            time.monotonic(), {"focus_position": 1200, "autofocus_state": "idle"}
        )
        _assert(dso.data.get("autofocus_state") == "idle", dso.data)

        video = Tap({"shooting_mode": 0, "focus_position": 1000, "autofocus_state": "idle"})
        device_worker._tap = video
        device_worker._arm_linkage_autofocus_watch()
        _assert(device_worker._linkage_af_until == 0.0, "video tap does not watch focus")
    finally:
        device_worker._reset_linkage_autofocus_watch()
        device_worker._reset_photo_autofocus_watch()
        device_worker._tap = previous


def main() -> None:
    test_photo_capture_seconds_keeps_hud_seconds()
    test_timelapse_video_length_uses_thirty_fps()
    test_camera_params_report_video_length_not_shoot_time()
    test_sdk_duration_by_name_would_have_sent_minutes()
    test_derive_activity_unlatches_burst_and_timelapse()
    test_burst_and_timelapse_complete_toasts()
    test_notify_decodes_burst_idle_and_timelapse_progress()
    test_notify_decodes_v3_record_and_burst_progress()
    test_record_and_timelapse_clocks_tick_from_start_stamp()
    test_record_activity_beats_stale_stack()
    test_tap_stamps_record_start_clock()
    test_camera_param_skips_matching_timelapse_duration()
    test_cancel_prime_clears_stills_and_flags_burst_reset()
    test_burst_start_packet_is_empty()
    test_wide_tap_autofocus_follows_firmware_state_not_focus_position()
    print("test_photo_capture: ok")


if __name__ == "__main__":
    main()
