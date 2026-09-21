from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.device_telemetry import (
    PARAM_ID_ASTRO_EXPOSURE,
    PARAM_ID_PHOTO_TELE_EXPOSURE,
    normalize_client_status,
)
from astro_dwarf.device_worker import camera_param_unchanged
from astro_dwarf.domain import (
    ControlSettings,
    control_settings_from_telemetry,
    firmware_exposure_name,
)
from astro_dwarf.telemetry_view import apply_mode_exposure_fields, camera_params_to_telemetry


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_firmware_exposure_name_keeps_dso_seconds() -> None:
    _assert(firmware_exposure_name("15") == "15", firmware_exposure_name("15"))
    _assert(firmware_exposure_name("15.0") == "15", firmware_exposure_name("15.0"))
    _assert(firmware_exposure_name(15.0) == "15", firmware_exposure_name(15.0))
    _assert(firmware_exposure_name("1/30") == "1/30", firmware_exposure_name("1/30"))


def test_photo_notify_does_not_clobber_dso_exposure() -> None:
    saved = ControlSettings(shooting_mode=2, exposure="15", wide_exposure="10")
    updated = control_settings_from_telemetry(
        {
            "shooting_mode": 1,
            "photo_exposure_text": "1/30",
            "photo_wide_exposure_text": "1/30",
            "exposure_text": "1/30",
            "wide_exposure_text": "1/30",
        },
        saved,
        persist_mode=False,
    )
    _assert(updated.exposure == "15", updated)
    _assert(updated.wide_exposure == "10", updated)
    _assert(updated.photo_exposure == "1/30", updated)
    _assert(updated.photo_wide_exposure == "1/30", updated)
    _assert(updated.shooting_mode == 2, updated.shooting_mode)


def test_dso_notify_updates_astro_slot_in_photo_mode() -> None:
    saved = ControlSettings(shooting_mode=2, exposure="8", photo_exposure="1/30")
    updated = control_settings_from_telemetry(
        {"shooting_mode": 1, "astro_exposure_text": "15", "photo_exposure_text": "1/60"},
        saved,
    )
    _assert(updated.exposure == "15", updated)
    _assert(updated.photo_exposure == "1/60", updated)


def test_hud_uses_astro_exposure_in_dso_mode() -> None:
    aliases = apply_mode_exposure_fields(
        {
            "shooting_mode": 2,
            "photo_exposure_text": "1/30",
            "astro_exposure_text": "15",
            "photo_wide_exposure_text": "1/60",
            "astro_wide_exposure_text": "10",
        }
    )
    _assert(aliases.get("exposure_text") == "15", aliases)
    _assert(aliases.get("wide_exposure_text") == "10", aliases)


def test_hud_uses_photo_exposure_in_photo_mode() -> None:
    aliases = apply_mode_exposure_fields(
        {
            "shooting_mode": 1,
            "photo_exposure_text": "1/30",
            "astro_exposure_text": "15",
        }
    )
    _assert(aliases.get("exposure_text") == "1/30", aliases)


def test_sdk_cache_keeps_photo_and_astro_separate() -> None:
    changes = normalize_client_status(
        {
            "CameraParamsDwarf": {
                str(PARAM_ID_PHOTO_TELE_EXPOSURE): {"value": 75, "mode": 1},
                str(PARAM_ID_ASTRO_EXPOSURE): {"value": 156, "mode": 1},
            }
        },
        "3",
    )
    _assert(changes.get("photo_exposure_text") == "1/30", changes)
    _assert(changes.get("astro_exposure_text") == "15", changes)
    _assert("exposure_text" not in changes, changes)


def test_photo_http_params_do_not_write_hud_exposure() -> None:
    changes = camera_params_to_telemetry(
        {
            "mode_id": 1,
            "cameras": {0: {"exposure": {"name": "1/30"}, "gain": {"value": 80}}},
        }
    )
    _assert(changes.get("photo_exposure_text") == "1/30", changes)
    _assert("exposure_text" not in changes, changes)
    _assert(changes.get("photo_gain") == 80, changes)
    _assert("gain" not in changes, changes)


def test_astro_http_params_still_fill_hud_exposure() -> None:
    changes = camera_params_to_telemetry(
        {
            "mode_id": 2,
            "cameras": {0: {"exposure": {"name": "15"}, "gain": {"value": 60}}},
        }
    )
    _assert(changes.get("astro_exposure_text") == "15", changes)
    _assert(changes.get("exposure_text") == "15", changes)


def test_worker_skips_matching_astro_exposure() -> None:
    snap = {"astro_exposure_text": "15", "exposure_text": "1/30"}
    _assert(
        camera_param_unchanged("set_exposure", ["15", "3", "tele"], snap, {}),
        "astro set must ignore a PHOTO HUD leftover",
    )
    _assert(
        not camera_param_unchanged("set_exposure", ["15", "3", "tele"], {"exposure_text": "1/30"}, {}),
        "photo leftover alone must not skip a DSO set",
    )


if __name__ == "__main__":
    test_firmware_exposure_name_keeps_dso_seconds()
    test_photo_notify_does_not_clobber_dso_exposure()
    test_dso_notify_updates_astro_slot_in_photo_mode()
    test_hud_uses_astro_exposure_in_dso_mode()
    test_hud_uses_photo_exposure_in_photo_mode()
    test_sdk_cache_keeps_photo_and_astro_separate()
    test_photo_http_params_do_not_write_hud_exposure()
    test_astro_http_params_still_fill_hud_exposure()
    test_worker_skips_matching_astro_exposure()
    print("ok")
