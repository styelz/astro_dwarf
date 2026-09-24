from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_worker import camera_param_unchanged, dispatch
from astro_dwarf.domain import (
    ControlSettings,
    control_settings_from_dict,
    control_settings_from_telemetry,
    firmware_stack_format,
    shooting_mode_camera_steps,
)
from astro_dwarf.telemetry_view import camera_params_to_telemetry


def _assert(condition: bool, message: object) -> None:
    if not condition:
        raise AssertionError(message)


def test_stack_format_maps_legacy_indexes() -> None:
    _assert(firmware_stack_format(0) == 2, firmware_stack_format(0))
    _assert(firmware_stack_format("0") == 2, "saved FITS index")
    _assert(firmware_stack_format("FITS") == 2, "name")
    _assert(firmware_stack_format(2) == 2, firmware_stack_format(2))
    _assert(firmware_stack_format(1) == 3, firmware_stack_format(1))
    _assert(firmware_stack_format("TIFF") == 3, "tiff name")
    _assert(firmware_stack_format(3) == 3, firmware_stack_format(3))
    _assert(firmware_stack_format("") is None, "blank")
    _assert(control_settings_from_dict({"stack_format": 0}).stack_format == "2", "persisted FITS")
    _assert(control_settings_from_dict({"stack_format": "1"}).stack_format == "3", "persisted TIFF")


def test_stack_format_skip_uses_firmware_values() -> None:
    _assert(
        camera_param_unchanged("set_stack_format", [2], {"stack_format": 2}, {}),
        "FITS already set",
    )
    _assert(
        not camera_param_unchanged("set_stack_format", [2], {"stack_format": 3}, {}),
        "TIFF is not FITS",
    )
    _assert(
        camera_param_unchanged("set_stack_format", [0], {"stack_format": 2}, {}),
        "legacy 0 matches firmware FITS",
    )


def test_dso_entry_restores_dso_slots_not_photo() -> None:
    settings = ControlSettings(
        shooting_mode=2,
        exposure="15",
        gain="60",
        wide_exposure="10",
        wide_gain="40",
        photo_exposure="1/30",
        photo_gain="10",
        ir_filter="Astro",
        stack_count="40",
    )
    steps = shooting_mode_camera_steps(settings, 2, include_wide=True)
    _assert(("auto_parameters", "false", "tele") in steps, steps)
    _assert(("exposure", "15", "tele") in steps, steps)
    _assert(("gain", "60", "tele") in steps, steps)
    _assert(("exposure", "10", "wide") in steps, steps)
    _assert(("exposure", "1/30", "tele") not in steps, steps)
    _assert(("ir", "Astro", "tele") in steps, steps)
    _assert(("count", "40", "tele") in steps, steps)


def test_auto_parameters_stays_on_across_modes() -> None:
    settings = ControlSettings(
        shooting_mode=1,
        auto_parameters="true",
        exposure="15",
        gain="60",
        wide_exposure="10",
        wide_gain="40",
        photo_exposure="",
        photo_gain="",
    )
    photo = shooting_mode_camera_steps(settings, 1, include_wide=True)
    dso = shooting_mode_camera_steps(settings, 2, include_wide=True)
    _assert(photo == [("auto_parameters", "true", "tele"), ("auto_parameters", "true", "wide")], photo)
    _assert(dso == [("auto_parameters", "true", "tele"), ("auto_parameters", "true", "wide")], dso)
    _assert(("exposure", "15", "tele") not in dso, dso)


def test_empty_mode_enables_auto_parameters() -> None:
    settings = ControlSettings(shooting_mode=1, exposure="15", gain="60")
    steps = shooting_mode_camera_steps(settings, 1, include_wide=True)
    _assert(("auto_parameters", "true", "tele") in steps, steps)
    _assert(("auto_parameters", "true", "wide") in steps, steps)
    _assert(("exposure", "15", "tele") not in steps, steps)
    _assert(shooting_mode_camera_steps(settings, 1, include_wide=False) == [("auto_parameters", "true", "tele")], "mini")


def test_auto_telemetry_does_not_become_manual() -> None:
    saved = ControlSettings(shooting_mode=2, exposure="15", gain="60", wide_exposure="10")
    updated = control_settings_from_telemetry(
        {
            "shooting_mode": 2,
            "auto_parameters_tele": True,
            "auto_parameters_wide": False,
            "astro_exposure_text": "1",
            "astro_gain": 0,
            "exposure_text": "1",
            "astro_wide_exposure_text": "8",
            "astro_wide_gain": 20,
        },
        saved,
    )
    _assert(updated.exposure == "15", updated.exposure)
    _assert(updated.gain == "60", updated.gain)
    _assert(updated.wide_exposure == "8", updated.wide_exposure)
    _assert(updated.wide_gain == "20", updated.wide_gain)


def test_camera_read_reports_auto_and_does_not_clear_it() -> None:
    import astro_dwarf.device_worker as worker

    changes = camera_params_to_telemetry(
        {
            "mode_id": 2,
            "cameras": {
                0: {"exposure": {"mode": 0, "name": "15"}, "gain": {"mode": 0, "value": 60}},
                1: {"exposure": {"mode": 1, "name": "10"}, "gain": {"mode": 1, "value": 40}},
            },
        }
    )
    _assert(changes.get("auto_parameters_tele") is True, changes)
    _assert("auto_parameters_wide" not in changes, changes)
    explicit = camera_params_to_telemetry(
        {
            "data": {
                "cameraParams": [
                    {"cameraId": 0, "isAuto": False},
                    {"cameraId": 1, "isAuto": True},
                ]
            }
        }
    )
    _assert(explicit.get("auto_parameters_tele") is False, explicit)
    _assert(explicit.get("auto_parameters_wide") is True, explicit)
    cleared: list[str] = []
    original_clear = worker._clear_auto_params
    original_sdk = worker.sdk_call
    worker._clear_auto_params = lambda *args, **kwargs: cleared.append("cleared") or ["tele"]
    worker.sdk_call = lambda *args, **kwargs: {"ok": True}

    try:
        result = dispatch({"command": "read_camera", "args": [2]})
    finally:
        worker._clear_auto_params = original_clear
        worker.sdk_call = original_sdk
    _assert(cleared == [], cleared)
    _assert(isinstance(result, dict) and "auto_params_cleared" not in result, result)


if __name__ == "__main__":
    test_stack_format_maps_legacy_indexes()
    test_stack_format_skip_uses_firmware_values()
    test_dso_entry_restores_dso_slots_not_photo()
    test_auto_parameters_stays_on_across_modes()
    test_empty_mode_enables_auto_parameters()
    test_auto_telemetry_does_not_become_manual()
    test_camera_read_reports_auto_and_does_not_clear_it()
    print("ok")
