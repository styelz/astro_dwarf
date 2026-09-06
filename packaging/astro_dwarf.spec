import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files


ROOT = Path(SPECPATH).parent
ICON_DIR = ROOT / "packaging" / "icons"
VERSION = os.environ.get("ASTRO_DWARF_VERSION", "0.1.0")

datas = [
    (str(ROOT / "astro_dwarf" / "qml"), "astro_dwarf/qml"),
]
datas += collect_data_files(
    "PySide6",
    includes=[
        "qml/QtCore/**",
        "qml/QtMultimedia/**",
        "qml/QtQml/**",
        "qml/QtQuick/**",
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
]

sdk_datas, sdk_binaries, sdk_hiddenimports = collect_all("dwarf_python_api")
datas += sdk_datas
binaries += sdk_binaries
hiddenimports += sdk_hiddenimports

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

icon = str(ICON_DIR / "astro-dwarf.ico") if sys.platform == "win32" else str(ICON_DIR / "astro-dwarf.png")

application = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AstroDwarf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    upx=True,
    console=True,
    icon=icon,
)

collection = COLLECT(
    application,
    worker,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
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
