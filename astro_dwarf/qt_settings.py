"""Flush Qt settings before a hard process exit.

Linux QSettings writes an INI file from the destructor or sync(). The GUI
process ends with os._exit() so those destructors never run, and Control
panel layout (and other QML Settings) never reach disk. Windows registry
writes are eager enough that the same path still looks fine there.
"""

from __future__ import annotations


def flush_qt_settings() -> None:
    from PySide6.QtCore import QSettings

    QSettings().sync()
