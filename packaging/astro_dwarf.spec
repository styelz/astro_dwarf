import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files


ROOT = Path(SPECPATH).parent
ICON_DIR = ROOT / "packaging" / "icons"
VERSION = os.environ.get(
    "ASTRO_DWARF_VERSION",
    (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
)
# UPX regularly breaks Qt plugins on macOS and Linux.
USE_UPX = sys.platform == "win32"


def collect_pyside_qml() -> list[tuple[str, str]]:
    """Copy QML modules into the layout PyInstaller's PySide6 runtime hook expects."""
    import PySide6

    base = Path(PySide6.__file__).resolve().parent
    modules = ["QtCore", "QtMultimedia", "QtQml", "QtQuick", "QtWebView"]
    if sys.platform.startswith("linux"):
        modules.extend(("QtWebEngine", "QtWebChannel"))
    collected: list[tuple[str, str]] = []
    for src_root, dest_root in (
        (base / "qml", "PySide6/qml"),
        (base / "Qt" / "qml", "PySide6/Qt/qml"),
    ):
        for module in modules:
            src = src_root / module
            if src.is_dir():
                collected.append((str(src), f"{dest_root}/{module}"))
    return collected


def collect_native_webview_plugins() -> list[tuple[str, str]]:
    """Ship the OS WebView backend. Analysis does not see this lazy plugin."""
    import PySide6

    base = Path(PySide6.__file__).resolve().parent
    collected: list[tuple[str, str]] = []
    for src_root, dest_root in (
        (base / "plugins" / "webview", "PySide6/plugins/webview"),
        (base / "Qt" / "plugins" / "webview", "PySide6/Qt/plugins/webview"),
    ):
        if not src_root.is_dir():
            continue
        for path in src_root.iterdir():
            if not path.is_file() or "webview" not in path.name.lower():
                continue
            if "webengine" in path.name.lower() and not sys.platform.startswith("linux"):
                continue
            collected.append((str(path), dest_root))
    return collected


datas = [
    (str(ROOT / "VERSION"), "."),
    (str(ROOT / "astro_dwarf" / "qml"), "qml"),
]
# Qt's title-bar icon comes from QIcon files, not the EXE resource PyInstaller embeds.
for _icon_name in ("astro-dwarf.ico", "astro-dwarf.png"):
    _icon_path = ICON_DIR / _icon_name
    if _icon_path.is_file():
        datas.append((str(_icon_path), "."))
        datas.append((str(_icon_path), "qml/assets"))
datas += collect_pyside_qml()
_qml_includes = [
    "qml/QtCore/**",
    "qml/QtMultimedia/**",
    "qml/QtQml/**",
    "qml/QtQuick/**",
    "qml/QtWebView/**",
    "Qt/qml/QtCore/**",
    "Qt/qml/QtMultimedia/**",
    "Qt/qml/QtQml/**",
    "Qt/qml/QtQuick/**",
    "Qt/qml/QtWebView/**",
]
if sys.platform.startswith("linux"):
    _qml_includes.extend(
        (
            "qml/QtWebEngine/**",
            "qml/QtWebChannel/**",
            "Qt/qml/QtWebEngine/**",
            "Qt/qml/QtWebChannel/**",
        )
    )
datas += collect_data_files("PySide6", includes=_qml_includes)

binaries = []
for filename in ("ffmpeg.exe", "ffmpeg"):
    candidate = ROOT / "vendor" / filename
    if candidate.is_file():
        binaries.append((str(candidate), "."))
native_webview_plugins = collect_native_webview_plugins()
binaries += native_webview_plugins
webview_upx_exclude = [Path(src).name for src, _dest in native_webview_plugins]

hiddenimports = [
    "app",
    "astro_dwarf",
    "astro_dwarf.app",
    "astro_dwarf.device_worker",
    "astro_dwarf.domain",
    "astro_dwarf.qt_backend",
    "astro_dwarf.runtime",
    "astro_dwarf.services",
    "astro_dwarf.storage",
    "astro_dwarf.stream_preview",
    "astro_dwarf.image_enhance",
    "astro_dwarf.location",
    "numpy",
    "cv2",
    "astro_dwarf.version",
    "tzdata",
    "PySide6.QtMultimedia",
    "PySide6.QtOpenGL",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtSvg",
    "PySide6.QtWebView",
    "filelock",
    "google.protobuf",
    "websockets",
    "websockets.client",
]


def collect_package(name: str) -> None:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(name)
    datas.extend(pkg_datas)
    binaries.extend(pkg_binaries)
    hiddenimports.extend(pkg_hiddenimports)


for package in ("dwarf_python_api", "dwarf_ble_connect", "websockets", "google.protobuf", "filelock", "bleak", "tzdata", "numpy", "cv2"):
    collect_package(package)
if sys.platform.startswith("linux"):
    hiddenimports.extend(
        (
            "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineQuick",
            "PySide6.QtWebChannel",
        )
    )
    for package in ("PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel"):
        collect_package(package)

analysis = Analysis(
    [str(ROOT / "packaging" / "entrypoint.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)


def _linux_host_gl_lib(dest_name: str) -> bool:
    """Leave GPU driver libraries to the host; bundled Mesa GLX abort()s on NVIDIA."""
    name = Path(str(dest_name)).name
    return name.startswith(
        (
            "libGL.so",
            "libEGL.so",
            "libGLESv2.so",
            "libGLESv1",
            "libOpenGL.so",
            "libGLdispatch.so",
            "libGLX.so",
            "libGLX_",
            "libnvidia-",
            "libvulkan.so",
            "libdrm.so",
            "libdrm_",
            "libgbm.so",
            "libwayland-egl.so",
        )
    )


if sys.platform.startswith("linux"):
    analysis.binaries = [
        entry for entry in analysis.binaries if not _linux_host_gl_lib(entry[0])
    ]

# Windows and macOS use the OS web view. Keep Chromium out of those bundles.
# Linux has no native QtWebView backend, so the SKY page needs Qt WebEngine.
def _is_webengine_payload(entry) -> bool:
    text = " ".join(str(part) for part in entry[:2]).lower()
    return "webengine" in text


if not sys.platform.startswith("linux"):
    analysis.binaries = [entry for entry in analysis.binaries if not _is_webengine_payload(entry)]
    analysis.datas = [entry for entry in analysis.datas if not _is_webengine_payload(entry)]

pyz = PYZ(analysis.pure)

if sys.platform == "win32":
    icon = str(ICON_DIR / "astro-dwarf.ico")
elif sys.platform == "darwin" and (ICON_DIR / "astro-dwarf.icns").is_file():
    icon = str(ICON_DIR / "astro-dwarf.icns")
else:
    icon = str(ICON_DIR / "astro-dwarf.png")

application = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AstroDwarf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=USE_UPX,
    console=False,
    icon=icon,
)

# A console-subsystem helper keeps stdin/stdout pipes available for QProcess
# while the user-facing Windows executable remains a GUI application.
worker = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AstroDwarfWorker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=USE_UPX,
    console=True,
    icon=icon,
)

collection = COLLECT(
    application,
    worker,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=USE_UPX,
    upx_exclude=webview_upx_exclude,
    name="AstroDwarf",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="AstroDwarf.app",
        icon=icon,
        bundle_identifier="com.astrodwarf.app",
        info_plist={
            "CFBundleDisplayName": "Astro Dwarf",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
        },
    )
