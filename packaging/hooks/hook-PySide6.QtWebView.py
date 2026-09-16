"""Collect QtWebView without Chromium/WebEngine on Windows and macOS.

Qt loads the OS backend (WebView2 / WKWebView) from plugins/webview only when a
WebView is created. That plugin is not a link-time dependency of Qt6WebView.dll,
so Analysis misses it unless this hook collects it. Missing it makes Qt
qFatal() when the SKY tab opens. Linux uses Qt WebEngine instead.
"""

import sys

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)


def _is_webengine(entry) -> bool:
    return "webengine" in " ".join(str(part) for part in entry[:2]).lower()


if not sys.platform.startswith("linux"):
    binaries = [entry for entry in binaries if not _is_webengine(entry)]
    datas = [entry for entry in datas if not _is_webengine(entry)]
