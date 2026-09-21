from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_worker import camera_param_unchanged
from astro_dwarf.qt_backend import (
    control_restore_should_set_auto_calibration,
    mosaic_capture_continues,
    mosaic_accept_live_frame,
    mosaic_finished_pane,
    mosaic_hold_pane,
    mosaic_live_still_camera,
    mosaic_preview_keep_live_sheet,
    mosaic_preview_should_open_wide,
    mosaic_frozen_takes_dropped_enhance,
    mosaic_goto_failed_result,
    mosaic_group_sessions,
    mosaic_live_pane,
    mosaic_overlay_live_pane,
    mosaic_pane_may_replace_frozen,
    mosaic_progress_phase,
    mosaic_result_holds_sheet,
    mosaic_result_pane,
    mosaic_result_should_drop_sheet,
    mosaic_should_copy_live_still,
    mosaic_should_hold_last_live_frame,
    mosaic_should_publish_pane_url,
    mosaic_should_refresh_slew_placeholder,
    mosaic_slew_frame_ready,
    mosaic_slew_live_pane,
    mosaic_slew_preview_should_restore,
    mosaic_stack_preview_should_retarget,
    mosaic_stack_reset_seen,
    preview_camera_needs_open,
    preview_can_attach_rtsp,
    preview_needs_rtsp_restart,
    preview_should_preserve_shooting_mode,
    preview_should_restore_dso,
    preview_should_reuse_player,
    preview_should_skip_go_live,
)
from astro_dwarf.stream_preview import MosaicFrames, MosaicLiveItem, live_frame_data_url
from astro_dwarf.telemetry_view import camera_params_to_telemetry


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_mosaic_live_item_font_pixel_size() -> None:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    item = MosaicLiveItem()
    _assert(item.fontPixelSize == 11, "default mosaic index font")
    item.fontPixelSize = 16
    _assert(item.fontPixelSize == 16, "scaled mosaic index font")
    item.fontPixelSize = 0
    _assert(item.fontPixelSize == 11, "invalid mosaic index font falls back")
    del app


def test_preview_preserves_dso_after_tracking() -> None:
    _assert(
        preview_should_preserve_shooting_mode({"shooting_mode": 2, "tracking_state": "idle"}, 1),
        "DSO mode must keep live view from forcing PHOTO",
    )
    _assert(
        preview_should_preserve_shooting_mode({"shooting_mode": 1, "tracking_state": "running"}, 1),
        "Active tracking must keep live view from forcing PHOTO",
    )
    _assert(
        not preview_should_preserve_shooting_mode({"shooting_mode": 1, "tracking_state": "idle"}, 1),
        "PHOTO mode without tracking can use the photo-mode camera open",
    )


def test_preview_skips_golive_after_tracking() -> None:
    _assert(
        preview_should_skip_go_live({"shooting_mode": 2, "tracking_state": "idle"}),
        "DSO after tracking must not send GoLive",
    )
    _assert(
        preview_should_skip_go_live({"shooting_mode": 1, "tracking_state": "running"}),
        "Active tracking must not send GoLive",
    )
    _assert(
        not preview_should_skip_go_live({"shooting_mode": 2, "capture_state": "running"}),
        "A running capture still needs GoLive before live view",
    )
    _assert(
        not preview_should_skip_go_live({"shooting_mode": 1, "tracking_state": "idle"}),
        "PHOTO mode still uses GoLive then photo_mode",
    )
    _assert(
        preview_should_skip_go_live({}, 2),
        "Persisted DSO after reconnect must not send GoLive before telemetry arrives",
    )


def test_preview_attaches_when_rtsp_is_already_live() -> None:
    _assert(
        preview_can_attach_rtsp({"stream_type": "RTSP", "shooting_mode": 1}),
        "A live tele RTSP encoder must attach instead of restarting cameras",
    )
    _assert(
        preview_can_attach_rtsp({"stream_type": "rtsp"}),
        "stream type from firmware is case-insensitive",
    )
    _assert(
        preview_can_attach_rtsp({"stream_type_wide": "RTSP"}),
        "A live wide RTSP encoder must attach even if tele is not advertised",
    )
    _assert(
        not preview_can_attach_rtsp({"stream_type": "JPEG"}, preview_result=True),
        "leftover stacking JPEG must restart cameras instead of attaching",
    )
    _assert(
        preview_can_attach_rtsp({}, tele_playing=True),
        "An already-playing tele player must attach",
    )
    _assert(
        not preview_can_attach_rtsp({"stream_type": "OFF"}),
        "First connect after reboot still has to open the cameras",
    )
    _assert(
        not preview_can_attach_rtsp({"stream_type": "JPEG"}),
        "Stacking JPEG is not a live RTSP attach",
    )
    _assert(
        not preview_can_attach_rtsp({"stream_type": "RTSP", "capture_state": "running"}),
        "A running capture must not skip GoLive",
    )
    _assert(
        not preview_can_attach_rtsp({"stream_type": "JPEG", "capture_state": "running"}, preview_result=True),
        "A running stack must not be treated as a live RTSP attach",
    )
    _assert(not preview_can_attach_rtsp({}), "Missing stream type is not an attach")


def test_preview_restarts_rtsp_after_stacking_jpeg() -> None:
    leftover = {"stream_type": "JPEG", "shooting_mode": 2}
    _assert(preview_needs_rtsp_restart(leftover), "idle JPEG leftover must restart RTSP")
    _assert(
        not preview_should_preserve_shooting_mode(leftover),
        "DSO leftover JPEG must switch to photo mode to start RTSP",
    )
    _assert(
        not preview_should_skip_go_live(leftover),
        "leftover stacking JPEG still needs GoLive before photo mode",
    )
    _assert(
        not preview_can_attach_rtsp(leftover, preview_result=True),
        "START LIVE VIEW after a stack must not attach to a dead JPEG encoder",
    )
    _assert(
        not preview_needs_rtsp_restart({"stream_type": "JPEG", "capture_state": "running"}),
        "a running stack must keep the HTTP stacking preview",
    )
    _assert(
        not preview_needs_rtsp_restart({"stream_type": "RTSP", "shooting_mode": 2}),
        "live RTSP after tracking must not force photo mode",
    )
    _assert(
        preview_should_skip_go_live({"stream_type": "RTSP", "shooting_mode": 2}),
        "DSO with live RTSP still skips GoLive",
    )
    _assert(
        preview_can_attach_rtsp({"stream_type": "RTSP"}, preview_result=True),
        "a finished stack that already has RTSP can attach",
    )
    _assert(
        preview_should_restore_dso(leftover),
        "DSO leftover JPEG must return to DSO after photo mode restarts RTSP",
    )
    _assert(
        preview_should_restore_dso({"stream_type": "JPEG"}, 2),
        "persisted DSO still restores after a JPEG leftover",
    )
    _assert(
        not preview_should_restore_dso({"stream_type": "JPEG", "shooting_mode": 1}),
        "PHOTO leftover JPEG stays in photo mode",
    )
    _assert(
        not preview_should_restore_dso({"stream_type": "RTSP", "shooting_mode": 2}),
        "live DSO RTSP does not take the photo-mode detour",
    )


def test_preview_opens_only_the_dark_camera() -> None:
    both = {"stream_type": "RTSP", "stream_type_wide": "RTSP"}
    _assert(not preview_camera_needs_open(both, "tele"), "live tele does not need enter_camera")
    _assert(not preview_camera_needs_open(both, "wide"), "live wide does not need open_wide")
    wide_only = {"stream_type_wide": "RTSP"}
    _assert(
        preview_camera_needs_open(wide_only, "tele"),
        "wide-only RTSP must open the dark tele camera",
    )
    _assert(
        not preview_camera_needs_open(wide_only, "wide"),
        "the live wide encoder must not be reopened",
    )
    leftover = {"stream_type": "JPEG"}
    _assert(
        not preview_camera_needs_open(leftover, "tele", preview_result=True),
        "leftover JPEG after a stack uses photo_mode, not enter_camera",
    )
    _assert(
        not preview_camera_needs_open(leftover, "wide", preview_result=True),
        "leftover JPEG after a stack must not open_wide",
    )
    _assert(
        not preview_camera_needs_open(
            {"stream_type": "JPEG", "capture_state": "running"},
            "tele",
        ),
        "a running stack does not send RTSP camera-open",
    )
    _assert(
        not preview_camera_needs_open({"stream_type": "OFF"}, "tele", playing=True),
        "a player that is already showing tele must not reopen it",
    )
    _assert(
        preview_camera_needs_open({"stream_type": "RTSP", "stream_type_wide": "OFF"}, "wide"),
        "explicitly off wide still needs open_wide",
    )


def test_preview_reuses_same_rtsp_player() -> None:
    rtsp = "rtsp://192.168.1.42/ch0/stream0"
    _assert(
        preview_should_reuse_player(rtsp, rtsp, True),
        "an already-playing RTSP player must keep its connection",
    )
    _assert(
        not preview_should_reuse_player(rtsp, rtsp, False),
        "a closed player with the same URL still has to open",
    )
    _assert(
        not preview_should_reuse_player(rtsp, "rtsp://192.168.1.42/ch1/stream0", True),
        "a different RTSP URL must start a new player",
    )
    http = "http://192.168.1.42:8092/mainstream"
    _assert(
        not preview_should_reuse_player(http, http, True),
        "stacking JPEG must reopen even when the URL is unchanged",
    )


def test_mosaic_goto_keeps_finished_frame_off_next_pane() -> None:
    _assert(mosaic_result_pane(2, "goto") == 1, "GOTO pane 2 still owns pane 1's stack")
    _assert(mosaic_result_pane(1, "complete") == 1, "completed pane 1")
    _assert(mosaic_result_pane(2, "stacking") == 2, "stacking pane 2 keeps its own frames")
    _assert(mosaic_live_pane(2, "goto") == 0, "slew must not own the stacking JPEG stream")
    _assert(mosaic_slew_live_pane(2, "goto") == 2, "camera RTSP overlays the pane being slewed")
    _assert(mosaic_slew_live_pane(1, "stacking") == 0, "stacking is not a slew overlay")
    _assert(mosaic_live_pane(1, "stacking") == 1, "live stays on the stacking pane")
    _assert(mosaic_live_pane(2, "stacking", False) == 0, "inactive mosaic has no live pane")
    _assert(
        mosaic_overlay_live_pane(
            current_index=1,
            phase="goto",
            preview_playing=True,
        )
        == 1,
        "first pane GOTO shows the live camera until stacking starts",
    )
    _assert(
        mosaic_overlay_live_pane(
            current_index=2,
            phase="goto",
            stacking_preview=True,
            preview_playing=True,
        )
        == 0,
        "leftover stacked.jpg must not paint the next pane during GOTO",
    )
    _assert(
        mosaic_overlay_live_pane(
            current_index=2,
            phase="stacking",
            may_copy=True,
        )
        == 2,
        "accepted stack frames still overlay the stacking pane",
    )
    _assert(
        mosaic_overlay_live_pane(
            current_index=1,
            phase="stacking",
            preview_playing=True,
        )
        == 1,
        "camera RTSP stays in the pane after stack is commanded until HTTP starts",
    )
    _assert(
        mosaic_overlay_live_pane(
            current_index=1,
            phase="stacking",
            stacking_preview=True,
            preview_playing=True,
        )
        == 0,
        "HTTP leftover must not paint the stacking pane before its own frames",
    )
    _assert(mosaic_result_pane(1, "goto") == 0, "first pane slew has no finished still")
    _assert(mosaic_result_pane(3, "failed") == 2, "failed GOTO keeps the previous pane")
    _assert(mosaic_result_pane(1, "failed") == 0, "first pane GOTO fail publishes nothing")


def test_mosaic_keeps_preview_open_between_panes() -> None:
    _assert(
        mosaic_capture_continues(live_phase="goto", worker_running=True),
        "live mosaic still owns later panes while the worker is running",
    )
    _assert(
        mosaic_capture_continues(firmware_pane=2, firmware_panes=4, session_running=True),
        "firmware mosaic is not finished after pane 2 of 4",
    )
    _assert(
        not mosaic_capture_continues(live_phase="", worker_running=False, firmware_panes=1),
        "a single stack should freeze when capture ends",
    )
    _assert(
        mosaic_stack_preview_should_retarget(2, 1, True, False, False),
        "pane 2 must reopen the same stacking JPEG URL",
    )
    _assert(
        not mosaic_stack_preview_should_retarget(2, 2, True, False, False),
        "the same pane should not restart the stream on every telemetry tick",
    )
    _assert(
        mosaic_stack_preview_should_retarget(1, 0, True, True, False),
        "first stacking start still switches live view to HTTP",
    )
    _assert(mosaic_progress_phase("GOTO pane 2/4") == "goto", "slew")
    _assert(mosaic_progress_phase("Settling before stack") == "goto", "settle is not live stacking")
    _assert(
        mosaic_progress_phase("Settling after pane stack") == "complete",
        "post-stack settle must not treat the finished pane as a slew overlay",
    )
    _assert(
        mosaic_slew_preview_should_restore(
            stacking=False, mosaic_continues=True, playing=False, stack_mode=False
        ),
        "camera RTSP must come back between mosaic panes",
    )
    _assert(
        not mosaic_slew_preview_should_restore(
            stacking=False,
            mosaic_continues=True,
            playing=False,
            stack_mode=False,
            opening=True,
        ),
        "do not reopen RTSP on every telemetry tick while it is already opening",
    )
    _assert(
        not mosaic_slew_preview_should_restore(
            stacking=True, mosaic_continues=True, playing=False, stack_mode=True
        ),
        "stacking still uses the HTTP preview",
    )
    _assert(mosaic_progress_phase("GOTO pane 3/4 failed") == "failed", "failed GOTO is not a slew freeze")
    _assert(mosaic_hold_pane(1, "goto") == 1, "slew pane keeps the last live frame")
    _assert(mosaic_hold_pane(2, "stacking") == 2, "stacking pane keeps the last live frame")
    _assert(mosaic_hold_pane(2, "complete") == 0, "finished panes are not live placeholders")
    _assert(mosaic_hold_pane(0, "stacking") == 0, "a single STACK has no mosaic cell")
    _assert(
        mosaic_should_hold_last_live_frame(2),
        "a mosaic pane may defer HTTP until the last live frame is held",
    )
    _assert(
        not mosaic_should_hold_last_live_frame(0),
        "single STACK must switch to stacking preview immediately",
    )
    _assert(
        not mosaic_should_refresh_slew_placeholder(
            stacking_preview=False,
            frozen=False,
            may_copy=False,
            has_live_frame=True,
            tracking=False,
        ),
        "mid-slew frames stay off the contact sheet",
    )
    _assert(
        mosaic_should_refresh_slew_placeholder(
            stacking_preview=False,
            frozen=False,
            may_copy=False,
            has_live_frame=True,
            tracking=True,
            track_elapsed_s=3.0,
            settle_s=3.0,
        ),
        "after tracking settles, the last live frame may fill the pane",
    )
    _assert(
        mosaic_should_refresh_slew_placeholder(
            stacking_preview=False,
            frozen=False,
            may_copy=False,
            has_live_frame=True,
            stacking=True,
        ),
        "once stack is commanded, keep updating the last live frame",
    )
    _assert(
        not mosaic_should_refresh_slew_placeholder(
            stacking_preview=True,
            frozen=False,
            may_copy=False,
            has_live_frame=True,
            stacking=True,
        ),
        "leftover stacked.jpg must not replace the last live frame",
    )
    _assert(
        not mosaic_slew_frame_ready(has_frame=False),
        "do not drop live video before a last frame exists",
    )
    _assert(
        mosaic_slew_frame_ready(has_frame=True, stacking=True),
        "a live frame after stack is commanded is enough to hold",
    )
    _assert(
        mosaic_slew_frame_ready(has_frame=False, timed_out=True),
        "wait a few seconds for the last frame, then switch anyway",
    )
    _assert(mosaic_progress_phase("Stacking pane 2/4") == "stacking", "stack start")
    _assert(mosaic_progress_phase("Waiting for pane 2 · 6/15") == "stacking", "stack progress")
    _assert(mosaic_progress_phase("Pane 2/4 complete") == "complete", "pane done")
    _assert(mosaic_finished_pane(1, 2) == 1, "late capture-end still owns pane 1")
    _assert(mosaic_finished_pane(0, 2) == 2, "no stream pane falls back to result pane")
    _assert(not mosaic_stack_reset_seen(6, 6, False), "leftover pane-1 counts are not a reset")
    _assert(mosaic_stack_reset_seen(1, 0, False), "fresh 1 stacked is a reset")
    _assert(mosaic_stack_reset_seen(6, 6, True), "reset stays latched")
    _assert(
        not mosaic_accept_live_frame(pane=2, stream_pane=2, stacked=6, taken=6, seen_reset=False),
        "leftover JPEG must not fill pane 2",
    )
    _assert(
        mosaic_accept_live_frame(pane=2, stream_pane=2, stacked=1, taken=1, seen_reset=True),
        "pane 2 accepts frames after its own stack starts",
    )
    _assert(
        not mosaic_accept_live_frame(pane=2, stream_pane=1, stacked=1, taken=1, seen_reset=True),
        "live frames stay on the stream pane",
    )


def test_mosaic_rejects_leftover_wide_still() -> None:
    _assert(
        not mosaic_should_copy_live_still(
            camera="wide",
            phase="stacking",
            pane=3,
            stream_pane=3,
            capturing=True,
            stacked=1,
            taken=1,
            seen_reset=True,
        ),
        "wide JPEG after GoLive must not freeze into a tele cell",
    )
    _assert(
        not mosaic_should_copy_live_still(
            camera="tele",
            phase="goto",
            pane=3,
            stream_pane=3,
            capturing=False,
            stacked=6,
            taken=6,
            seen_reset=True,
        ),
        "slew frames must not publish into the next pane",
    )
    _assert(
        not mosaic_should_copy_live_still(
            camera="tele",
            phase="complete",
            pane=3,
            stream_pane=2,
            capturing=False,
            stacked=6,
            taken=6,
            seen_reset=True,
        ),
        "GoLive leftover after a pane stack must not replace the next cell",
    )
    _assert(
        not mosaic_should_copy_live_still(
            camera="tele",
            phase="stacking",
            pane=3,
            stream_pane=3,
            capturing=True,
            stacked=1,
            taken=1,
            seen_reset=True,
            stack_preview=False,
        ),
        "detached stacking preview must not freeze GoLive JPEG",
    )
    _assert(
        mosaic_should_copy_live_still(
            camera="tele",
            phase="stacking",
            pane=3,
            stream_pane=3,
            capturing=True,
            stacked=1,
            taken=1,
            seen_reset=True,
            stack_preview=True,
        ),
        "tele stack frames freeze while that pane is stacking",
    )


def test_mosaic_goto_fail_does_not_publish_pane_url() -> None:
    _assert(
        not mosaic_should_publish_pane_url(pane=3, has_still=False, goto_failed=True, failed_pane=3),
        "GOTO fail must not invent a pane URL",
    )
    _assert(
        not mosaic_should_publish_pane_url(pane=3, has_still=True, goto_failed=True, failed_pane=3),
        "leftover live on a failed GOTO pane is not a stacked still",
    )
    _assert(
        mosaic_should_publish_pane_url(pane=1, has_still=True, goto_failed=True, failed_pane=3),
        "already stacked panes keep their URLs",
    )
    _assert(
        mosaic_should_publish_pane_url(pane=1, has_still=True, goto_failed=False),
        "a stacked pane still publishes",
    )
    _assert(
        mosaic_goto_failed_result(
            "Mosaic pane 3/4 GOTO failed · RA 5.3600h Dec -69.700° (LMC pane 3) · "
            "not calibrated or this scene will not plate-solve. Not stacking this pane."
        ),
        "worker GOTO-fail text is recognized",
    )
    _assert(not mosaic_goto_failed_result("Mosaic complete"), "success is not a GOTO fail")


def test_mosaic_contact_sheet_never_freezes_wide() -> None:
    _assert(mosaic_live_still_camera() == "tele", "finished panes copy tele only")
    _assert(
        mosaic_preview_should_open_wide(mosaic_running=False),
        "live view may still open wide for PIP",
    )
    _assert(
        not mosaic_preview_should_open_wide(mosaic_running=True),
        "a running mosaic must not open the wide camera",
    )


def test_mosaic_group_sessions_uses_repository_all() -> None:
    from astro_dwarf.domain import Mosaic, Session, Target

    one = Session(
        name="Atria pane 1",
        target=Target(name="Atria"),
        device_id="dev-1",
        scheduled_start="2026-09-20T00:00:00+00:00",
        mosaic=Mosaic(group_id="g", rows=2, columns=2),
    )
    two = Session(
        name="Atria pane 2",
        target=Target(name="Atria"),
        device_id="dev-1",
        scheduled_start="2026-09-20T00:00:00+00:00",
        mosaic=Mosaic(group_id="g", rows=2, columns=2),
    )
    other = Session(
        name="Other",
        target=Target(name="Other"),
        device_id="dev-2",
        scheduled_start="2026-09-20T00:00:00+00:00",
        mosaic=Mosaic(group_id="g"),
    )

    class Repo:
        def all(self):
            return [one, two, other]

    found = mosaic_group_sessions(Repo(), "dev-1", "g")
    _assert(found == [one, two], found)
    _assert(mosaic_group_sessions(Repo(), "dev-1", "") == [], "empty group")
    try:
        Repo().values()
    except AttributeError:
        pass
    else:
        raise AssertionError("JsonRepository has all(), not values()")


def test_mosaic_frames_keep_completed_stills() -> None:
    from PySide6.QtGui import QImage, QColor

    frames = MosaicFrames()
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor(20, 40, 60))
    frames.set_layout(2, 2, 1, True, "live-mosaic-a")
    frames.put(1, image)
    frames.freeze(1)
    later = QImage(8, 8, QImage.Format.Format_RGB32)
    later.fill(QColor(200, 0, 0))
    frames.put(1, later)
    frames.set_layout(2, 2, 2, True, "live-mosaic-a")
    leftover = QImage(8, 8, QImage.Format.Format_RGB32)
    leftover.fill(QColor(20, 40, 60))
    frames.put(2, leftover)
    frames.freeze(2)
    other = QImage(8, 8, QImage.Format.Format_RGB32)
    other.fill(QColor(0, 180, 0))
    frames.put(2, other)
    _assert(1 in frames.indexes(), "same mosaic group must keep pane 1")
    _assert(frames.peek(1).pixelColor(0, 0).blue() == 60, "frozen pane 1 must keep its finished still")
    _assert(frames.peek(2).pixelColor(0, 0).blue() == 60, "frozen pane 2 must not take pane 1 leftover again")
    enhanced = QImage(8, 8, QImage.Format.Format_RGB32)
    enhanced.fill(QColor(8, 8, 8))
    frames.put(1, enhanced, replace_frozen=True)
    _assert(frames.peek(1).pixelColor(0, 0).red() == 8, "enhance may replace a frozen raw placeholder")
    frames.set_layout(2, 2, 3, True, "live-mosaic-b")
    _assert(1 in frames.indexes(), "layout updates must not wipe completed stills")
    _assert(mosaic_pane_may_replace_frozen(True), "enhance on may replace a frozen mosaic cell")
    _assert(not mosaic_pane_may_replace_frozen(False), "enhance off must keep the raw still")
    _assert(
        mosaic_frozen_takes_dropped_enhance(continues=True, capturing=False, frozen=True),
        "later mosaic panes must keep a delayed enhance after capture_active drops",
    )
    _assert(
        not mosaic_frozen_takes_dropped_enhance(continues=True, capturing=False, frozen=False),
        "live overlay must not take a dropped enhance onto the next pane",
    )
    _assert(
        not mosaic_frozen_takes_dropped_enhance(continues=True, capturing=True, frozen=True),
        "while capturing, live enhance still goes to the live overlay",
    )
    _assert(
        not mosaic_frozen_takes_dropped_enhance(continues=False, capturing=False, frozen=True),
        "a finished single stack is not a mosaic pane boundary",
    )


def test_sky_mosaic_urls_backfill_from_stored_stills() -> None:
    from PySide6.QtGui import QImage, QColor

    frames = MosaicFrames()
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor(20, 40, 60))
    frames.put(1, image)
    frames.put(3, image)
    frames.freeze(1)
    frames.freeze(3)
    urls = {}
    for index in frames.indexes():
        url = live_frame_data_url(frames.peek(index))
        if url:
            urls[str(index)] = url
    _assert(set(urls) == {"1", "3"}, "every stored still must get a SKY data URL")
    _assert(all(value.startswith("data:image/jpeg;base64,") for value in urls.values()), urls)


def test_mosaic_result_keeps_contact_sheet_until_dismissed() -> None:
    _assert(
        mosaic_result_holds_sheet(preview_result=True, active=True, columns=2, rows=2),
        "a finished mosaic must keep the contact sheet while the result is on screen",
    )
    _assert(
        mosaic_result_holds_sheet(preview_result=False, active=True, columns=2, rows=2, held=True),
        "the sheet must stay through the gap between mosaic-complete and previewResult",
    )
    _assert(
        not mosaic_result_holds_sheet(preview_result=True, active=True, columns=1, rows=1),
        "a single stack result is not a mosaic sheet",
    )
    _assert(
        not mosaic_result_holds_sheet(preview_result=False, active=True, columns=2, rows=2),
        "dismissing the result must drop the held mosaic sheet",
    )


def test_mosaic_dismiss_drops_leftover_sheet_and_sky_stills() -> None:
    _assert(
        mosaic_result_should_drop_sheet(
            preview_result=True, held=True, frames_active=True, columns=2, rows=2
        ),
        "Dismiss must clear the finished mosaic sheet",
    )
    _assert(
        mosaic_result_should_drop_sheet(
            preview_result=False, held=True, frames_active=True, columns=2, rows=2
        ),
        "Start live view must clear a held mosaic sheet even after the result overlay is gone",
    )
    _assert(
        mosaic_result_should_drop_sheet(
            preview_result=False, held=False, frames_active=True, columns=2, rows=2
        ),
        "leftover mosaic layout after dismiss must still be dropped",
    )
    _assert(
        not mosaic_result_should_drop_sheet(
            preview_result=True,
            held=True,
            frames_active=True,
            columns=2,
            rows=2,
            mosaic_running=True,
        ),
        "a running mosaic must keep its contact sheet",
    )


def test_mosaic_preview_hides_after_capture_without_held_result() -> None:
    _assert(
        mosaic_preview_keep_live_sheet(live_phase="stacking", worker_running=True),
        "live mosaic stacking still owns the sheet",
    )
    _assert(
        mosaic_preview_keep_live_sheet(mosaic_active=True, capturing=True),
        "firmware mosaic capture still owns the sheet",
    )
    _assert(
        mosaic_preview_keep_live_sheet(mosaic_active=True, capture_continues=True),
        "GOTO between mosaic panes still owns the sheet",
    )
    _assert(
        not mosaic_preview_keep_live_sheet(mosaic_active=True, capturing=False, capture_continues=False),
        "a finished session must not keep the live mosaic layout on its own",
    )
    _assert(
        not mosaic_preview_keep_live_sheet(live_phase="stacking", live_stopping=True),
        "a stopping mosaic without a worker is not a live capture",
    )


def test_mosaic_frames_clear_resets_grid() -> None:
    from PySide6.QtGui import QImage, QColor

    frames = MosaicFrames()
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor(20, 40, 60))
    frames.set_layout(2, 2, 1, True, "live-mosaic-a")
    frames.put(1, image)
    frames.clear()
    active, columns, rows, current, images = frames.snapshot()
    _assert(not active, "cleared mosaic frames are inactive")
    _assert(columns == 1 and rows == 1, "cleared mosaic frames must not keep the grid")
    _assert(current == 0 and not images, "cleared mosaic frames must drop stills")


def test_restore_skips_unknown_auto_calibration() -> None:
    _assert(not control_restore_should_set_auto_calibration("false", None), "unknown must not set")
    _assert(not control_restore_should_set_auto_calibration("false", False), "already off")
    _assert(control_restore_should_set_auto_calibration("false", True), "firmware on, saved off")
    _assert(not control_restore_should_set_auto_calibration("", False), "unset preference")


def test_camera_params_map_ir_and_auto_calibration() -> None:
    changes = camera_params_to_telemetry(
        {
            "cameras": {0: {"filterType": 1, "exposure": {"name": "15"}, "gain": {"value": 60}}},
            "shooting_mode": {"autoCalibration": False},
            "tech_settings": {0: {"stackCount": 5}},
        }
    )
    _assert(changes.get("ir_filter") == "Astro Filter", changes)
    _assert(changes.get("auto_calibration") is False, changes)
    _assert(changes.get("stack_count") == 5, changes)
    _assert(changes.get("exposure_text") == "15", changes)
    _assert(
        camera_param_unchanged("set_auto_calibration", [False], changes, {}),
        "worker must skip a matching auto-cal set",
    )


if __name__ == "__main__":
    test_mosaic_live_item_font_pixel_size()
    test_preview_preserves_dso_after_tracking()
    test_preview_skips_golive_after_tracking()
    test_preview_attaches_when_rtsp_is_already_live()
    test_preview_opens_only_the_dark_camera()
    test_preview_reuses_same_rtsp_player()
    test_mosaic_goto_keeps_finished_frame_off_next_pane()
    test_mosaic_keeps_preview_open_between_panes()
    test_mosaic_rejects_leftover_wide_still()
    test_mosaic_goto_fail_does_not_publish_pane_url()
    test_mosaic_contact_sheet_never_freezes_wide()
    test_mosaic_group_sessions_uses_repository_all()
    test_mosaic_frames_keep_completed_stills()
    test_sky_mosaic_urls_backfill_from_stored_stills()
    test_mosaic_result_keeps_contact_sheet_until_dismissed()
    test_mosaic_dismiss_drops_leftover_sheet_and_sky_stills()
    test_mosaic_preview_hides_after_capture_without_held_result()
    test_mosaic_frames_clear_resets_grid()
    test_restore_skips_unknown_auto_calibration()
    test_camera_params_map_ir_and_auto_calibration()
    print("ok")
