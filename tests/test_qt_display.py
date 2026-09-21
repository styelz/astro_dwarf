from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.qt_display import (
    LINUX_WEBENGINE_FLAGS,
    _ensure_utf8_locale,
    is_noisy_webengine_message,
    needs_software_qt,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _linux(**overrides: object) -> bool:
    values = {
        "os_name": "posix",
        "platform": "linux",
        "frozen": True,
        "wsl": False,
        "hypervisor": False,
        "has_drm": True,
        "system_qt": False,
        "software_qt": False,
    }
    values.update(overrides)
    return needs_software_qt(**values)


def test_frozen_native_linux_keeps_gpu() -> None:
    _assert(not _linux(), "native NVIDIA/AMD installer must not force software Qt")


def test_wsl_uses_software_even_with_drm() -> None:
    _assert(_linux(wsl=True, has_drm=True), "WSL still needs the GLX fallback")


def test_hyperv_uses_software() -> None:
    _assert(_linux(hypervisor=True, has_drm=True), "Hyper-V guests use software Qt")


def test_no_drm_uses_software() -> None:
    _assert(_linux(has_drm=False), "no render node means no host OpenGL")


def test_system_qt_keeps_gpu_in_wsl() -> None:
    _assert(not _linux(wsl=True, system_qt=True), "ASTRO_DWARF_QT_SYSTEM=1 uses the host GPU")


def test_software_qt_env_forces_fallback() -> None:
    _assert(_linux(software_qt=True, has_drm=True), "ASTRO_DWARF_QT_SOFTWARE=1 forces software Qt")


def test_windows_never_software() -> None:
    _assert(
        not needs_software_qt(os_name="nt", platform="win32", frozen=True, wsl=True),
        "Windows must not take the Linux software-Qt path",
    )


def test_empty_lang_becomes_utf8() -> None:
    import os

    previous = os.environ.get("LANG")
    os.environ.pop("LANG", None)
    try:
        _ensure_utf8_locale()
        _assert(os.environ.get("LANG") == "C.UTF-8", os.environ.get("LANG", ""))
    finally:
        if previous is None:
            os.environ.pop("LANG", None)
        else:
            os.environ["LANG"] = previous


def test_posix_lc_all_becomes_utf8() -> None:
    import os

    previous_lang = os.environ.get("LANG")
    previous_all = os.environ.get("LC_ALL")
    os.environ["LANG"] = "C"
    os.environ["LC_ALL"] = "POSIX"
    try:
        _ensure_utf8_locale()
        _assert(os.environ.get("LANG") == "C.UTF-8", os.environ.get("LANG", ""))
        _assert(os.environ.get("LC_ALL") == "C.UTF-8", os.environ.get("LC_ALL", ""))
    finally:
        if previous_lang is None:
            os.environ.pop("LANG", None)
        else:
            os.environ["LANG"] = previous_lang
        if previous_all is None:
            os.environ.pop("LC_ALL", None)
        else:
            os.environ["LC_ALL"] = previous_all


def test_webengine_flags_avoid_vulkan_fallback() -> None:
    _assert("disable-features=Vulkan" in LINUX_WEBENGINE_FLAGS, LINUX_WEBENGINE_FLAGS)
    _assert("swiftshader" in LINUX_WEBENGINE_FLAGS, LINUX_WEBENGINE_FLAGS)


def test_aborted_console_is_noisy() -> None:
    _assert(is_noisy_webengine_message("js: Aborted(undefined)"), "abort should be filtered")
    _assert(is_noisy_webengine_message("Compositor returned null texture"), "dma-buf spam")
    _assert(not is_noisy_webengine_message("js: mosaic ready"), "normal js should pass")


def test_bundled_fontconfig_is_shipped() -> None:
    from astro_dwarf.qt_fonts import bundled_font_dir

    folder = bundled_font_dir()
    _assert(folder is not None, "fonts directory missing")
    _assert((folder / "fonts.conf").is_file(), "fonts.conf missing")
    _assert(any(path.suffix.lower() == ".ttf" for path in folder.iterdir()), "no bundled TTF")


if __name__ == "__main__":
    test_frozen_native_linux_keeps_gpu()
    test_wsl_uses_software_even_with_drm()
    test_hyperv_uses_software()
    test_no_drm_uses_software()
    test_system_qt_keeps_gpu_in_wsl()
    test_software_qt_env_forces_fallback()
    test_windows_never_software()
    test_empty_lang_becomes_utf8()
    test_posix_lc_all_becomes_utf8()
    test_webengine_flags_avoid_vulkan_fallback()
    test_aborted_console_is_noisy()
    test_bundled_fontconfig_is_shipped()
    print("qt_display tests ok")
