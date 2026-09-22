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

    def snapshot(self) -> dict[str, object]:
        return {"dark_state": self.phase, "cmos_tele_c": 12}

    def response_after(self, _command: int, _since: float) -> None:
        return None


def _restore(previous: dict[str, object]) -> None:
    worker._tap = previous["tap"]
    worker._device = previous["device"]
    worker._send_request = previous["send"]
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
        "continue": worker._continue_shooting,
    }


def test_model_steps_follow_each_manual() -> None:
    dwarf3 = worker.dark_frame_steps("Dwarf 3")
    mini = worker.dark_frame_steps("Dwarf Mini")
    dwarf2 = worker.dark_frame_steps("Dwarf II")
    _assert("ND filter" in dwarf3 and "retract the lens cylinder" in dwarf3, dwarf3)
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

    def send(_operation, message, command, _module, _label):
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
        return 0

    worker._send_request = send
    try:
        tele = worker._take_dark_frames("Stack", False, worker._dark_capture_settings(False), 1)
        worker._tap = _DarkTap()
        wide = worker._take_dark_frames("Stack", True, worker._dark_capture_settings(True), 1)
    finally:
        _restore(previous)
    _assert(tele == "", tele)
    _assert(wide == "", wide)
    _assert(sent[0] == (11021, tele_index, 60, 0, 10), sent[0])
    _assert(sent[1] == (11025, wide_index, 60, 0, 10), sent[1])


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


if __name__ == "__main__":
    test_model_steps_follow_each_manual()
    test_tele_gain_limits()
    test_unprompted_run_continues_immediately()
    test_prompt_waits_to_continue()
    test_prompt_cancel_does_not_continue()
    test_take_darks_builds_the_firmware_request()
    test_remembered_continue_skips_the_next_pane()
    test_wide_dark_state_notify()
    print("ok")
