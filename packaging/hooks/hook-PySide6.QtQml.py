"""Collect QtQml libraries without PyInstaller's all-modules QML sweep.

The application-specific QML module directories are listed in the spec file.
The stock hook collects every installed QML module, including WebEngine and
Quick3D, which adds hundreds of megabytes of unrelated runtime files.
"""

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
