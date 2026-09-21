"""Display environment that must exist before PySide/Qt loads."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def running_in_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        text = Path("/proc/sys/kernel/osrelease").read_text(
            encoding="utf-8", errors="ignore"
        ).lower()
    except OSError:
        return False
    return "microsoft" in text or "wsl" in text


def _dmi_text() -> str:
    chunks: list[str] = []
    for candidate in (
        Path("/sys/class/dmi/id/sys_vendor"),
        Path("/sys/class/dmi/id/product_name"),
        Path("/sys/devices/virtual/dmi/id/sys_vendor"),
        Path("/sys/devices/virtual/dmi/id/product_name"),
    ):
        try:
            chunks.append(candidate.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
    return "\n".join(chunks).lower()


def running_in_hyperv() -> bool:
    """True on Hyper-V guests, not Surface PCs or native Microsoft-branded DMI."""
    text = _dmi_text()
    if "hyper-v" in text or "hyperv" in text:
        return True
    if "microsoft" in text and "virtual machine" in text:
        return True
    try:
        cpu = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "hypervisor" in cpu and any(
        token in cpu for token in ("microsoft", "hyperv", "hyper-v")
    )


def running_in_hypervisor() -> bool:
    """True on Hyper-V and similar VMs. GPU passthrough guests still match."""
    if running_in_hyperv():
        return True
    text = _dmi_text()
    tokens = ("kvm", "qemu", "vmware", "virtualbox", "xen", "bochs", "virtual machine")
    if any(token in text for token in tokens):
        return True
    try:
        kind = Path("/sys/hypervisor/type").read_text(
            encoding="utf-8", errors="ignore"
        ).lower()
    except OSError:
        kind = ""
    if any(token in kind for token in tokens):
        return True
    try:
        cpu = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False
    return "hypervisor" in cpu and "kvm" in cpu


def has_drm_render_node() -> bool:
    dri = Path("/dev/dri")
    try:
        if not dri.is_dir():
            return False
        return any(path.name.startswith("renderD") for path in dri.iterdir())
    except OSError:
        return False


def running_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def needs_software_qt(
    *,
    os_name: str | None = None,
    platform: str | None = None,
    frozen: bool | None = None,
    wsl: bool | None = None,
    hypervisor: bool | None = None,
    hyperv: bool | None = None,
    has_drm: bool | None = None,
    system_qt: bool | None = None,
    software_qt: bool | None = None,
) -> bool:
    """True when Qt would abort without a software scene graph.

    WSL and Hyper-V guests often cannot initialize GLX or EGL, and Qt then
    qFatal("Could not initialize GLX"). Native Linux desktops — including
    frozen NVIDIA/AMD/Intel installers — must keep host OpenGL so Stellarium
    Web can run. ASTRO_DWARF_QT_SYSTEM=1 forces the host GPU. ASTRO_DWARF_QT_SOFTWARE=1
    forces the fallback.
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
    if wsl:
        return True
    if hyperv is None:
        hyperv = bool(hypervisor) if hypervisor is not None else running_in_hyperv()
    if hyperv:
        return True
    _ = frozen
    if has_drm is None:
        has_drm = has_drm_render_node()
    return not has_drm


# Chromium still needs WebGL for Stellarium. --disable-gpu leaves a black atlas.
# SwiftShader can draw without a host GPU. It cannot recover a missing Qt GL
# context; QT_XCB_GL_INTEGRATION=none is required so the window still opens.
SOFTWARE_WEBENGINE_FLAGS = (
    "--enable-webgl --ignore-gpu-blocklist --disable-gpu-sandbox "
    "--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader"
)
LINUX_WEBENGINE_FLAGS = "--enable-webgl --ignore-gpu-blocklist --disable-gpu-sandbox"


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


def apply_software_qt_env() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    # none skips GLX/EGL init. xcb_egl/xcb_glx qFatal on Hyper-V/WSL guests
    # with no usable GPU ("Could not initialize GLX").
    os.environ["QT_XCB_GL_INTEGRATION"] = "none"
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    if os.environ.get("QSG_RHI_BACKEND", "").strip().lower() == "software":
        os.environ.pop("QSG_RHI_BACKEND", None)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = SOFTWARE_WEBENGINE_FLAGS


def configure_qt_display() -> None:
    """Keep the Linux window opening when the guest has no usable GPU."""
    if sys.platform.startswith("linux"):
        _strip_readline_library_path()
        os.environ.setdefault("NO_AT_BRIDGE", "1")
        os.environ.setdefault("GTK_MODULES", "")
        os.environ.setdefault("GTK3_MODULES", "")
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    if needs_software_qt():
        apply_software_qt_env()
    elif sys.platform.startswith("linux"):
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS")
        if not flags or _has_disable_gpu(flags):
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = LINUX_WEBENGINE_FLAGS
        elif "--enable-webgl" not in _chromium_flag_tokens(flags):
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --enable-webgl"
