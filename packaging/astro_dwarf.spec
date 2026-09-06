import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files


ROOT = Path(SPECPATH).parent
ICON_DIR = ROOT / "packaging" / "icons"
VERSION = os.environ.get("ASTRO_DWARF_VERSION", "0.1.0")
# UPX regularly breaks Qt plugins on macOS and Linux.
USE_UPX = sys.platform == "win32"


def collect_pyside_qml() -> list[tuple[str, str]]:
    """Copy QML modules into the layout PyInstaller's PySide6 runtime hook expects."""
    import PySide6

    base = Path(PySide6.__file__).resolve().parent
    modules = ("QtCore", "QtMultimedia", "QtQml", "QtQuick")
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


datas = [
    (str(ROOT / "qml"), "qml"),
]
datas += collect_pyside_qml()
datas += collect_data_files(
    "PySide6",
    includes=[
        "qml/QtCore/**",
        "qml/QtMultimedia/**",
        "qml/QtQml/**",
        "qml/QtQuick/**",
        "Qt/qml/QtCore/**",
        "Qt/qml/QtMultimedia/**",
        "Qt/qml/QtQml/**",
        "Qt/qml/QtQuick/**",
    ],
)

binaries = []
for filename in ("ffmpeg.exe", "ffmpeg"):
    candidate = ROOT / "vendor" / filename
    if candidate.is_file():
        binaries.append((str(candidate), "."))

hiddenimports = [
    "PySide6.QtMultimedia",
    "PySide6.QtOpenGL",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtSvg",
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


for package in ("dwarf_python_api", "websockets", "google.protobuf", "filelock", "bleak"):
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
