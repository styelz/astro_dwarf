"""Display environment that must exist before PySide/Qt loads."""

from __future__ import annotations

import os
import re
import subprocess
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
    Web can run. A frozen bundle whose libstdc++ is older than the host
    driver is re-executed with the host runtime first; if a context still
    cannot be created, the Qt Quick process sets ASTRO_DWARF_QT_SOFTWARE=1
    instead of aborting. ASTRO_DWARF_QT_SYSTEM=1 forces the host GPU.
    ASTRO_DWARF_QT_SOFTWARE=1 forces the fallback.
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
    "--disable-features=Vulkan --enable-unsafe-swiftshader "
    "--use-gl=angle --use-angle=swiftshader"
)
# GBM often fails on virtio / some Mesa stacks and on NVIDIA without
# nvidia-drm modeset. Chromium then picks Vulkan, and Stellarium's WASM
# abort()s. SwiftShader still draws, but its dma-buf never reaches the
# Qt window ("Compositor returned null texture"), so both atlases stay
# blank unless compositing is done on the CPU.
LINUX_WEBENGINE_FLAGS = (
    "--enable-webgl --ignore-gpu-blocklist --disable-gpu-sandbox "
    "--disable-gpu-compositing --disable-features=Vulkan "
    "--enable-unsafe-swiftshader --use-gl=angle --use-angle=swiftshader"
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


def apply_software_qt_env() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    # none skips GLX/EGL init. xcb_egl/xcb_glx qFatal on Hyper-V/WSL guests
    # with no usable GPU ("Could not initialize GLX"). Qt Quick still
    # qFatal("Failed to initialize graphics backend for OpenGL") unless the
    # software scene graph is selected before QGuiApplication, even when a
    # leftover environment asked for OpenGL.
    os.environ["QT_XCB_GL_INTEGRATION"] = "none"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ.pop("QSG_RHI_BACKEND", None)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = SOFTWARE_WEBENGINE_FLAGS


def fall_back_to_software_qt() -> None:
    """Open without a host GL context.

    Wayland's platform plugin needs EGL. A session whose driver cannot
    create a context still has XWayland on desktop compositors, and the
    xcb software path is what keeps Qt Quick from aborting.
    """
    os.environ["ASTRO_DWARF_QT_SOFTWARE"] = "1"
    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if platform in ("", "wayland", "wayland-egl"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


_SYMBOL_VERSION = {
    "GLIBCXX_": re.compile(rb"GLIBCXX_(\d+(?:\.\d+)*)"),
    "GCC_": re.compile(rb"GCC_(\d+(?:\.\d+)*)"),
}


def max_symbol_version(blob: bytes, prefix: str) -> tuple[int, ...] | None:
    """Highest ELF version symbol, so GLIBCXX_3.4.30 beats GLIBCXX_3.4.9."""
    pattern = _SYMBOL_VERSION.get(prefix)
    if pattern is None:
        return None
    best: tuple[int, ...] | None = None
    for match in pattern.finditer(blob):
        key = tuple(int(part) for part in match.group(1).split(b"."))
        if best is None or key > best:
            best = key
    return best


def newer_symbol_version(host: bytes, bundled: bytes, prefix: str) -> bool:
    host_version = max_symbol_version(host, prefix)
    bundled_version = max_symbol_version(bundled, prefix)
    if host_version is None or bundled_version is None:
        return False
    return host_version > bundled_version


def cxx_runtime_preload(
    *,
    bundled_libstd: bytes | None,
    host_libstd: bytes | None,
    host_libstd_path: str | None,
    host_libgcc_path: str | None,
    same_file: bool = False,
) -> list[str]:
    """Host libstdc++ and its matching libgcc when the host copy is newer.

    The frozen bundle carries the build machine's libstdc++. PyInstaller
    puts that directory first on LD_LIBRARY_PATH, so a rolling-release
    driver (Arch, CachyOS) fails to load and Qt reports EGL missing,
    Vulkan -9 (VK_ERROR_INCOMPATIBLE_DRIVER), then aborts. Preloading the
    newer host pair lets the driver load. An older host keeps the bundle.
    """
    if same_file or not bundled_libstd or not host_libstd or not host_libstd_path:
        return []
    if not host_libgcc_path:
        return []
    if not newer_symbol_version(host_libstd, bundled_libstd, "GLIBCXX_"):
        return []
    return [host_libstd_path, host_libgcc_path]


def parse_ldconfig_path(text: str, soname: str) -> str | None:
    """First x86-64 ldconfig hit for soname. Skip i386 copies."""
    tagged: list[str] = []
    untagged: list[str] = []
    for line in text.splitlines():
        if "=>" not in line:
            continue
        left, right = line.split("=>", 1)
        token = left.strip().split()
        if not token or token[0] != soname:
            continue
        path = right.strip()
        if not path:
            continue
        if "x86-64" in left or "x86_64" in left:
            tagged.append(path)
        elif any(arch in left for arch in ("i386", "i686", "x32")):
            continue
        else:
            untagged.append(path)
    if tagged:
        return tagged[0]
    if untagged:
        return untagged[0]
    return None


def _ldconfig_text() -> str:
    for binary in ("ldconfig", "/usr/sbin/ldconfig", "/sbin/ldconfig"):
        try:
            completed = subprocess.run(
                [binary, "-p"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0 and completed.stdout:
            return completed.stdout
    return ""


def host_shared_object(soname: str) -> Path | None:
    parsed = parse_ldconfig_path(_ldconfig_text(), soname)
    candidates: list[Path] = []
    if parsed:
        candidates.append(Path(parsed))
    for folder in (
        Path("/usr/lib"),
        Path("/usr/lib64"),
        Path("/usr/lib/x86_64-linux-gnu"),
        Path("/lib64"),
        Path("/lib/x86_64-linux-gnu"),
    ):
        candidates.append(folder / soname)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _read_bytes(path: Path | None) -> bytes | None:
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def bundled_cxx_preload_paths() -> list[str]:
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return []
    root = Path(meipass)
    bundled = root / "libstdc++.so.6"
    host_std = host_shared_object("libstdc++.so.6")
    host_gcc = host_shared_object("libgcc_s.so.1")
    same_file = False
    if host_std is not None:
        try:
            same_file = bundled.resolve() == host_std.resolve()
        except OSError:
            same_file = False
    return cxx_runtime_preload(
        bundled_libstd=_read_bytes(bundled),
        host_libstd=_read_bytes(host_std),
        host_libstd_path=str(host_std) if host_std is not None else None,
        host_libgcc_path=str(host_gcc) if host_gcc is not None else None,
        same_file=same_file,
    )


def prefer_host_cxx_runtime() -> None:
    """Re-exec once so the dynamic linker preloads a newer host libstdc++.

    LD_PRELOAD is read at process start. PyInstaller prepends the bundle to
    LD_LIBRARY_PATH and does not clear LD_PRELOAD, so the replacement
    process loads the host C++ runtime before Mesa or NVIDIA.
    """
    if not running_frozen() or not sys.platform.startswith("linux"):
        return
    if os.environ.get("ASTRO_DWARF_CXX_RUNTIME") == "1":
        return
    os.environ["ASTRO_DWARF_CXX_RUNTIME"] = "1"
    paths = bundled_cxx_preload_paths()
    if not paths:
        return
    current = [part for part in os.environ.get("LD_PRELOAD", "").split(":") if part]
    merged: list[str] = []
    for part in [*paths, *current]:
        if part not in merged:
            merged.append(part)
    os.environ["LD_PRELOAD"] = ":".join(merged)
    argv = [sys.executable, *sys.argv[1:]]
    try:
        os.execve(sys.executable, argv, os.environ)
    except OSError:
        return


def should_probe_host_gl(
    *,
    platform: str,
    argv: list[str],
    env: dict[str, str],
) -> bool:
    """True for the process that is about to open Qt Quick on Linux.

    The splash parent only paints widgets. Probing there delays the splash
    and does not stop the child from aborting. Workers never open a scene.
    """
    if not str(platform).startswith("linux"):
        return False
    if env.get("ASTRO_DWARF_GL_PROBE") == "1":
        return False
    if env.get("ASTRO_DWARF_GL_PROBED") == "1":
        return False
    if env.get("ASTRO_DWARF_QT_SYSTEM") == "1":
        return False
    if env.get("ASTRO_DWARF_QT_SOFTWARE") == "1":
        return False
    if env.get("QT_QUICK_BACKEND", "").strip().lower() == "software":
        return False
    if "--worker" in argv or env.get("ASTRO_DWARF_WORKER") == "1":
        return False
    if "--child" in argv:
        return True
    if env.get("ASTRO_DWARF_NO_SPLASH") == "1":
        return True
    if env.get("ASTRO_DWARF_TEST_HARNESS") == "1":
        return True
    if env.get("ASTRO_DWARF_TEST_EXIT_MS"):
        return True
    return False


def run_gl_probe() -> int:
    """1 when Qt cannot make an OpenGL context current. Used by a child process."""
    try:
        from PySide6.QtGui import QGuiApplication, QOffscreenSurface, QOpenGLContext
    except Exception:
        return 1
    try:
        if QGuiApplication.instance() is None:
            QGuiApplication(["astro-dwarf-gl-probe"])
        context = QOpenGLContext()
        surface = QOffscreenSurface()
        surface.setFormat(context.format())
        surface.create()
        if not surface.isValid() or not context.create() or not context.makeCurrent(surface):
            return 1
        context.doneCurrent()
    except Exception:
        return 1
    return 0


def gl_platform_choice(default_ok: bool, xcb_ok: bool, current: str) -> str | None:
    """'keep' or 'xcb' when some platform created a context. None means software."""
    if default_ok:
        return "keep"
    if current.strip().lower() in ("", "wayland", "wayland-egl") and xcb_ok:
        return "xcb"
    return None


def _gl_probe_succeeded(platform: str | None) -> bool:
    """False when a short-lived probe cannot create the temporary GL context.

    Qt Quick aborts in-process on that failure. The probe is allowed to
    exit non-zero, including SIGABRT, without taking the window down.
    """
    env = os.environ.copy()
    env["ASTRO_DWARF_GL_PROBE"] = "1"
    env["ASTRO_DWARF_NO_SPLASH"] = "1"
    env.pop("ASTRO_DWARF_TEST_EXIT_MS", None)
    env.pop("ASTRO_DWARF_TEST_HARNESS", None)
    if platform:
        env["QT_QPA_PLATFORM"] = platform
    try:
        completed = subprocess.run(
            [sys.executable],
            env=env,
            timeout=12,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def select_host_gl_platform() -> str | None:
    """Platform that can create a context: 'keep', 'xcb', or None."""
    os.environ["ASTRO_DWARF_GL_PROBED"] = "1"
    current = os.environ.get("QT_QPA_PLATFORM", "")
    default_ok = _gl_probe_succeeded(None)
    xcb_ok = False
    if not default_ok and current.strip().lower() in ("", "wayland", "wayland-egl"):
        xcb_ok = _gl_probe_succeeded("xcb")
    return gl_platform_choice(default_ok, xcb_ok, current)


def _narrow_locale(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    if "UTF-8" in text.upper() or "UTF8" in text.upper():
        return False
    return text in ("C", "POSIX")


def _ensure_utf8_locale() -> None:
    """Qt text shaping needs UTF-8. SSH/cron often start with LANG=C."""
    lang = os.environ.get("LANG", "")
    if _narrow_locale(lang):
        os.environ["LANG"] = "C.UTF-8"
    lc_all = os.environ.get("LC_ALL", "")
    if lc_all and _narrow_locale(lc_all):
        os.environ["LC_ALL"] = "C.UTF-8"
    lc_ctype = os.environ.get("LC_CTYPE", "")
    if lc_ctype and _narrow_locale(lc_ctype):
        os.environ["LC_CTYPE"] = "C.UTF-8"


def isolate_bundled_fontconfig() -> Path | None:
    """Point fontconfig at the shipped file so host conf.d cannot break matching."""
    if not sys.platform.startswith("linux"):
        return None
    if os.environ.get("FONTCONFIG_FILE", "").strip():
        current = Path(os.environ["FONTCONFIG_FILE"])
        return current if current.is_file() else None
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "fonts" / "fonts.conf")
    try:
        candidates.append(Path(sys.executable).resolve().parent / "fonts" / "fonts.conf")
    except OSError:
        pass
    candidates.append(Path(__file__).resolve().parent / "fonts" / "fonts.conf")
    for path in candidates:
        if path.is_file():
            os.environ["FONTCONFIG_FILE"] = str(path)
            os.environ.setdefault("FONTCONFIG_PATH", str(path.parent))
            return path
    return None


def is_noisy_webengine_message(message: str) -> bool:
    text = str(message or "")
    if "Aborted(" in text or text.startswith("js: Aborted"):
        return True
    noisy = (
        "Failed to get native pixmap",
        "Compositor returned null texture",
        "dma_buf acquisition failure",
    )
    return any(token in text for token in noisy)


def install_qt_message_filter() -> None:
    """Drop Stellarium WASM abort spam; keep every other Qt message."""
    try:
        from PySide6.QtCore import qInstallMessageHandler
    except Exception:
        return

    def _handler(_mode, _context, message) -> None:
        if is_noisy_webengine_message(str(message)):
            return
        sys.stderr.write(str(message) + "\n")

    qInstallMessageHandler(_handler)


def configure_qt_display() -> None:
    """Keep the Linux window opening when the guest has no usable GPU."""
    if os.environ.get("ASTRO_DWARF_GL_PROBE") == "1":
        # os._exit skips Qt's teardown. A successful context can still
        # SIGABRT while QGuiApplication is destroyed, which the parent
        # would treat as a missing driver.
        os._exit(run_gl_probe())
    # Before any Qt import: a newer host libstdc++ has to be preloaded or
    # Arch/CachyOS drivers never create the GL context Qt Quick requires.
    prefer_host_cxx_runtime()
    if sys.platform.startswith("win"):
        # Harmless DirectWrite noise from Qt enumerating legacy OEM raster
        # fonts (e.g. "8514oem"); unrelated to qt_fonts.py candidate lists.
        rules = os.environ.get("QT_LOGGING_RULES", "")
        if "qt.qpa.fonts" not in rules:
            extra = "qt.qpa.fonts.warning=false"
            os.environ["QT_LOGGING_RULES"] = f"{rules};{extra}" if rules else extra
    if sys.platform.startswith("linux"):
        _ensure_utf8_locale()
        isolate_bundled_fontconfig()
        _strip_readline_library_path()
        os.environ.setdefault("NO_AT_BRIDGE", "1")
        os.environ.setdefault("GTK_MODULES", "")
        os.environ.setdefault("GTK3_MODULES", "")
        os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
        rules = os.environ.get("QT_LOGGING_RULES", "")
        if "js=" not in rules:
            extra = "js.warning=false;js.critical=false"
            os.environ["QT_LOGGING_RULES"] = f"{rules};{extra}" if rules else extra
    if (
        running_frozen()
        and should_probe_host_gl(platform=sys.platform, argv=sys.argv, env=dict(os.environ))
        and not needs_software_qt()
    ):
        chosen = select_host_gl_platform()
        if chosen is None:
            sys.stderr.write(
                "Astro Dwarf: OpenGL did not start, so this window is using software rendering.\n"
            )
            fall_back_to_software_qt()
        elif chosen == "xcb":
            os.environ["QT_QPA_PLATFORM"] = "xcb"
    if needs_software_qt():
        apply_software_qt_env()
    elif sys.platform.startswith("linux"):
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS")
        if not flags or _has_disable_gpu(flags):
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = LINUX_WEBENGINE_FLAGS
        elif "--enable-webgl" not in _chromium_flag_tokens(flags):
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --enable-webgl"
        elif "--disable-features=Vulkan" not in flags:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
                f"{flags} --disable-features=Vulkan --enable-unsafe-swiftshader "
                "--disable-gpu-compositing"
            )
        elif "--disable-gpu-compositing" not in _chromium_flag_tokens(flags):
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --disable-gpu-compositing"
    if sys.platform.startswith("linux"):
        install_qt_message_filter()
