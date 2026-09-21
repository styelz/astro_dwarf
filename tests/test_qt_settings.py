from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QSettings

from astro_dwarf.qt_settings import flush_qt_settings


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_flush_writes_ini_while_store_is_alive(tmp_path: Path) -> None:
    app = QCoreApplication.instance() or QCoreApplication(["astro-dwarf-settings-test"])
    previous_org = app.organizationName()
    previous_name = app.applicationName()
    previous_format = QSettings.defaultFormat()
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    app.setOrganizationName("AstroFlushOrg")
    app.setApplicationName("AstroFlushApp")
    try:
        live = QSettings()
        live.setValue("panelLayout/panelOrderJson", "keep-me")
        flush_qt_settings()
        files = [path for path in tmp_path.rglob("*") if path.is_file()]
        _assert(bool(files), f"no settings file under {tmp_path}")
        blob = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in files)
        _assert("keep-me" in blob, blob)
    finally:
        app.setOrganizationName(previous_org)
        app.setApplicationName(previous_name)
        QSettings.setDefaultFormat(previous_format)


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as folder:
        test_flush_writes_ini_while_store_is_alive(Path(folder))
    print("qt_settings tests ok")
