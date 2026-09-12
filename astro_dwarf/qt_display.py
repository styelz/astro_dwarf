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
) -> bool:
    """True when Qt would abort without a software scene graph.

    Frozen Linux installers ship Ubuntu Qt pieces that often cannot create a
    GLX context on NVIDIA, newer Mesa, or XWayland. Qt then calls qFatal
    ("Could not initialize GLX") and abort()s. WSL has the same gap. Set
    ASTRO_DWARF_QT_SYSTEM=1 to use the host OpenGL stack instead.
    """
    os_name = os.name if os_name is None else os_name
    platform = sys.platform if platform is None else platform
    if os_name == "nt":
        return False
    if system_qt is None:
        system_qt = os.environ.get("ASTRO_DWARF_QT_SYSTEM") == "1"
    if system_qt:
        return False
    if wsl is None:
        wsl = running_in_wsl()
    if frozen is None:
        frozen = running_frozen()
    if wsl:
        return True
    return bool(frozen) and platform.startswith("linux")


def apply_software_qt_env() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QSG_RHI_BACKEND", "software")


def configure_qt_display() -> None:
    """Skip GLX/EGL when bundled Qt cannot talk to the host GPU driver."""
    if needs_software_qt():
        apply_software_qt_env()
