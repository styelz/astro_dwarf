"""Missing-dark prompts wait for a person, and unattended stacks do not."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dwarf_python_api.proto import notify_pb2

from astro_dwarf.device_telemetry import (
    CMD_NOTIFY_LONG_EXP_PROGRESS,
    CMD_NOTIFY_STATE_CAPTURE_WIDE_RAW_DARK,
    TYPE_NOTIFICATION,
    TelemetryTap,
)
from astro_dwarf import device_worker as worker


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


class _DarkTap:
    def __init__(self) -> None:
        self.phase = "idle"
        self.code: int | None = None

    def snapshot(self) -> dict[str, object]:
        return {"dark_state": self.phase, "cmos_tele_c": 12}

    def response_after(self, _command: int, _since: float) -> int | None:
        return self.code


def _restore(previous: dict[str, object]) -> None:
    worker._tap = previous["tap"]
    worker._device = previous["device"]
    worker._send_request = previous["send"]
    worker.send_without_response = previous["fire"]
    worker._stop_dark_capture = previous["stop_dark"]
    worker._continue_shooting = previous["continue"]
    worker._stop.clear()
    worker._begin_dark_prompt_run(False)
    worker._clear_stack_exposure()
    worker._stack_bin_index = 0


def _snapshot() -> dict[str, object]:
    return {
        "tap": worker._tap,
        "device": worker._device,
        "send": worker._send_request,
        "fire": worker.send_without_response,
        "stop_dark": worker._stop_dark_capture,
        "continue": worker._continue_shooting,
    }


def test_model_steps_follow_each_manual() -> None:
    dwarf3 = worker.dark_frame_steps("Dwarf 3")
    mini = worker.dark_frame_steps("Dwarf Mini")
    dwarf2 = worker.dark_frame_steps("Dwarf II")
    _assert("ND filter" in dwarf3 and "retract the lens cylinder" in dwarf3, dwarf3)
    _assert("before calibration" in dwarf3, dwarf3)
    _assert("dark shutter" in mini and "ND filter" not in mini, mini)
    _assert("lens cover" in dwarf2 and "ND filter" not in dwarf2 and "dark shutter" not in dwarf2, dwarf2)
    _assert(
        "different sensor temperature" in worker.dark_warning_summary(worker.CODE_ASTRO_DARK_TEMP_MISMATCH),
        "mismatch copy",
    )


def test_tele_gain_limits() -> None:
    _assert(not worker.dark_gain_allowed(39, wide=False), "39 is below the tele minimum")
    _assert(worker.dark_gain_allowed(40, wide=False), "40 is allowed")
    _assert(worker.dark_gain_allowed(150, wide=False), "150 is allowed")
    _assert(not worker.dark_gain_allowed(151, wide=False), "151 is above the tele maximum")
    _assert(worker.dark_gain_allowed(10, wide=True), "wide darks keep the stack gain")
    _assert(not worker.dark_gain_allowed(None, wide=True), "missing gain cannot be sent")
    _assert(worker.dark_gain_index(60, "3", False) == 18, "tele gain 60 is table index 18")
    _assert(worker.dark_gain_index(60, "3", True) == 18, "wide gain 60 is table index 18")
    _assert(worker.dark_exposure_index("15", "3", False) is not None, "15s is in the tele table")
    _assert(worker.dark_exposure_index("", "3", False) is None, "blank exposure is unknown")


def test_unprompted_run_continues_immediately() -> None:
    previous = _snapshot()
    continued: list[str] = []
    worker._begin_dark_prompt_run(False)
    worker._continue_shooting = lambda name: continued.append(name) or True
    try:
        outcome = worker._after_dark_warning("Stack", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False)
    finally:
        _restore(previous)
    _assert(outcome == "started", outcome)
    _assert(continued == ["Stack"], continued)


def test_schedule_dark_prompt_asks_once_then_skips() -> None:
    from astro_dwarf.services import SCHEDULE_DARK_TIMEOUT_S, schedule_dark_prompt

    prompt, timeout = schedule_dark_prompt(part_of_schedule=True, skipped=False)
    _assert(prompt is True and timeout == SCHEDULE_DARK_TIMEOUT_S, (prompt, timeout))
    _assert(timeout == 60, timeout)
    prompt, timeout = schedule_dark_prompt(part_of_schedule=True, skipped=True)
    _assert(prompt is False and timeout == 0, (prompt, timeout))
    prompt, timeout = schedule_dark_prompt(part_of_schedule=False, skipped=False)
    _assert(prompt is True and timeout == 60, (prompt, timeout))
    prompt, timeout = schedule_dark_prompt(part_of_schedule=False, skipped=True)
    _assert(prompt is True and timeout == 60, "Run Now with the scheduler off still asks")


def test_prompt_timeout_continues_and_skips_the_next_ask() -> None:
    previous = _snapshot()
    continued: list[str] = []
    phases: list[str] = []
    worker._stop.clear()
    worker._begin_dark_prompt_run(True, 1.2)
    worker._continue_shooting = lambda name: continued.append(name) or True
    real_emit = worker.emit

    def emit(payload: dict[str, object]) -> None:
        if payload.get("event") == "dark_prompt":
            phases.append(str(payload.get("phase") or ""))
            if payload.get("phase") == "ask":
                _assert(int(payload.get("timeout_s") or 0) == 1, payload)

    worker.emit = emit
    before = worker._dark_token
    holder: dict[str, object] = {}

    def run() -> None:
        holder["outcome"] = worker._after_dark_warning(
            "Stack", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False
        )

    thread = threading.Thread(target=run)
    thread.start()
    try:
        thread.join(3)
        _assert(not thread.is_alive(), "the countdown did not release the prompt")
        _assert(holder.get("outcome") == "started", holder)
        _assert(continued == ["Stack"], continued)
        _assert(worker._dark_token != before, "the prompt never opened")
        _assert(phases[:1] == ["ask"] and "timeout" in phases, phases)
        again = worker._dark_token
        outcome = worker._after_dark_warning(
            "Stack pane 2", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False
        )
        _assert(outcome == "started", outcome)
        _assert(worker._dark_token == again, "a timed-out run asked again")
        _assert(continued == ["Stack", "Stack pane 2"], continued)
    finally:
        if thread.is_alive():
            worker._stop.set()
            worker.accept_dark_prompt_reply(worker._dark_token, "cancel")
            thread.join(2)
        worker.emit = real_emit
        _restore(previous)


def test_manual_alignment_ignores_the_schedule_countdown() -> None:
    previous = _snapshot()
    worker._stop.clear()
    worker._session_active.clear()
    worker._dark_run_choice = None
    worker._begin_dark_prompt_run(True, 0.25)
    worker._device = {"camera": "tele", "model": "Dwarf 3"}
    worker._stack_exposure_name = "15"
    worker._stack_gain = 60
    worker._stack_bin_index = 0
    saved_query = worker._query_dark_library
    worker._query_dark_library = lambda _wide: []
    holder: dict[str, object] = {}

    def run() -> None:
        worker._offer_darks_before_manual_alignment("Calibrate")
        holder["done"] = True

    thread = threading.Thread(target=run)
    thread.start()
    try:
        time.sleep(0.45)
        _assert(thread.is_alive(), "the schedule countdown closed a manual dark prompt")
        _assert(worker.accept_dark_prompt_reply(worker._dark_token, "continue"), "continue was rejected")
        thread.join(2)
        _assert(holder.get("done") is True, holder)
        _assert(worker._dark_prompt_timeout_s == 0.25, worker._dark_prompt_timeout_s)
    finally:
        if thread.is_alive():
            worker._stop.set()
            worker.accept_dark_prompt_reply(worker._dark_token, "cancel")
            thread.join(2)
        worker._query_dark_library = saved_query
        _restore(previous)


def test_prompt_waits_to_continue() -> None:
    previous = _snapshot()
    continued: list[str] = []
    worker._stop.clear()
    worker._begin_dark_prompt_run(True)
    worker._continue_shooting = lambda name: continued.append(name) or True
    before = worker._dark_token
    holder: dict[str, object] = {}

    def run() -> None:
        holder["outcome"] = worker._after_dark_warning("Stack", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.time() + 2
        while worker._dark_token == before and time.time() < deadline:
            time.sleep(0.01)
        _assert(worker._dark_token != before, "the prompt did not open")
        _assert(worker.accept_dark_prompt_reply(worker._dark_token, "continue"), "continue was rejected")
        thread.join(2)
        _assert(not thread.is_alive(), "continue did not finish the wait")
        _assert(holder.get("outcome") == "started", holder)
        _assert(continued == ["Stack"], continued)
    finally:
        if thread.is_alive():
            worker._stop.set()
            worker.accept_dark_prompt_reply(worker._dark_token, "cancel")
            thread.join(2)
        _restore(previous)


def test_prompt_cancel_does_not_continue() -> None:
    previous = _snapshot()
    continued: list[str] = []
    worker._stop.clear()
    worker._begin_dark_prompt_run(True)
    worker._continue_shooting = lambda name: continued.append(name) or True
    before = worker._dark_token
    holder: dict[str, object] = {}

    def run() -> None:
        try:
            holder["outcome"] = worker._handle_missing_darks(
                "Stack", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False
            )
        except RuntimeError as exc:
            holder["error"] = str(exc)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.time() + 2
        while worker._dark_token == before and time.time() < deadline:
            time.sleep(0.01)
        _assert(worker.accept_dark_prompt_reply(worker._dark_token, "cancel"), "cancel was rejected")
        thread.join(2)
        _assert(not thread.is_alive(), "cancel did not finish the wait")
        _assert("cancelled" in str(holder.get("error") or ""), holder)
        _assert("outcome" not in holder, holder)
        _assert(continued == [], continued)
    finally:
        if thread.is_alive():
            worker._stop.set()
            thread.join(2)
        _restore(previous)


def test_take_darks_builds_the_firmware_request() -> None:
    previous = _snapshot()
    sent: list[tuple[int, int, int, int, int]] = []
    worker._device = {"model": "Dwarf 3"}
    worker._stack_exposure_name = "15"
    worker._stack_gain = 60
    worker._stack_bin_index = 0
    worker._tap = _DarkTap()
    tele_index = worker.dark_exposure_index("15", "3", False)
    wide_index = worker.dark_exposure_index("15", "3", True)

    def send(message, command, _module, timeout=None):
        sent.append((
            int(command),
            int(message.exp_index),
            int(message.gain_index),
            int(message.bin_index),
            int(message.cap_size),
        ))
        tap = worker._tap
        tap.phase = "running"

        def finish() -> None:
            time.sleep(0.05)
            tap.phase = "stopped"

        threading.Thread(target=finish, daemon=True).start()
        return True

    worker.send_without_response = send
    try:
        tele = worker._take_dark_frames("Stack", False, worker._dark_capture_settings(False), 1)
        worker._tap = _DarkTap()
        wide = worker._take_dark_frames("Stack", True, worker._dark_capture_settings(True), 1)
    finally:
        _restore(previous)
    _assert(tele == "", tele)
    _assert(wide == "", wide)
    _assert(sent[0] == (11021, tele_index, 18, 0, 10), sent[0])
    _assert(sent[1] == (11025, wide_index, 18, 0, 10), sent[1])


def test_device_not_activated_does_not_discard_finished_darks() -> None:
    previous = _snapshot()
    stopped: list[bool] = []
    worker._device = {"model": "Dwarf 3"}
    worker._stack_exposure_name = "15"
    worker._stack_gain = 50
    worker._stack_bin_index = 0
    tap = _DarkTap()
    tap.code = -5
    worker._tap = tap

    def send(_message, _command, _module, timeout=None):
        tap.phase = "running"

        def finish() -> None:
            time.sleep(0.05)
            tap.phase = "stopped"

        threading.Thread(target=finish, daemon=True).start()
        return True

    worker.send_without_response = send
    worker._stop_dark_capture = lambda _wide: stopped.append(True)
    try:
        result = worker._take_dark_frames("Stack", False, worker._dark_capture_settings(False), 1)
    finally:
        _restore(previous)
    _assert(result == "", result)
    _assert(stopped == [], stopped)


def test_library_match_uses_exposure_gain_and_temperature() -> None:
    # Live DWARF 3 library: gain 60 is stored as index 18, name "60".
    settings = {
        "exp_index": 156,
        "gain": 60,
        "gain_index": 18,
        "bin_index": 0,
        "temperature": "35°C",
    }
    frames = [{
        "exp_index": 156,
        "gain_index": 18,
        "gain_name": "60",
        "bin_index": 0,
        "temperature": 28,
    }]
    _assert(worker.dark_library_status(frames, settings) == "match", "gain name 60, within 8°C")
    frames[0]["temperature"] = 50
    _assert(worker.dark_library_status(frames, settings) == "mismatch", "outside 8°C")
    frames[0]["gain_name"] = "80"
    _assert(worker.dark_library_status(frames, settings) == "missing", "different gain name")
    frames[0]["gain_name"] = ""
    frames[0]["temperature"] = 28
    _assert(worker.dark_library_status(frames, settings) == "match", "table index 18")
    frames[0]["gain_index"] = 60
    _assert(worker.dark_library_status(frames, settings) == "missing", "raw gain is not the index")


def test_cancel_does_not_block_the_next_manual_command() -> None:
    previous = _snapshot()
    worker._stop.clear()
    worker._session_active.clear()
    worker._dark_run_choice = "cancel"
    worker._tap = None
    worker._device = {"camera": "wide", "model": "Dwarf 3"}
    try:
        worker._offer_darks_before_manual_alignment("Stack")
        choice = worker._dark_run_choice
    finally:
        _restore(previous)
    _assert(choice is None, choice)


def test_stop_dark_capture_sends_wide_and_plain_stops() -> None:
    previous = _snapshot()
    sent: list[int] = []

    def send(_message, command, _module, timeout=None):
        sent.append(int(command))
        return True

    worker.send_without_response = send
    try:
        worker._stop_dark_capture(True)
    finally:
        _restore(previous)
    _assert(sent == [11026, 11008], sent)


def test_remembered_continue_skips_the_next_pane() -> None:
    previous = _snapshot()
    continued: list[str] = []
    worker._begin_dark_prompt_run(True)
    worker._dark_run_choice = "continue"
    worker._continue_shooting = lambda name: continued.append(name) or True
    before = worker._dark_token
    try:
        outcome = worker._after_dark_warning("Stack pane 2", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False)
    finally:
        _restore(previous)
    _assert(outcome == "started", outcome)
    _assert(worker._dark_token == before, "a remembered continue must not open the modal")
    _assert(continued == ["Stack pane 2"], continued)


def test_long_exposure_progress_counts_as_dark_frames() -> None:
    """DWARF 3 sends 15288 once per dark frame and never sends dark_state."""
    previous = _snapshot()
    saved = (worker.DARK_FRAME_COUNT, worker._DARK_FRAME_QUIET_S, worker._DARK_START_TIMEOUT_S)
    worker.DARK_FRAME_COUNT = 2
    worker._DARK_FRAME_QUIET_S = 0.05
    worker._DARK_START_TIMEOUT_S = 0.4
    tap = _DarkTap()
    tap.progress = 0.0
    worker._device = {"model": "Dwarf 3"}
    worker._tap = tap

    def snapshot() -> dict[str, object]:
        return {"dark_state": "idle", "exposure_progress_at": tap.progress}

    tap.snapshot = snapshot

    def send(_message, _command, _module, timeout=None):
        def tick() -> None:
            time.sleep(0.05)
            tap.progress = time.monotonic()
            time.sleep(0.3)
            tap.progress = time.monotonic()

        threading.Thread(target=tick, daemon=True).start()
        return True

    settings = {
        "gain_ok": True,
        "exposure_ok": True,
        "exp_index": 1,
        "gain": 50,
        "bin_index": 0,
        "gain_index": 15,
        "exposure": "0.05",
    }
    worker.send_without_response = send
    try:
        result = worker._take_dark_frames("Stack", False, settings, 1)
    finally:
        worker.DARK_FRAME_COUNT, worker._DARK_FRAME_QUIET_S, worker._DARK_START_TIMEOUT_S = saved
        _restore(previous)
    _assert(result == "", result)


def test_dark_frame_clock_ticks_between_notifications() -> None:
    """15288 arrives once per frame with exposured_time 0. The modal still counts."""
    previous = _snapshot()
    saved = (worker.DARK_FRAME_COUNT, worker._DARK_FRAME_QUIET_S, worker._DARK_START_TIMEOUT_S)
    worker.DARK_FRAME_COUNT = 1
    worker._DARK_FRAME_QUIET_S = 0.05
    worker._DARK_START_TIMEOUT_S = 5.0
    tap = _DarkTap()
    tap.progress = 0.0
    worker._device = {"model": "Dwarf 3"}
    worker._tap = tap
    elapsed: list[tuple[int, int]] = []
    real_emit = worker.emit

    def snapshot() -> dict[str, object]:
        return {
            "dark_state": "idle",
            "exposure_progress_at": tap.progress,
            "exposure_elapsed_s": 0,
        }

    def emit(payload: dict[str, object]) -> None:
        if payload.get("event") == "dark_prompt":
            elapsed.append((int(payload.get("done") or 0), int(payload.get("elapsed_s") or 0)))

    tap.snapshot = snapshot
    worker.emit = emit

    def send(_message, _command, _module, timeout=None):
        def tick() -> None:
            time.sleep(0.05)
            tap.progress = time.monotonic()

        threading.Thread(target=tick, daemon=True).start()
        return True

    settings = {
        "gain_ok": True,
        "exposure_ok": True,
        "exp_index": 1,
        "gain": 80,
        "bin_index": 0,
        "gain_index": 24,
        "exposure": "2",
        "wide": True,
        "model": "Dwarf 3",
    }
    worker.send_without_response = send
    try:
        result = worker._take_dark_frames("Stack", True, settings, 1)
    finally:
        worker.emit = real_emit
        worker.DARK_FRAME_COUNT, worker._DARK_FRAME_QUIET_S, worker._DARK_START_TIMEOUT_S = saved
        _restore(previous)
    _assert(result == "", result)
    running = [seconds for done, seconds in elapsed if done >= 1]
    _assert(running and min(running) >= 1 and max(running) == 2, elapsed)


def test_missing_reply_does_not_drop_the_prompt_code() -> None:
    """A silent dark command must not replace the warning code with None.

    Progress updates call int(code). response_after returns None until the
    telescope answers, and that used to crash the session and leave Cancel dead.
    """
    previous = _snapshot()
    saved = (
        worker.DARK_FRAME_COUNT,
        worker._DARK_FRAME_QUIET_S,
        worker._DARK_REFUSAL_GRACE_S,
        worker._DARK_START_TIMEOUT_S,
    )
    worker.DARK_FRAME_COUNT = 1
    worker._DARK_FRAME_QUIET_S = 0.05
    worker._DARK_REFUSAL_GRACE_S = 0.05
    worker._DARK_START_TIMEOUT_S = 2.0
    tap = _DarkTap()
    tap.progress = 0.0
    worker._device = {"model": "Dwarf 3"}
    worker._tap = tap
    kinds: list[str] = []
    real_emit = worker.emit

    def snapshot() -> dict[str, object]:
        return {"dark_state": "idle", "exposure_progress_at": tap.progress, "exposure_elapsed_s": 0}

    def emit(payload: dict[str, object]) -> None:
        if payload.get("event") == "dark_prompt":
            kinds.append(str(payload.get("kind")))

    tap.snapshot = snapshot
    worker.emit = emit

    def send(_message, _command, _module, timeout=None):
        def tick() -> None:
            time.sleep(0.2)
            tap.progress = time.monotonic()

        threading.Thread(target=tick, daemon=True).start()
        return True

    settings = {
        "gain_ok": True,
        "exposure_ok": True,
        "exp_index": 1,
        "gain": 80,
        "bin_index": 0,
        "gain_index": 24,
        "exposure": "0.05",
        "wide": True,
        "model": "Dwarf 3",
    }
    worker.send_without_response = send
    try:
        result = worker._take_dark_frames(
            "Stack", True, settings, 1, worker.CODE_ASTRO_DARK_NOT_FOUND
        )
    finally:
        worker.emit = real_emit
        (
            worker.DARK_FRAME_COUNT,
            worker._DARK_FRAME_QUIET_S,
            worker._DARK_REFUSAL_GRACE_S,
            worker._DARK_START_TIMEOUT_S,
        ) = saved
        _restore(previous)
    _assert(result == "", result)
    _assert(kinds and all(kind == "missing" for kind in kinds), kinds)


def test_dark_start_timeout_without_progress() -> None:
    previous = _snapshot()
    saved = worker._DARK_START_TIMEOUT_S
    worker._DARK_START_TIMEOUT_S = 0.2
    worker._device = {"model": "Dwarf 3"}
    worker._tap = _DarkTap()
    worker.send_without_response = lambda *_args, **_kwargs: True
    worker._stop_dark_capture = lambda _wide: None
    try:
        result = worker._take_dark_frames(
            "Stack",
            False,
            {"gain_ok": True, "exposure_ok": True, "exp_index": 1, "gain": 50, "gain_index": 15, "bin_index": 0, "exposure": "15"},
            1,
        )
    finally:
        worker._DARK_START_TIMEOUT_S = saved
        _restore(previous)
    _assert(result == "Dark frames did not start", result)


def test_long_exp_progress_is_stamped() -> None:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0)
    tap._notify = notify_pb2
    tap._base = object()
    note = notify_pb2.LongExpPhotoProgress()
    note.total_time = 15
    note.exposured_time = 1
    changes = tap._decode(
        CMD_NOTIFY_LONG_EXP_PROGRESS,
        TYPE_NOTIFICATION,
        note.SerializeToString(),
    )
    _assert(changes.get("exposure_elapsed_s") == 1.0, changes)
    _assert(float(changes.get("exposure_progress_at") or 0) > 0, changes)


def test_wide_dark_state_notify() -> None:
    tap = TelemetryTap(lambda _payload: None, flush_interval=0)
    tap._notify = notify_pb2
    tap._base = object()
    note = notify_pb2.OperationStateNotify()
    note.state = 1
    changes = tap._decode(
        CMD_NOTIFY_STATE_CAPTURE_WIDE_RAW_DARK,
        TYPE_NOTIFICATION,
        note.SerializeToString(),
    )
    _assert(changes.get("dark_state") == "running", changes)


def test_dark_library_rows_delete_and_choices() -> None:
    from dwarf_python_api.proto import base_pb2

    from astro_dwarf.device_telemetry import CMD_ASTRO_DEL_DARK_FRAME_LIST, TelemetryTap

    frame = {
        "exp_index": 12,
        "gain_index": 18,
        "bin_index": 0,
        "exp_name": "30s",
        "gain_name": "60",
        "bin_name": "4k",
        "temperature": 12,
    }
    item = worker.dark_library_media_item("tele", frame)
    _assert(item["id"] == "tele:12:18:0:12", item)
    _assert(item["kind"] == "dark" and item["camera"] == "tele", item)
    _assert("30s" in item["target"] and "60" in item["target"], item)
    _assert("TELE" in item["subtitle"] and "4K" in item["subtitle"] and "12°C" in item["subtitle"], item)
    missing_temp = worker.dark_library_media_item("wide", {**frame, "temperature": None})
    _assert(missing_temp["id"].endswith(":na"), missing_temp["id"])
    _assert(missing_temp["temperature"] is None, missing_temp)

    groups = worker.split_dark_delete_groups([item, missing_temp])
    _assert(len(groups["tele"]) == 1 and len(groups["wide"]) == 1, groups)
    message = worker.build_dark_delete_message(groups["tele"])
    row = message.dark_list[0]
    _assert(row.exp_index == 12 and row.gain_index == 18 and row.bin_index == 0 and row.temp_value == 12, row)
    blank = worker.build_dark_delete_message(groups["wide"])
    _assert(blank.dark_list[0].temp_value == 0, blank.dark_list[0].temp_value)

    tele = worker.dark_capture_choices("3", False)
    gain_60 = next(entry for entry in tele["gains"] if entry["name"] == "60")
    _assert(gain_60["index"] == 18, gain_60)
    gain_names = [entry["name"] for entry in tele["gains"]]
    _assert("60" in gain_names and "0" not in gain_names and "10" not in gain_names, gain_names)
    _assert(all(worker.dark_gain_allowed(name, wide=False) for name in gain_names), gain_names)
    _assert(any(entry["name"] == "30" for entry in tele["exposures"]), "30s exposure")
    _assert([entry["index"] for entry in tele["bins"]] == [0, 1], tele["bins"])
    wide = worker.dark_capture_choices("3", True)
    wide_names = [entry["name"] for entry in wide["gains"]]
    _assert("0" in wide_names or "2" in wide_names or "10" in wide_names, wide_names)
    _assert(wide["bins"] == [], wide["bins"])

    saved = worker._query_dark_library

    def query(wide_lens: bool) -> list[dict[str, object]] | None:
        if wide_lens:
            return [{
                "exp_index": 1, "gain_index": 2, "bin_index": 0,
                "exp_name": "15s", "gain_name": "60", "bin_name": "4k", "temperature": 10,
            }]
        return [
            {
                "exp_index": 4, "gain_index": 5, "bin_index": 1,
                "exp_name": "60s", "gain_name": "80", "bin_name": "2k", "temperature": 9,
            },
            {
                "exp_index": 3, "gain_index": 4, "bin_index": 0,
                "exp_name": "30s", "gain_name": "60", "bin_name": "4k", "temperature": 11,
            },
        ]

    worker._query_dark_library = query
    try:
        listed = worker.dark_library_list(True)
    finally:
        worker._query_dark_library = saved
    names = [entry["exp_name"] for entry in listed["frames"]]
    _assert(names == ["30s", "60s", "15s"], names)
    _assert([entry["camera"] for entry in listed["frames"]] == ["tele", "tele", "wide"], listed["frames"])
    worker._query_dark_library = lambda _wide: None
    try:
        missing = worker.dark_library_list(True)
    finally:
        worker._query_dark_library = saved
    _assert(missing["ok"] is False and missing["frames"] == [], missing)

    events: list[dict[str, object]] = []
    tap = TelemetryTap(lambda payload: events.append(payload), flush_interval=0)
    tap._base = base_pb2
    reply = base_pb2.ComResponse()
    reply.code = 0
    before = time.monotonic()
    tap.on_packet(CMD_ASTRO_DEL_DARK_FRAME_LIST, 1, reply.SerializeToString())
    _assert(tap.response_after(CMD_ASTRO_DEL_DARK_FRAME_LIST, before) == 0, "delete reply")
    _assert(events == [], "a delete reply is not a telemetry change")


def test_library_capture_settings_use_the_table_index() -> None:
    previous = _snapshot()
    worker._device = {"model": "Dwarf 3"}
    worker._tap = _DarkTap()
    try:
        settings = worker.dark_library_capture_settings("tele", "30s", 60, 0)
        _assert(settings["gain_index"] == 18, settings)
        _assert(settings["exp_index"] is not None, settings)
        _assert(settings["bin_index"] == 0, settings)
        _assert(settings["library"] is True, settings)
        _assert(settings["gain_ok"] and settings["exposure_ok"], settings)
        _assert("this stack" not in str(settings["steps"]), settings["steps"])
        _assert("ND filter" in str(settings["steps"]), settings["steps"])
        blocked = worker.dark_library_capture_settings("tele", "30s", 10, 0)
        _assert(not blocked["gain_ok"], blocked)
        _assert("40" in str(blocked["block_reason"]), blocked["block_reason"])
        wide = worker.dark_library_capture_settings("wide", "15s", 10, 0)
        _assert(wide["gain_ok"] and wide["bin_index"] == 1, wide)
        worker._device = {"model": "Dwarf Mini"}
        mini = worker.dark_library_capture_settings("wide", "15s", 60, 0)
        _assert(not mini["gain_ok"] and "wide" in str(mini["block_reason"]).lower(), mini)
        _assert("this stack" in worker.dark_frame_steps("Dwarf 3"), "stack copy stays")
    finally:
        _restore(previous)


def _gain60_library() -> list[dict[str, object]]:
    return [{
        "exp_index": worker.dark_exposure_index("30", "3", False),
        "gain_index": 18,
        "gain_name": "60",
        "bin_index": 0,
        "temperature": 12,
    }]


def test_stored_darks_are_not_asked_for_again() -> None:
    previous = _snapshot()
    phases: list[object] = []
    real_emit = worker.emit
    real_query = worker._query_dark_library
    worker._stop.clear()
    worker._begin_dark_prompt_run(True, 60)
    worker._device = {"model": "Dwarf 3", "camera": "tele"}
    worker._tap = _DarkTap()
    worker._stack_exposure_name = "30"
    worker._stack_gain = 60
    worker._stack_bin_index = 0
    worker._query_dark_library = lambda _wide: _gain60_library()

    def emit(payload: dict[str, object]) -> None:
        if payload.get("event") == "dark_prompt":
            phases.append(payload.get("phase"))

    worker.emit = emit
    try:
        outcome = worker._after_dark_warning("Stack", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False)
    finally:
        worker.emit = real_emit
        worker._query_dark_library = real_query
        worker._force_camera_write = False
        _restore(previous)
    _assert(outcome == "stored", outcome)
    _assert(phases == [], phases)


def test_empty_library_still_asks_to_create_darks() -> None:
    previous = _snapshot()
    phases: list[object] = []
    continued: list[str] = []
    real_emit = worker.emit
    real_query = worker._query_dark_library
    worker._stop.clear()
    worker._begin_dark_prompt_run(True, 0.4)
    worker._device = {"model": "Dwarf 3", "camera": "tele"}
    worker._tap = None
    worker._stack_exposure_name = "30"
    worker._stack_gain = 60
    worker._stack_bin_index = 0
    worker._query_dark_library = lambda _wide: []
    worker._continue_shooting = lambda name: continued.append(name) or True

    def emit(payload: dict[str, object]) -> None:
        if payload.get("event") == "dark_prompt":
            phases.append(payload.get("phase"))

    worker.emit = emit
    holder: dict[str, object] = {}

    def run() -> None:
        holder["outcome"] = worker._after_dark_warning(
            "Stack", worker.CODE_ASTRO_DARK_NOT_FOUND, wide=False
        )

    thread = threading.Thread(target=run)
    thread.start()
    try:
        thread.join(3)
        _assert(not thread.is_alive(), "empty library did not open the prompt")
        _assert(holder.get("outcome") == "started", holder)
        _assert(phases[:1] == ["ask"], phases)
        _assert(continued == ["Stack"], continued)
    finally:
        if thread.is_alive():
            worker._stop.set()
            worker.accept_dark_prompt_reply(worker._dark_token, "cancel")
            thread.join(2)
        worker.emit = real_emit
        worker._query_dark_library = real_query
        _restore(previous)


def test_stored_darks_retry_the_start_without_a_prompt() -> None:
    previous = _snapshot()
    saved = (
        worker._query_dark_library,
        worker._sdk_needs_continue,
        worker._clear_sdk_continue,
        worker._mark_capture_started,
        worker.sdk_call,
        worker._api,
    )
    sends: list[str] = []
    calls: list[str] = []
    needs = [True, False]
    worker._stop.clear()
    worker._begin_dark_prompt_run(True, 60)
    worker._device = {"model": "Dwarf 3", "camera": "tele"}
    worker._tap = None
    worker._api = object()
    worker._stack_exposure_name = "30"
    worker._stack_gain = 60
    worker._stack_bin_index = 0
    worker._query_dark_library = lambda _wide: _gain60_library()
    worker._send_request = lambda _operation, _message, _command, _module, label: sends.append(str(label)) or 0
    worker._sdk_needs_continue = lambda: needs.pop(0)
    worker._clear_sdk_continue = lambda: None
    worker._mark_capture_started = lambda: None
    worker.sdk_call = lambda operation, *_args: calls.append(operation) or True
    try:
        worker._start_capture("Stack", "astro", [1])
    finally:
        (
            worker._query_dark_library,
            worker._sdk_needs_continue,
            worker._clear_sdk_continue,
            worker._mark_capture_started,
            worker.sdk_call,
            worker._api,
        ) = saved
        worker._force_camera_write = False
        _restore(previous)
    _assert(sends == ["Stack", "Stack"], sends)
    _assert(calls == ["set_exposure", "set_gain", "set_binning"], calls)
    _assert(needs == [], needs)


def test_stored_darks_sdk_continue_cleared_on_retry() -> None:
    """_clear_sdk_continue is called by _refuse_stored_darks so the retry does not re-trigger the dark check.

    This is the live bug: the SDK sets needsContinueShooting=True and never clears it on its own.
    Without the _clear_sdk_continue call in _refuse_stored_darks, _sdk_needs_continue() returns True
    on the second attempt too, the stored-dark path fires again, and the session fails with
    'capture check refused them' even though the dark library is a real match.
    """
    previous = _snapshot()
    saved = (
        worker._query_dark_library,
        worker._sdk_needs_continue,
        worker._clear_sdk_continue,
        worker._mark_capture_started,
        worker.sdk_call,
        worker._api,
    )
    sends: list[str] = []
    calls: list[str] = []
    cleared = [False]
    worker._stop.clear()
    worker._begin_dark_prompt_run(True, 60)
    worker._device = {"model": "Dwarf 3", "camera": "tele"}
    worker._tap = None
    worker._api = object()
    worker._stack_exposure_name = "30"
    worker._stack_gain = 60
    worker._stack_bin_index = 0
    worker._query_dark_library = lambda _wide: _gain60_library()
    worker._send_request = lambda _operation, _message, _command, _module, label: sends.append(str(label)) or 0
    # Simulate a stuck needsContinueShooting flag: True until _clear_sdk_continue fires.
    worker._sdk_needs_continue = lambda: not cleared[0]
    worker._clear_sdk_continue = lambda: cleared.__setitem__(0, True)
    worker._mark_capture_started = lambda: None
    worker.sdk_call = lambda operation, *_args: calls.append(operation) or True
    try:
        worker._start_capture("Stack", "astro", [1])
    finally:
        (
            worker._query_dark_library,
            worker._sdk_needs_continue,
            worker._clear_sdk_continue,
            worker._mark_capture_started,
            worker.sdk_call,
            worker._api,
        ) = saved
        worker._force_camera_write = False
        _restore(previous)
    _assert(cleared == [True], f"_clear_sdk_continue was not called: {cleared}")
    _assert(sends == ["Stack", "Stack"], sends)
    _assert(calls == ["set_exposure", "set_gain", "set_binning"], calls)


def test_second_refusal_does_not_ask_to_create_stored_darks() -> None:
    previous = _snapshot()
    saved = (
        worker._query_dark_library,
        worker._sdk_needs_continue,
        worker._clear_sdk_continue,
        worker._mark_capture_started,
        worker.sdk_call,
        worker._api,
    )
    phases: list[object] = []
    real_emit = worker.emit
    sends: list[str] = []
    worker._stop.clear()
    worker._begin_dark_prompt_run(True, 60)
    worker._device = {"model": "Dwarf 3", "camera": "tele"}
    worker._tap = None
    worker._api = object()
    worker._stack_exposure_name = "30"
    worker._stack_gain = 60
    worker._stack_bin_index = 0
    worker._query_dark_library = lambda _wide: _gain60_library()
    worker._send_request = lambda _operation, _message, _command, _module, label: sends.append(str(label)) or 0
    worker._sdk_needs_continue = lambda: True
    worker._clear_sdk_continue = lambda: None
    worker._mark_capture_started = lambda: None
    worker.sdk_call = lambda _operation, *_args: True
    worker.emit = lambda payload: phases.append(payload.get("phase")) if isinstance(payload, dict) and payload.get("event") == "dark_prompt" else None
    refused = ""
    try:
        try:
            worker._start_capture("Stack", "astro", [1])
        except RuntimeError as exc:
            refused = str(exc)
    finally:
        worker.emit = real_emit
        (
            worker._query_dark_library,
            worker._sdk_needs_continue,
            worker._clear_sdk_continue,
            worker._mark_capture_started,
            worker.sdk_call,
            worker._api,
        ) = saved
        worker._force_camera_write = False
        _restore(previous)
    _assert("already on the telescope" in refused, refused)
    _assert(sends == ["Stack", "Stack"], sends)
    _assert(phases == [], phases)


if __name__ == "__main__":
    test_model_steps_follow_each_manual()
    test_dark_library_rows_delete_and_choices()
    test_library_capture_settings_use_the_table_index()
    test_tele_gain_limits()
    test_unprompted_run_continues_immediately()
    test_schedule_dark_prompt_asks_once_then_skips()
    test_prompt_waits_to_continue()
    test_prompt_timeout_continues_and_skips_the_next_ask()
    test_stored_darks_are_not_asked_for_again()
    test_empty_library_still_asks_to_create_darks()
    test_stored_darks_retry_the_start_without_a_prompt()
    test_stored_darks_sdk_continue_cleared_on_retry()
    test_second_refusal_does_not_ask_to_create_stored_darks()
    test_manual_alignment_ignores_the_schedule_countdown()
    test_prompt_cancel_does_not_continue()
    test_take_darks_builds_the_firmware_request()
    test_device_not_activated_does_not_discard_finished_darks()
    test_long_exposure_progress_counts_as_dark_frames()
    test_dark_frame_clock_ticks_between_notifications()
    test_missing_reply_does_not_drop_the_prompt_code()
    test_dark_start_timeout_without_progress()
    test_long_exp_progress_is_stamped()
    test_library_match_uses_exposure_gain_and_temperature()
    test_cancel_does_not_block_the_next_manual_command()
    test_stop_dark_capture_sends_wide_and_plain_stops()
    test_remembered_continue_skips_the_next_pane()
    test_wide_dark_state_notify()
    print("ok")
