from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.qt_display import (
    LINUX_WEBENGINE_FLAGS,
    _ensure_utf8_locale,
    apply_software_qt_env,
    cxx_runtime_preload,
    fall_back_to_software_qt,
    gl_platform_choice,
    is_noisy_webengine_message,
    needs_software_qt,
    newer_symbol_version,
    parse_ldconfig_path,
    should_probe_host_gl,
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
    _assert("disable-gpu-compositing" in LINUX_WEBENGINE_FLAGS, LINUX_WEBENGINE_FLAGS)
    _assert("swiftshader" in LINUX_WEBENGINE_FLAGS, LINUX_WEBENGINE_FLAGS)


def test_aborted_console_is_noisy() -> None:
    _assert(is_noisy_webengine_message("js: Aborted(undefined)"), "abort should be filtered")
    _assert(is_noisy_webengine_message("Compositor returned null texture"), "dma-buf spam")
    _assert(not is_noisy_webengine_message("js: mosaic ready"), "normal js should pass")


def test_newer_glibcxx_outranks_shorter_patch() -> None:
    older = b"\0GLIBCXX_3.4.9\0GLIBCXX_3.4.20\0"
    newer = b"\0GLIBCXX_3.4.30\0GLIBCXX_3.4.33\0"
    _assert(newer_symbol_version(newer, older, "GLIBCXX_"), "3.4.33 is newer than 3.4.20")
    _assert(not newer_symbol_version(older, newer, "GLIBCXX_"), "older host must stay on the bundle")
    _assert(not newer_symbol_version(newer, newer, "GLIBCXX_"), "equal runtimes must not preload")
    _assert(not newer_symbol_version(b"", newer, "GLIBCXX_"), "missing symbols are not newer")


def test_preload_uses_host_pair_only_when_newer() -> None:
    older = b"GLIBCXX_3.4.30"
    newer = b"GLIBCXX_3.4.33"
    paths = cxx_runtime_preload(
        bundled_libstd=older,
        host_libstd=newer,
        host_libstd_path="/usr/lib/libstdc++.so.6",
        host_libgcc_path="/usr/lib/libgcc_s.so.1",
    )
    _assert(paths == ["/usr/lib/libstdc++.so.6", "/usr/lib/libgcc_s.so.1"], str(paths))
    _assert(
        cxx_runtime_preload(
            bundled_libstd=newer,
            host_libstd=older,
            host_libstd_path="/usr/lib/libstdc++.so.6",
            host_libgcc_path="/usr/lib/libgcc_s.so.1",
        )
        == [],
        "older host must not be preloaded",
    )
    _assert(
        cxx_runtime_preload(
            bundled_libstd=older,
            host_libstd=newer,
            host_libstd_path="/usr/lib/libstdc++.so.6",
            host_libgcc_path=None,
        )
        == [],
        "libstdc++ without its libgcc must not be mixed",
    )
    _assert(
        cxx_runtime_preload(
            bundled_libstd=older,
            host_libstd=newer,
            host_libstd_path="/usr/lib/libstdc++.so.6",
            host_libgcc_path="/usr/lib/libgcc_s.so.1",
            same_file=True,
        )
        == [],
        "the bundle and the host path are the same file",
    )


def test_ldconfig_prefers_x86_64() -> None:
    text = "\n".join(
        (
            "libstdc++.so.6 (libc6) => /usr/lib32/libstdc++.so.6",
            "libstdc++.so.6 (libc6,x86-64) => /usr/lib/libstdc++.so.6",
            "libgcc_s.so.1 (libc6,x86-64) => /usr/lib/libgcc_s.so.1",
        )
    )
    _assert(
        parse_ldconfig_path(text, "libstdc++.so.6") == "/usr/lib/libstdc++.so.6",
        parse_ldconfig_path(text, "libstdc++.so.6") or "",
    )
    i386_only = "libstdc++.so.6 (libc6,i386) => /usr/lib32/libstdc++.so.6"
    _assert(parse_ldconfig_path(i386_only, "libstdc++.so.6") is None, "i386 libstdc++ is the wrong ABI")


def _probe(**overrides: object) -> bool:
    values = {
        "platform": "linux",
        "argv": ["AstroDwarf", "--child"],
        "env": {},
    }
    values.update(overrides)
    return should_probe_host_gl(**values)  # type: ignore[arg-type]


def test_gl_probe_runs_for_the_qt_quick_process() -> None:
    _assert(_probe(), "the splash child opens Qt Quick")
    _assert(not _probe(argv=["AstroDwarf"]), "the splash parent only paints widgets")
    _assert(not _probe(argv=["AstroDwarf", "--worker"]), "the worker has no scene graph")
    _assert(not _probe(env={"ASTRO_DWARF_QT_SOFTWARE": "1"}), "software mode is already selected")
    _assert(not _probe(env={"ASTRO_DWARF_QT_SYSTEM": "1"}), "system override skips the probe")
    _assert(not _probe(env={"ASTRO_DWARF_GL_PROBED": "1"}), "probe once")
    _assert(_probe(argv=["AstroDwarf"], env={"ASTRO_DWARF_TEST_EXIT_MS": "3000"}), "smoke test opens Qt Quick")
    _assert(not _probe(platform="win32"), "Windows does not take the Linux probe")


def _restore_env(keys: tuple[str, ...]) -> dict[str, str | None]:
    import os

    return {key: os.environ.get(key) for key in keys}


def _put_env(saved: dict[str, str | None]) -> None:
    import os

    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_software_qt_overrides_opengl_request() -> None:
    import os

    keys = (
        "QT_QPA_PLATFORM",
        "QT_XCB_GL_INTEGRATION",
        "QT_QUICK_BACKEND",
        "QSG_RHI_BACKEND",
        "QTWEBENGINE_CHROMIUM_FLAGS",
    )
    saved = _restore_env(keys)
    os.environ["QT_QUICK_BACKEND"] = "opengl"
    os.environ["QT_XCB_GL_INTEGRATION"] = "xcb_glx"
    os.environ["QSG_RHI_BACKEND"] = "opengl"
    try:
        apply_software_qt_env()
        _assert(os.environ.get("QT_QUICK_BACKEND") == "software", os.environ.get("QT_QUICK_BACKEND", ""))
        _assert(os.environ.get("QT_XCB_GL_INTEGRATION") == "none", os.environ.get("QT_XCB_GL_INTEGRATION", ""))
        _assert("QSG_RHI_BACKEND" not in os.environ, "RHI backend must not force OpenGL")
    finally:
        _put_env(saved)


def test_software_fallback_leaves_wayland_for_xcb() -> None:
    import os

    keys = ("QT_QPA_PLATFORM", "ASTRO_DWARF_QT_SOFTWARE")
    saved = _restore_env(keys)
    os.environ["QT_QPA_PLATFORM"] = "wayland"
    try:
        fall_back_to_software_qt()
        _assert(os.environ.get("QT_QPA_PLATFORM") == "xcb", os.environ.get("QT_QPA_PLATFORM", ""))
        _assert(os.environ.get("ASTRO_DWARF_QT_SOFTWARE") == "1", "fallback has to stick for the child")
    finally:
        _put_env(saved)


def test_gl_platform_choice_keeps_a_working_driver() -> None:
    _assert(gl_platform_choice(True, False, "wayland") == "keep", "working Wayland stays")
    _assert(gl_platform_choice(False, True, "wayland") == "xcb", "X11 is the fallback when Wayland GL fails")
    _assert(gl_platform_choice(False, True, "") == "xcb", "unset platform may retry on xcb")
    _assert(gl_platform_choice(False, False, "wayland") is None, "neither platform means software rendering")
    _assert(gl_platform_choice(False, True, "offscreen") is None, "an explicit offscreen session is not moved to xcb")


def test_software_fallback_keeps_offscreen() -> None:
    import os

    keys = ("QT_QPA_PLATFORM", "ASTRO_DWARF_QT_SOFTWARE")
    saved = _restore_env(keys)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        fall_back_to_software_qt()
        _assert(os.environ.get("QT_QPA_PLATFORM") == "offscreen", os.environ.get("QT_QPA_PLATFORM", ""))
    finally:
        _put_env(saved)


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
    test_newer_glibcxx_outranks_shorter_patch()
    test_preload_uses_host_pair_only_when_newer()
    test_ldconfig_prefers_x86_64()
    test_gl_probe_runs_for_the_qt_quick_process()
    test_software_qt_overrides_opengl_request()
    test_software_fallback_leaves_wayland_for_xcb()
    test_gl_platform_choice_keeps_a_working_driver()
    test_software_fallback_keeps_offscreen()
    test_bundled_fontconfig_is_shipped()
    print("qt_display tests ok")
