"""Display environment that must exist before PySide/Qt loads."""

from __future__ import annotations

import os
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


def configure_qt_display() -> None:
    """Use X11 + software Qt Quick on WSL, where bundled Qt has no working GLX/EGL."""
    if os.name == "nt" or os.environ.get("ASTRO_DWARF_QT_SYSTEM") == "1":
        return
    if not running_in_wsl():
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("QT_XCB_GL_INTEGRATION", "none")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
