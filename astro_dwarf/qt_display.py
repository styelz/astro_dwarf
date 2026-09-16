"""Display environment that must exist before PySide/Qt loads."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def running_in_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    for candidate in (Path("/proc/sys/kernel/osrelease"), Path("/proc/version")):
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if "microsoft" in text or "wsl" in text:
            return True
    return False


def running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def needs_software_qt(
    *,
    os_name: str | None = None,
    platform: str | None = None,
    frozen: bool | None = None,
    wsl: bool | None = None,
    system_qt: bool | None = None,
    software_qt: bool | None = None,
) -> bool:
    """True when Qt Quick should use the software scene graph.

    Stellarium Web needs a real GL or EGL context. Never disable xcb GL
    integration for that reason. Frozen Linux builds use the host libGL, so
    they follow the GPU path unless WSL or ASTRO_DWARF_QT_SOFTWARE=1.
    ASTRO_DWARF_QT_SYSTEM=1 keeps host OpenGL even on WSL.
    """
    os_name = os.name if os_name is None else os_name
    platform = sys.platform if platform is None else platform
    if os_name == "nt":
        return False
    if not platform.startswith("linux"):
        return False
    if system_qt is None:
        system_qt = os.environ.get("ASTRO_DWARF_QT_SYSTEM") == "1"
    if system_qt:
        return False
    if software_qt is None:
        software_qt = os.environ.get("ASTRO_DWARF_QT_SOFTWARE") == "1"
    if software_qt:
        return True
    if wsl is None:
        wsl = running_in_wsl()
    return bool(wsl)


# Stellarium Web is WebGL. --disable-gpu and QT_XCB_GL_INTEGRATION=none leave a
# black atlas (createProgram on a missing GL context). SwiftShader is only a
# GPU-less fallback; Qt still needs GLX or EGL enabled to host WebEngine.
SOFTWARE_WEBENGINE_FLAGS = (
    "--enable-webgl --ignore-gpu-blocklist --disable-gpu-sandbox "
    "--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader"
)
LINUX_WEBENGINE_FLAGS = (
    "--enable-webgl --ignore-gpu-blocklist --disable-gpu-sandbox"
)


def _chromium_flag_tokens(raw: str | None) -> list[str]:
    return [part for part in str(raw or "").split() if part]


def _has_disable_gpu(raw: str | None) -> bool:
    return "--disable-gpu" in _chromium_flag_tokens(raw)


def _strip_readline_library_path() -> None:
    """Keep system /bin/sh from loading Qt's older libreadline.

    Fedora/Arch bash looks up rl_trim_arg_from_keyseq. Qt's copy of
    libreadline is older, so a poisoned LD_LIBRARY_PATH prints
    'undefined symbol: rl_trim_arg_from_keyseq' and child shells fail.
    """
    raw = os.environ.get("LD_LIBRARY_PATH")
    if not raw:
        return
    kept: list[str] = []
    for part in raw.split(":"):
        if not part:
            continue
        folder = Path(part)
        try:
            names = [path.name for path in folder.iterdir()] if folder.is_dir() else []
        except OSError:
            kept.append(part)
            continue
        has_readline = any(name.startswith("libreadline.so") for name in names)
        has_qt = any(name.startswith("libQt") for name in names)
        if has_readline and not has_qt:
            continue
        kept.append(part)
    if kept:
        os.environ["LD_LIBRARY_PATH"] = ":".join(kept)
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)


def _clear_blocked_gl_env(*, drop_software_quick: bool) -> None:
    """Undo flags that prevent WebEngine from creating a GL context.

    QSG_RHI_BACKEND=software is not a valid Qt RHI backend. Qt logs
    'Unknown key software' and falls back to OpenGL, which then fails when
    QT_XCB_GL_INTEGRATION=none has disabled both GLX and EGL.
    """
    if os.environ.get("QT_XCB_GL_INTEGRATION") == "none":
        os.environ.pop("QT_XCB_GL_INTEGRATION", None)
    if os.environ.get("QSG_RHI_BACKEND", "").strip().lower() == "software":
        os.environ.pop("QSG_RHI_BACKEND", None)
    if drop_software_quick and os.environ.get("QT_QUICK_BACKEND") == "software":
        os.environ.pop("QT_QUICK_BACKEND", None)


def apply_software_qt_env() -> None:
    _clear_blocked_gl_env(drop_software_quick=False)
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = SOFTWARE_WEBENGINE_FLAGS


def configure_qt_display() -> None:
    """Keep Linux WebEngine able to create GL/EGL for Stellarium Web."""
    if sys.platform.startswith("linux"):
        _strip_readline_library_path()
        os.environ.setdefault("NO_AT_BRIDGE", "1")
        os.environ.setdefault("GTK_MODULES", "")
        os.environ.setdefault("GTK3_MODULES", "")
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        software = needs_software_qt()
        _clear_blocked_gl_env(drop_software_quick=not software)
        if software:
            apply_software_qt_env()
        else:
            flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS")
            if not flags or _has_disable_gpu(flags):
                os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = LINUX_WEBENGINE_FLAGS
            elif "--enable-webgl" not in _chromium_flag_tokens(flags):
                os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --enable-webgl"
