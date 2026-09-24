"""Route macOS keystrokes to either QML or the embedded sky map.

WKWebView is a native subview of the Qt window. AppKit delivers keys to
whichever view is first responder. That can stay on the web view while a
Settings field shows a caret, or stay on Qt while Stellarium's target search
shows a caret. In both cases the caret blinks and nothing is inserted.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable


def find_named_view(root: Any, name: str, *, children: Callable[[Any], list], class_name: Callable[[Any], str], depth: int = 0) -> Any:
    if root is None or depth > 12:
        return None
    label = class_name(root) or ""
    if label == name or label.endswith("." + name):
        return root
    for child in children(root) or []:
        found = find_named_view(child, name, children=children, class_name=class_name, depth=depth + 1)
        if found is not None:
            return found
    return None


def qpa_blocks_appkit(platform: str | None = None) -> bool:
    """True when this process is not a Cocoa Qt session.

    The installer smoke test uses the offscreen plugin. Its window id is not
    an NSView, and messaging it through AppKit aborts the process.
    """
    raw = os.environ.get("QT_QPA_PLATFORM") if platform is None else platform
    name = str(raw or "").split(":")[0].strip()
    if name and name != "cocoa":
        return True
    if platform is not None:
        return False
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        active = str(app.platformName() if app is not None else "")
    except Exception:
        active = ""
    return bool(active) and active != "cocoa"


def sync_keyboard_owner(window, *, web_view: bool) -> bool:
    """Point AppKit at WKWebView or the Qt view. False if the web view is not up yet."""
    if sys.platform != "darwin" or window is None or qpa_blocks_appkit():
        return not web_view
    try:
        host = int(window.winId() or 0)
    except Exception:
        return False
    if not host:
        return False
    if web_view and _focus_is_other_window(window):
        web_view = False
    if web_view:
        target = _find_webview(host)
        if not target:
            return False
    else:
        target = _focus_view(host)
    _make_first_responder(target)
    return True


def _focus_is_other_window(window) -> bool:
    try:
        from PySide6.QtGui import QGuiApplication

        focused = QGuiApplication.focusWindow()
    except Exception:
        return False
    return focused is not None and focused is not window


def _focus_view(host: int) -> int:
    try:
        from PySide6.QtGui import QGuiApplication

        focused = QGuiApplication.focusWindow()
        if focused is not None:
            view = int(focused.winId() or 0)
            if view:
                return view
    except Exception:
        pass
    return host


def _find_webview(host: int) -> int:
    found = find_named_view(host, "WKWebView", children=_subviews, class_name=_class_name)
    return int(found or 0)


def _libobjc():
    import ctypes

    return ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")


def _sel(name: str) -> int:
    import ctypes

    lib = _libobjc()
    lib.sel_registerName.argtypes = [ctypes.c_char_p]
    lib.sel_registerName.restype = ctypes.c_void_p
    return int(lib.sel_registerName(name.encode("utf-8")) or 0)


def _send(obj: int, selector: str, *args: int):
    import ctypes

    lib = _libobjc()
    argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    values = [ctypes.c_void_p(obj), ctypes.c_void_p(_sel(selector))]
    for arg in args:
        argtypes.append(ctypes.c_void_p)
        values.append(ctypes.c_void_p(int(arg)))
    proto = ctypes.CFUNCTYPE(ctypes.c_void_p, *argtypes)
    fn = proto(("objc_msgSend", lib))
    return int(fn(*values) or 0)


def _send_ulong(obj: int, selector: str, index: int | None = None) -> int:
    import ctypes

    lib = _libobjc()
    if index is None:
        proto = ctypes.CFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p)
        fn = proto(("objc_msgSend", lib))
        return int(fn(ctypes.c_void_p(obj), ctypes.c_void_p(_sel(selector))) or 0)
    proto = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
    fn = proto(("objc_msgSend", lib))
    return int(fn(ctypes.c_void_p(obj), ctypes.c_void_p(_sel(selector)), int(index)) or 0)


def _class_name(view: int) -> str:
    import ctypes

    lib = _libobjc()
    lib.object_getClassName.argtypes = [ctypes.c_void_p]
    lib.object_getClassName.restype = ctypes.c_char_p
    raw = lib.object_getClassName(ctypes.c_void_p(int(view)))
    if not raw:
        return ""
    return raw.decode("utf-8", "replace")


def _subviews(view: int) -> list[int]:
    array = _send(int(view), "subviews")
    if not array:
        return []
    count = min(_send_ulong(array, "count"), 64)
    found = []
    for index in range(count):
        child = _send_ulong(array, "objectAtIndex:", index)
        if child:
            found.append(child)
    return found


def _make_first_responder(view: int) -> None:
    window = _send(int(view), "window")
    if window:
        _send(window, "makeFirstResponder:", int(view))
