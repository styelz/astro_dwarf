"""Env-gated HUD harness server for scripts/harness.py.

Indoor HUD scene: ``scripts/harness.py nudge 90`` (joystick up) lifts the
head off the table. Snapshot first; skip that nudge when the room is already
in frame.

Sky work (calibrate, GOTO, mosaic, track) needs stars out the window, not
the table or roof. Snapshot and read it. Polar pos homes to the polar pose
(indoors: the roof) and is not a recovery for a failed mosaic or GOTO.

Do not power down the telescope unless the user explicitly asks.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

LAB_DEVICE_IP = "192.168.1.42"
DEFAULT_PORT = 8765
PAGE_NAMES = {
    0: "control",
    1: "calendar",
    2: "sessions",
    3: "history",
    4: "media",
    5: "sky",
    6: "settings",
}
PAGE_INDEX = {name: index for index, name in PAGE_NAMES.items()}
SKIP_OBJECT_NAMES = {"splitHandle", "settingsPage"}
LAYOUT_PREFIXES = ("panelDrag-", "panelEdge-", "layoutResetMenu")
PAD_ALIASES = {
    "POWER": "power_down",
    "CALIBRATE": "calibrate",
    "AUTO FOCUS": "autofocus",
    "INFINITY": "infinity",
    "POLAR / EQ": "polar",
    "POLAR POS": "polar_position",
    "LIGHTS": "lights_on",
    "INDICATOR": "indicator_on",
    "STACK": "stack",
    "MOSAIC STACK": "stack",
    "TRACK": "track",
    "BURST": "burst_start",
    "RECORD": "record_start",
    "TIMELAPSE": "timelapse_start",
    "REBOOT": "reboot",
}


def pad_start_from_query(query: str) -> str | None:
    text = str(query or "").strip()
    if not text:
        return None
    if text.startswith("pad-"):
        return text[4:]
    if text in PAD_ALIASES:
        return PAD_ALIASES[text]
    lowered = {key.lower(): value for key, value in PAD_ALIASES.items()}
    if text.lower() in lowered:
        return lowered[text.lower()]
    if text in set(PAD_ALIASES.values()):
        return text
    return None


def harness_enabled(env: dict[str, str] | None = None, *, frozen: bool = False) -> bool:
    source = os.environ if env is None else env
    return str(source.get("ASTRO_DWARF_TEST_HARNESS") or "").strip() == "1" and not frozen


def harness_port(env: dict[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    raw = str(source.get("ASTRO_DWARF_TEST_HARNESS_PORT") or "").strip()
    if not raw:
        return DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return port if 1 <= port <= 65535 else DEFAULT_PORT


def device_ready(device: Any) -> bool:
    """True as soon as the link is up. Preview start does not count as busy."""
    if not isinstance(device, dict):
        return False
    return bool(device.get("connected")) and not bool(device.get("connecting")) and not bool(
        device.get("disconnecting")
    ) and not bool(device.get("cancelling"))


def device_by_ip(devices: Any, ip: str = LAB_DEVICE_IP) -> dict[str, Any] | None:
    wanted = str(ip or LAB_DEVICE_IP).strip()
    if not wanted:
        return None
    for item in devices or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("ip_address") or "").strip() == wanted:
            return item
    return None


def page_name_from_index(index: Any) -> str:
    try:
        return PAGE_NAMES[int(index)]
    except (TypeError, ValueError, KeyError):
        return "control"


def page_index_from_name(name: str) -> int | None:
    key = str(name or "").strip().lower()
    if key == "settings" or key == "6":
        return None
    if key.isdigit():
        index = int(key)
        return index if index in PAGE_NAMES and index != 6 else None
    return PAGE_INDEX.get(key)


def is_layout_chrome(name: str) -> bool:
    text = str(name or "")
    if text in SKIP_OBJECT_NAMES and text != "settingsPage":
        return True
    return text.startswith(LAYOUT_PREFIXES)


def should_skip_names(name: str, ancestors: list[str]) -> bool:
    if name == "settingsPage" or "settingsPage" in ancestors:
        return True
    return is_layout_chrome(name)


def object_name_of(obj: Any) -> str:
    getter = getattr(obj, "objectName", None)
    if callable(getter):
        return str(getter() or "")
    return str(getattr(obj, "objectName", "") or "")


def ancestor_names(obj: Any) -> list[str]:
    names: list[str] = []
    parent_fn = getattr(obj, "parent", None)
    current = parent_fn() if callable(parent_fn) else None
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = object_name_of(current)
        if name:
            names.append(name)
        parent_fn = getattr(current, "parent", None)
        current = parent_fn() if callable(parent_fn) else None
    return names


def should_skip_object(obj: Any) -> bool:
    return should_skip_names(object_name_of(obj), ancestor_names(obj))


def _property(obj: Any, name: str, default: Any = None) -> Any:
    getter = getattr(obj, "property", None)
    if callable(getter):
        try:
            value = getter(name)
        except Exception:
            return default
        return default if value is None else value
    return getattr(obj, name, default)


def is_visible_item(obj: Any) -> bool:
    visible = _property(obj, "visible", True)
    if visible is False:
        return False
    opacity = _property(obj, "opacity", 1)
    try:
        if float(opacity) == 0:
            return False
    except (TypeError, ValueError):
        pass
    return True


def _has_signal(obj: Any, name: str) -> bool:
    target = getattr(obj, name, None)
    return target is not None and callable(getattr(target, "emit", None))


def control_kind(obj: Any) -> str:
    if _property(obj, "from", None) is not None and _property(obj, "to", None) is not None and _property(obj, "value", None) is not None:
        return "spinbox"
    if _property(obj, "currentIndex", None) is not None and _property(obj, "model", None) is not None:
        return "combo"
    if _property(obj, "checked", None) is not None and (
        callable(getattr(obj, "click", None)) or callable(getattr(obj, "setOn", None)) or _has_signal(obj, "clicked")
    ):
        if _property(obj, "text", None) is not None or _property(obj, "accessibleName", None):
            return "check"
    if _property(obj, "placeholderText", None) is not None or _property(obj, "echoMode", None) is not None:
        if _property(obj, "text", None) is not None:
            return "field"
    if callable(getattr(obj, "click", None)) or _has_signal(obj, "clicked"):
        return "button"
    if callable(getattr(obj, "triggered", None)) or _has_signal(obj, "triggered"):
        name = object_name_of(obj)
        text = str(_property(obj, "text", "") or "")
        if name or text:
            return "menu"
    return ""


def named_hook_kind(name: str) -> str:
    if name.startswith("pad-"):
        return "button"
    if name.startswith(("session-", "template-", "history-", "media-", "upcoming-", "calendar-")):
        return "item"
    if name in {"titleConnect", "confirmCancel", "confirmAccept", "analogPad", "previewHost", "livePane"}:
        return "hook"
    return ""


def is_interactive(obj: Any) -> bool:
    name = object_name_of(obj)
    if named_hook_kind(name):
        return True
    return bool(control_kind(obj))


def control_label(obj: Any) -> str:
    for key in ("accessibleName", "text", "placeholderText", "displayText"):
        value = _property(obj, key, None)
        if value not in (None, ""):
            return str(value)
    return object_name_of(obj)


def control_value(obj: Any) -> Any:
    kind = control_kind(obj)
    if kind == "combo":
        return _property(obj, "currentText", _property(obj, "displayText", ""))
    if kind == "spinbox":
        return _property(obj, "value", None)
    if kind == "check":
        return bool(_property(obj, "checked", False))
    if kind in {"field", "button", "menu"}:
        return _property(obj, "text", "")
    return None


def control_path(obj: Any) -> str:
    parts = [name for name in reversed(ancestor_names(obj)) if name]
    own = object_name_of(obj) or control_label(obj)
    if own:
        parts.append(own)
    return "/".join(parts)


def describe_control(obj: Any) -> dict[str, Any]:
    name = object_name_of(obj)
    kind = control_kind(obj) or named_hook_kind(name) or "item"
    return {
        "objectName": name,
        "name": control_label(obj) or name,
        "type": kind,
        "enabled": bool(_property(obj, "enabled", True)),
        "visible": is_visible_item(obj),
        "value": control_value(obj),
        "path": control_path(obj),
    }


def _is_mock(obj: Any) -> bool:
    return type(obj).__module__ == "unittest.mock"


def _iter_children(obj: Any) -> list[Any]:
    kids: list[Any] = []
    children_fn = getattr(obj, "children", None)
    if callable(children_fn) and not _is_mock(children_fn):
        kids.extend(list(children_fn() or []))
    child_items = getattr(obj, "childItems", None)
    if callable(child_items) and not _is_mock(child_items):
        try:
            kids.extend(list(child_items() or []))
        except Exception:
            pass
    content = _property(obj, "contentItem", None)
    if content is not None and content is not obj and not _is_mock(content):
        kids.append(content)
    return kids


def _qml_plain(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    to_variant = getattr(value, "toVariant", None)
    if callable(to_variant):
        try:
            return to_variant()
        except Exception:
            return value
    return value


def walk_objects(root: Any) -> list[Any]:
    found: list[Any] = []
    stack = [root]
    seen: set[int] = set()
    finder = getattr(root, "findChildren", None)
    if callable(finder) and not _is_mock(finder):
        try:
            from PySide6.QtCore import QObject

            extra = finder(QObject)
            if isinstance(extra, (list, tuple)):
                stack.extend(child for child in extra if child is not None and not _is_mock(child))
        except Exception:
            pass
    while stack:
        obj = stack.pop()
        if obj is None or id(obj) in seen or _is_mock(obj):
            continue
        seen.add(id(obj))
        found.append(obj)
        for child in reversed(_iter_children(obj)):
            stack.append(child)
    return found


def list_controls(root: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for obj in walk_objects(root):
        if should_skip_object(obj) or not is_visible_item(obj) or not is_interactive(obj):
            continue
        items.append(describe_control(obj))
        items[-1]["_obj"] = obj
    return items


def resolve_control(controls: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    text = str(query or "").strip()
    if not text:
        return None
    named = [item for item in controls if item.get("objectName") == text]
    if len(named) == 1:
        return named[0]
    if len(named) > 1:
        raise ValueError(f"ambiguous objectName {text}")
    labels = [item for item in controls if item.get("name") == text]
    if len(labels) == 1:
        return labels[0]
    if len(labels) > 1:
        raise ValueError(f"ambiguous name {text}")
    paths = [
        item
        for item in controls
        if item.get("path") == text or str(item.get("path") or "").endswith("/" + text)
    ]
    if len(paths) == 1:
        return paths[0]
    if len(paths) > 1:
        raise ValueError(f"ambiguous path {text}")
    lowered = text.lower()
    fuzzy = [
        item
        for item in controls
        if str(item.get("objectName") or "").lower() == lowered
        or str(item.get("name") or "").lower() == lowered
    ]
    if len(fuzzy) == 1:
        return fuzzy[0]
    return None


def _popup_open(root: Any, name: str) -> bool:
    menu = find_named(root, name)
    if menu is None:
        return False
    return bool(_property(menu, "opened", False))


def _spin_value(root: Any, name: str) -> Any:
    obj = find_named(root, name)
    if obj is None:
        return None
    value = _property(obj, "value", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def find_named(root: Any, name: str) -> Any | None:
    wanted = str(name or "")
    if not wanted:
        return None
    if object_name_of(root) == wanted:
        return root
    finder = getattr(root, "findChild", None)
    if callable(finder):
        try:
            from PySide6.QtCore import QObject

            child = finder(QObject, wanted)
            if child is not None:
                return child
        except Exception:
            pass
    prefix = None
    if wanted in {"upcoming", "calendar-sidebar", "session", "calendar-session"}:
        prefix = wanted + "-"
    for obj in walk_objects(root):
        name = object_name_of(obj)
        if name == wanted:
            return obj
        if prefix and name.startswith(prefix):
            return obj
    return None


def _item_window_pos(obj: Any, nx: float = 0.5, ny: float = 0.5) -> Any:
    from PySide6.QtCore import QPoint, QPointF

    width = float(_property(obj, "width", 0) or 0)
    height = float(_property(obj, "height", 0) or 0)
    mapper = getattr(obj, "mapToScene", None)
    if not callable(mapper):
        raise RuntimeError(f"{object_name_of(obj) or 'item'} cannot mapToScene")
    scene = mapper(QPointF(max(0.0, width * nx), max(0.0, height * ny)))
    return QPoint(int(round(scene.x())), int(round(scene.y())))


def _drag_trace(message: str) -> None:
    path = os.path.join(tempfile.gettempdir(), "astro-dwarf-drag.log")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{time.time():.3f} {message}\n")


def drag_item(obj: Any, dx: float = 0, dy: float = 80, steps: int = 8) -> dict[str, Any]:
    from PySide6.QtCore import Qt, QPoint
    from PySide6.QtTest import QTest

    window_fn = getattr(obj, "window", None)
    window = window_fn() if callable(window_fn) else window_fn
    if window is None:
        raise RuntimeError(f"{object_name_of(obj) or 'item'} has no window")
    activate = getattr(window, "requestActivate", None)
    if callable(activate):
        activate()
    start = _item_window_pos(obj)
    delay = 20
    _drag_trace(f"press {start.x()},{start.y()}")
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start, delay)
    _drag_trace("pressed")
    proxy = find_named(window, "sessionDragProxy")
    mouse_event = getattr(QTest, "mouseEvent", None)
    for index in range(1, max(1, int(steps)) + 1):
        pos = QPoint(
            start.x() + int(dx * index / steps),
            start.y() + int(dy * index / steps),
        )
        _drag_trace(f"move {pos.x()},{pos.y()}")
        if callable(mouse_event):
            mouse_event(QTest.MouseMove, window, Qt.LeftButton, Qt.NoModifier, pos, delay)
        else:
            QTest.mouseMove(window, pos, delay)
        _drag_trace(
            f"moved {index} proxy={bool(proxy.property('visible')) if proxy is not None else 'missing'}"
        )
    end = QPoint(start.x() + int(dx), start.y() + int(dy))
    _drag_trace(f"release {end.x()},{end.y()}")
    from PySide6.QtCore import QCoreApplication, QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    QCoreApplication.postEvent(
        window,
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(end),
            QPointF(end),
            Qt.LeftButton,
            Qt.MouseButtons(Qt.NoButton),
            Qt.NoModifier,
        ),
    )
    _drag_trace("posted release")
    return {
        "dragged": object_name_of(obj),
        "from": [start.x(), start.y()],
        "to": [end.x(), end.y()],
    }


def invoke_qml(obj: Any, name: str, *args: Any) -> Any:
    method = getattr(obj, name, None)
    if callable(method):
        return method(*args)
    raise AttributeError(name)


def _emit_or_call(obj: Any, name: str, *args: Any) -> bool:
    target = getattr(obj, name, None)
    if target is None:
        return False
    emit = getattr(target, "emit", None)
    if callable(emit):
        emit(*args)
        return True
    if callable(target):
        target(*args)
        return True
    return False


def pointer_click_object(
    obj: Any,
    *,
    double: bool = False,
    button: str = "left",
    nx: float = 0.5,
    ny: float = 0.5,
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    window_fn = getattr(obj, "window", None)
    window = window_fn() if callable(window_fn) else window_fn
    if window is None:
        raise RuntimeError(f"{object_name_of(obj) or control_label(obj)} has no window")
    activate = getattr(window, "requestActivate", None)
    if callable(activate):
        activate()
    pos = _item_window_pos(obj, nx, ny)
    qt_button = Qt.RightButton if str(button or "left").strip().lower() == "right" else Qt.LeftButton
    delay = 20
    QTest.mousePress(window, qt_button, Qt.NoModifier, pos, delay)
    QTest.mouseRelease(window, qt_button, Qt.NoModifier, pos, delay)
    if double:
        QTest.mousePress(window, qt_button, Qt.NoModifier, pos, delay)
        QTest.mouseRelease(window, qt_button, Qt.NoModifier, pos, delay)


def click_object(obj: Any) -> None:
    # MenuItem.click() emits clicked and leaves triggered alone, so the
    # item's onTriggered handler never runs. Fire triggered for menu rows.
    if _property(obj, "menu", None) is not None and _emit_or_call(obj, "triggered"):
        return
    click = getattr(obj, "click", None)
    if callable(click):
        try:
            click()
            return
        except Exception:
            pass
    if _emit_or_call(obj, "clicked"):
        return
    if _emit_or_call(obj, "triggered"):
        return
    pointer_click_object(obj)


def _combo_texts(obj: Any) -> list[str]:
    model = _property(obj, "model", None)
    texts: list[str] = []
    if model is None:
        return texts
    if isinstance(model, (list, tuple)):
        for item in model:
            if isinstance(item, dict):
                texts.append(str(item.get("name") or item.get("text") or item.get("label") or ""))
            else:
                texts.append(str(item))
        return texts
    count = _property(obj, "count", None)
    try:
        total = int(count)
    except (TypeError, ValueError):
        total = -1
    if total >= 0:
        at = getattr(obj, "textAt", None)
        if callable(at):
            return [str(at(index) or "") for index in range(total)]
    return [str(model)]


def set_object(obj: Any, value: Any) -> None:
    kind = control_kind(obj)
    if kind == "field":
        obj.setProperty("text", str(value))
        _emit_or_call(obj, "editingFinished")
        return
    if kind == "spinbox":
        number = int(float(value)) if str(value).strip() else 0
        obj.setProperty("value", number)
        _emit_or_call(obj, "valueModified")
        return
    if kind == "check":
        wanted = str(value).strip().lower() in {"1", "true", "yes", "on"}
        setter = getattr(obj, "setOn", None)
        if callable(setter):
            setter(wanted)
        else:
            obj.setProperty("checked", wanted)
        if bool(_property(obj, "checked", False)) != wanted:
            click_object(obj)
        return
    if kind == "combo":
        text = str(value)
        texts = _combo_texts(obj)
        index = next((i for i, item in enumerate(texts) if item == text), -1)
        if index < 0:
            index = next((i for i, item in enumerate(texts) if item.lower() == text.lower()), -1)
        if index < 0:
            try:
                index = int(text)
            except ValueError as exc:
                raise RuntimeError(f"combo has no option {text}") from exc
        obj.setProperty("currentIndex", index)
        _emit_or_call(obj, "activated", index)
        return
    raise RuntimeError(f"cannot set {kind or object_name_of(obj)}")


def item_summary(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": str(item or "")}
    keys = (
        "id",
        "name",
        "target_name",
        "target",
        "file_name",
        "status",
        "device_id",
        "device_name",
        "start_date",
        "start_time",
        "scheduled_start",
        "date",
        "kind",
        "is_dir",
        "outcome",
        "session_id",
        "has_session",
    )
    return {key: item[key] for key in keys if key in item}


class TestHarness:
    def __init__(self, application: Any, window: Any, backend: Any) -> None:
        from PySide6.QtCore import QObject, Qt, Signal, Slot

        class _Bridge(QObject):
            requested = Signal(object)

            @Slot(object)
            def run(self, item: Any) -> None:
                fn, box, done = item
                try:
                    box["value"] = fn()
                except Exception as exc:
                    box["error"] = exc
                    box["trace"] = traceback.format_exc()
                done.set()

        self.application = application
        self.window = window
        self.backend = backend
        self.last_toast: dict[str, Any] = {}
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.host = "127.0.0.1"
        self.port = harness_port()
        self._bridge = _Bridge()
        if application is not None:
            self._bridge.moveToThread(application.thread())
        self._bridge.requested.connect(self._bridge.run, Qt.QueuedConnection)
        toast = getattr(backend, "toast", None)
        connect = getattr(toast, "connect", None)
        if callable(connect):
            connect(self._on_toast)

    def _on_toast(self, message: str, level: str, detail: str, _meta: Any = None) -> None:
        self.last_toast = {
            "message": str(message or ""),
            "level": str(level or ""),
            "detail": str(detail or ""),
        }

    def start(self) -> str:
        handler = self._handler()
        self.server = ThreadingHTTPServer((self.host, self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="test-harness")
        self.thread.start()
        url = f"http://{self.host}:{self.port}"
        print(f"Test harness listening on {url}", flush=True)
        return url

    def stop(self) -> None:
        server = self.server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        self.server = None

    def refresh_window(self) -> Any:
        from PySide6.QtGui import QGuiApplication

        current = self.window
        try:
            if current is not None:
                current.property("visible")
                return current
        except RuntimeError:
            current = None
        for win in QGuiApplication.topLevelWindows():
            try:
                if object_name_of(win) == "astroWindow":
                    self.window = win
                    return win
            except RuntimeError:
                continue
        for win in QGuiApplication.topLevelWindows():
            try:
                win.property("currentPage")
                self.window = win
                return win
            except RuntimeError:
                continue
        if current is not None:
            self.window = current
            return current
        raise RuntimeError("app window is gone")

    def on_gui(self, fn: Any, timeout: float = 12.0) -> Any:
        from PySide6.QtCore import QCoreApplication, QThread

        def wrapped() -> Any:
            self.refresh_window()
            return fn()

        app = QCoreApplication.instance()
        if app is not None and QThread.currentThread() is app.thread():
            return wrapped()

        done = threading.Event()
        box: dict[str, Any] = {}
        self._bridge.requested.emit((wrapped, box, done))
        if not done.wait(timeout):
            raise TimeoutError("GUI thread did not handle the harness call")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def hooks(self) -> Any:
        return find_named(self.window, "testHarness")

    def call_hook(self, name: str, *args: Any) -> Any:
        hooks = self.hooks()
        if hooks is None:
            raise RuntimeError("testHarness QML object is missing")
        return invoke_qml(hooks, name, *args)

    def state(self) -> dict[str, Any]:
        backend = self.backend
        device = dict(getattr(backend, "selectedDevice", {}) or {})
        session = dict(getattr(backend, "currentSession", {}) or {})
        sky = dict(getattr(backend, "skyTarget", {}) or {})
        index = int(self.window.property("currentPage") or 0)
        ready = device_ready(device)
        can_power = ready and str(device.get("pending_action") or "") != "power_down"
        return {
            "page": page_name_from_index(index),
            "pageIndex": index,
            "device": {
                "id": str(getattr(backend, "selectedDeviceId", "") or device.get("id") or ""),
                "name": str(device.get("name") or ""),
                "ip": str(device.get("ip_address") or ""),
                "connected": bool(device.get("connected")),
                "connecting": bool(device.get("connecting")),
                "disconnecting": bool(device.get("disconnecting")),
                "cancelling": bool(device.get("cancelling")),
                "busy": bool(device.get("busy")),
                "pending": str(device.get("pending_action") or ""),
                "activity": str(device.get("activity") or ""),
                "status": str(device.get("status") or ""),
                "ready": ready,
            },
            "can": {
                "power_down": can_power,
                "reboot": can_power,
                "calibrate": ready and str(device.get("activity") or "") != "calibrate",
            },
            "preview": {
                "active": bool(getattr(backend, "previewActive", False)),
                "playing": bool(getattr(backend, "previewPlaying", False)),
                "tele": bool(getattr(backend, "previewTelePlaying", False)),
                "wide": bool(getattr(backend, "previewWidePlaying", False)),
                "status": str(getattr(backend, "previewStatus", "") or ""),
                "tele_match_nx": (device.get("telemetry") or {}).get("tele_match_nx"),
                "tele_match_ny": (device.get("telemetry") or {}).get("tele_match_ny"),
                "tele_match_nw": (device.get("telemetry") or {}).get("tele_match_nw"),
                "tele_match_nh": (device.get("telemetry") or {}).get("tele_match_nh"),
            },
            "session": {
                "id": str(session.get("id") or ""),
                "name": str(session.get("target_name") or session.get("name") or ""),
                "status": str(session.get("status") or ""),
            },
            "sky": {
                "name": str(sky.get("name") or ""),
                "locked": bool(sky.get("locked")),
                "ra_hours": sky.get("ra_hours"),
                "dec_degrees": sky.get("dec_degrees"),
                "provider": str(getattr(backend, "skyMapProvider", "") or ""),
            },
            "toast": dict(self.last_toast),
            "menus": {
                "session": _popup_open(self.window, "sessionContextMenu"),
                "sky": _popup_open(self.window, "skyContextMenu"),
            },
            "sky_grid": {
                "columns": _spin_value(self.window, "skyColumns"),
                "rows": _spin_value(self.window, "skyRows"),
                "overlap": _spin_value(self.window, "skyOverlap"),
                "pa": _spin_value(self.window, "skyPa"),
            },
            "media": {
                "source": str(getattr(backend, "mediaSource", "") or ""),
                "folder": str(getattr(backend, "mediaFolder", "") or ""),
                "folders": [
                    str(item.get("name") or "")
                    for item in (getattr(backend, "mediaRootFolders", []) or [])
                    if isinstance(item, dict)
                ],
            },
        }

    def controls(self) -> list[dict[str, Any]]:
        items = []
        seen: set[str] = set()
        for item in list_controls(self.window):
            row = {key: value for key, value in item.items() if key != "_obj"}
            key = str(row.get("objectName") or row.get("path") or row.get("name") or "")
            if key:
                seen.add(key)
            items.append(row)
        try:
            extra = _qml_plain(self.call_hook("padList")) or []
        except Exception:
            extra = []
        if not isinstance(extra, list):
            extra = []
        for row in extra:
            row = _qml_plain(row)
            if not isinstance(row, dict):
                continue
            name = str(row.get("objectName") or "")
            if name and name in seen:
                continue
            if name:
                seen.add(name)
            items.append(dict(row))
        return items

    def _resolved(self, query: str) -> Any:
        controls = list_controls(self.window)
        match = resolve_control(controls, query)
        if match is None:
            raise RuntimeError(f"control not found: {query}")
        return match["_obj"]

    def click(self, query: str, double: bool = False, button: str = "left", nx: float = 0.5, ny: float = 0.5) -> dict[str, Any]:
        start = pad_start_from_query(query)
        if start and not double and str(button or "left").strip().lower() != "right":
            try:
                result = self.call_hook("clickPad", start)
            except Exception:
                result = "missing"
            if result and result != "missing":
                return {"clicked": query, "via": "pad", "pad": result}
        try:
            obj = self._resolved(query)
        except RuntimeError:
            obj = find_named(self.window, query)
            if obj is None and str(button or "left").strip().lower() != "right":
                raise
        if str(button or "left").strip().lower() == "right" and not double:
            via = self._click_fallbacks(query, double=double, button=button, ny=ny)
            if via == "menu":
                return {"clicked": query, "double": False, "button": "right", "via": via}
            if obj is None:
                raise RuntimeError(f"control not found: {query}")
        if double or str(button or "left").strip().lower() == "right":
            try:
                pointer_click_object(obj, double=double, button=button, nx=nx, ny=ny)
            except Exception:
                pass
            via = self._click_fallbacks(query, double=double, button=button, ny=ny)
            return {"clicked": query, "double": bool(double), "button": str(button or "left"), "via": via}
        click_object(obj)
        return {"clicked": query}

    def _click_fallbacks(self, query: str, *, double: bool, button: str, ny: float) -> str:
        name = str(query or "")
        if double and name.startswith("calendar-day-"):
            page = find_named(self.window, "calendarPage")
            if page is not None and int(_property(page, "viewMode", 0) or 0) != 1:
                invoke_qml(page, "openNight", name[len("calendar-day-"):])
                return "openNight"
            return "pointer"
        if double and name == "nightTimelineTrack":
            dialog = find_named(self.window, "sessionDialog")
            if dialog is None or not bool(_property(dialog, "visible", False)):
                page = find_named(self.window, "calendarPage")
                if page is not None:
                    minutes = max(0, min(1439, int(round(1440 * float(ny)))))
                    invoke_qml(page, "createSessionAtMinutes", minutes)
                    return "createSession"
            return "pointer"
        if str(button or "left").strip().lower() == "right" and name == "pageNavBar":
            menu = find_named(self.window, "navBarPlacementMenu")
            popup = getattr(menu, "popup", None) if menu is not None else None
            if callable(popup):
                popup()
                return "menu"
        if str(button or "left").strip().lower() == "right" and name.startswith("session-"):
            if self._open_session_menu(name[len("session-") :]):
                return "menu"
        if str(button or "left").strip().lower() == "right" and name == "skyPage":
            page = find_named(self.window, "skyPage")
            if page is not None:
                try:
                    width = float(_property(page, "width", 0) or 0)
                    height = float(_property(page, "height", 0) or 0)
                    invoke_qml(page, "openSkyMenu", width * 0.5, height * 0.55)
                except Exception:
                    return "pointer"
                return "menu"
        return "pointer"

    def _open_session_menu(self, session_id: str) -> bool:
        page = find_named(self.window, "sessionsPage")
        if page is None:
            return False
        try:
            result = invoke_qml(page, "openListedSessionMenu", str(session_id or ""))
        except Exception:
            return False
        return str(result or "") == "open"

    def drag(self, query: str, dx: float = 0, dy: float = 80, mode: str = "pointer") -> dict[str, Any]:
        _drag_trace(f"drag query={query} mode={mode}")
        kind = str(mode or "pointer").strip().lower()
        if kind in {"coordinator", "start", "reorder"}:
            ident = str(query or "")
            if ident.startswith("upcoming-"):
                ident = ident[len("upcoming-"):]
            elif ident in {"upcoming", "calendar-sidebar", "session"}:
                rows = self.items("upcoming" if ident == "upcoming" else "sessions")
                if not rows:
                    raise RuntimeError(f"no {ident} sessions")
                ident = str(rows[0].get("id") or "")
            phase = "start" if kind == "start" else ("reorder" if kind == "reorder" else "all")
            result = self.call_hook("sessionDrag", ident, phase, dx, dy)
            return {"dragged": query, "via": "coordinator", "result": str(result), "phase": phase, "id": ident}
        obj = find_named(self.window, query)
        _drag_trace(f"found {object_name_of(obj) if obj is not None else 'none'}")
        if obj is None:
            obj = self._resolved(query)
        result = drag_item(obj, dx, dy)
        result["query"] = query
        return result

    def set_value(self, query: str, value: Any) -> dict[str, Any]:
        key = str(query or "").strip()
        if key in {"sky_map_provider", "skyMapProvider"}:
            setter = getattr(self.backend, "setSkyMapProvider", None)
            if not callable(setter):
                raise RuntimeError("sky map provider is not available")
            setter(str(value or ""))
            return {"set": key, "value": str(getattr(self.backend, "skyMapProvider", "") or "")}
        set_object(self._resolved(query), value)
        return {"set": query, "value": value}

    def go_to_page(self, name: str) -> dict[str, Any]:
        index = page_index_from_name(name)
        if index is None:
            raise RuntimeError("settings page is out of harness scope")
        self.call_hook("goToNamedPage", page_name_from_index(index))
        return {"page": page_name_from_index(index)}

    def snapshot(self) -> dict[str, Any]:
        grab = getattr(self.window, "grabWindow", None)
        if not callable(grab):
            raise RuntimeError("window does not support grabWindow")
        image = grab()
        path = os.path.join(tempfile.gettempdir(), "astro-dwarf-harness.png")
        if not image.save(path):
            raise RuntimeError("could not write snapshot")
        return {"path": path}

    def connect_device(self, ip: str = "", device_id: str = "") -> dict[str, Any]:
        target_ip = str(ip or LAB_DEVICE_IP).strip()
        device = None
        if device_id:
            for item in getattr(self.backend, "devices", []) or []:
                if isinstance(item, dict) and str(item.get("id") or "") == str(device_id):
                    device = item
                    break
        if device is None:
            device = device_by_ip(getattr(self.backend, "devices", []), target_ip)
        if device is None:
            raise RuntimeError(f"no device at {target_ip}")
        ident = str(device.get("id") or "")
        if str(getattr(self.backend, "selectedDeviceId", "") or "") != ident:
            self.backend.selectDevice(ident)
        current = dict(getattr(self.backend, "selectedDevice", {}) or {})
        if current.get("connecting"):
            self.backend.cancelConnect(ident)
            return {"id": ident, "action": "cancel"}
        if current.get("connected"):
            return {"id": ident, "action": "already-connected"}
        self.backend.connectDevice(ident)
        return {"id": ident, "ip": str(device.get("ip_address") or target_ip), "action": "connect"}

    def items(self, kind: str) -> list[dict[str, Any]]:
        mapping = {
            "sessions": "sessions",
            "upcoming": "upcomingSessions",
            "templates": "templates",
            "history": "history",
            "media": "mediaItems",
            "calendar": "sessions",
        }
        attr = mapping.get(str(kind or "").strip().lower())
        if not attr:
            raise RuntimeError(f"unknown item kind {kind}")
        rows = getattr(self.backend, attr, []) or []
        return [item_summary(row) for row in rows]

    def handle(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        parsed = urlparse(path)
        route = parsed.path.rstrip("/") or "/"
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        payload = dict(body or {})

        def work() -> dict[str, Any]:
            if method == "GET" and route == "/state":
                return self.state()
            if method == "GET" and route == "/controls":
                return {"controls": self.controls()}
            if method == "GET" and route == "/items":
                return {"items": self.items(str(query.get("kind") or payload.get("kind") or "sessions"))}
            if method == "POST" and route == "/click":
                return self.click(
                    str(payload.get("name") or payload.get("path") or ""),
                    bool(payload.get("double")),
                    str(payload.get("button") or "left"),
                    float(payload.get("nx") if payload.get("nx") is not None else 0.5),
                    float(payload.get("ny") if payload.get("ny") is not None else 0.5),
                )
            if method == "POST" and route == "/drag":
                return self.drag(
                    str(payload.get("name") or payload.get("path") or ""),
                    float(payload.get("dx") or 0),
                    float(payload.get("dy") if payload.get("dy") is not None else 80),
                    str(payload.get("mode") or "pointer"),
                )
            if method == "POST" and route == "/set":
                return self.set_value(str(payload.get("name") or payload.get("path") or ""), payload.get("value"))
            if method == "POST" and route == "/page":
                return self.go_to_page(str(payload.get("page") or payload.get("name") or ""))
            if method == "POST" and route == "/snapshot":
                return self.snapshot()
            if method == "POST" and route == "/window/maximize":
                maximize_window(self.window)
                return {"action": "maximize"}
            if method == "POST" and route == "/window/resize":
                show = getattr(self.window, "showNormal", None)
                if callable(show):
                    show()
                width = int(payload.get("width") or _property(self.window, "minimumWidth", 1040) or 1040)
                height = int(payload.get("height") or _property(self.window, "minimumHeight", 620) or 620)
                resize = getattr(self.window, "resize", None)
                if not callable(resize):
                    raise RuntimeError("window does not support resize")
                resize(width, height)
                return {
                    "width": int(_property(self.window, "width", width) or width),
                    "height": int(_property(self.window, "height", height) or height),
                }
            if method == "POST" and route == "/device/action":
                operation = str(payload.get("operation") or payload.get("name") or "")
                label = str(payload.get("label") or operation)
                result = self.call_hook("requestAction", operation, label)
                return {"operation": operation, "result": result}
            if method == "POST" and route == "/device/connect":
                return self.connect_device(str(payload.get("ip") or ""), str(payload.get("id") or ""))
            if method == "POST" and route == "/device/disconnect":
                self.call_hook("disconnectSelected")
                return {"action": "disconnect"}
            if method == "POST" and route == "/device/cancel":
                self.call_hook("cancelConnectSelected")
                return {"action": "cancel"}
            if method == "POST" and route == "/device/select":
                ident = str(payload.get("id") or "")
                ip = str(payload.get("ip") or "")
                if not ident and ip:
                    device = device_by_ip(getattr(self.backend, "devices", []), ip)
                    ident = str((device or {}).get("id") or "")
                if not ident:
                    raise RuntimeError("device id or ip required")
                self.call_hook("selectById", ident)
                return {"id": ident}
            if method == "POST" and route == "/preview/center":
                nx = float(payload.get("nx", 0.5))
                ny = float(payload.get("ny", 0.5))
                self.call_hook("centerPreview", nx, ny)
                return {"nx": nx, "ny": ny}
            if method == "POST" and route == "/joystick/nudge":
                angle = float(payload.get("angle", 0))
                self.call_hook("joystickNudge", angle)
                return {"angle": angle}
            if method == "POST" and route == "/items/open":
                kind = str(payload.get("kind") or "sessions")
                ident = str(payload.get("id") or "")
                action = str(payload.get("action") or "edit")
                result = self.call_hook("openItem", kind, ident, action)
                return {"kind": kind, "id": ident, "action": action, "result": result}
            if method == "POST" and route == "/items/delete":
                kind = str(payload.get("kind") or "sessions")
                ident = str(payload.get("id") or "")
                result = self.call_hook("deleteItem", kind, ident)
                return {"kind": kind, "id": ident, "result": result}
            if method == "POST" and route == "/items/run":
                kind = str(payload.get("kind") or "sessions")
                ident = str(payload.get("id") or "")
                result = self.call_hook("runItem", kind, ident)
                return {"kind": kind, "id": ident, "result": result}
            if method == "POST" and route == "/sky/harvest":
                action = str(payload.get("action") or "import")
                result = self.call_hook("skyHarvest", action)
                return {"action": action, "result": result}
            if method == "POST" and route == "/sky/view":
                ra = float(payload.get("ra_hours", 0))
                dec = float(payload.get("dec_degrees", 0))
                result = self.call_hook("skyView", ra, dec)
                return {"ra_hours": ra, "dec_degrees": dec, "result": result}
            if method == "POST" and route == "/sky/lock":
                result = self.call_hook(
                    "skyLock",
                    str(payload.get("name") or ""),
                    float(payload.get("ra_hours", 0)),
                    float(payload.get("dec_degrees", 0)),
                )
                return {"result": result}
            if method == "POST" and route == "/sky/menu":
                action = str(payload.get("action") or "")
                result = self.call_hook("skyMenu", action)
                return {"action": action, "result": result}
            if method == "POST" and route == "/sky/eval":
                script = str(payload.get("script") or payload.get("js") or "")
                started = self.call_hook("skyEval", script)
                hooks = self.hooks()
                deadline = time.monotonic() + 4.0
                from PySide6.QtCore import QCoreApplication, QEventLoop

                while time.monotonic() < deadline:
                    if bool(hooks.property("skyEvalDone")):
                        break
                    QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
                return {
                    "started": started,
                    "done": bool(hooks.property("skyEvalDone")),
                    "result": str(hooks.property("skyEvalResult") or ""),
                }
            if method == "POST" and route == "/confirm":
                action = str(payload.get("action") or "accept")
                result = self.call_hook("confirmAction", action)
                return {"action": action, "result": result}
            raise RuntimeError(f"unknown {method} {route}")

        return self.on_gui(work)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        harness = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def _read_body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                if not raw:
                    return {}
                data = json.loads(raw.decode("utf-8"))
                return data if isinstance(data, dict) else {}

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                blob = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

            def do_GET(self) -> None:
                self._dispatch("GET")

            def do_POST(self) -> None:
                self._dispatch("POST")

            def _dispatch(self, method: str) -> None:
                try:
                    body = self._read_body() if method == "POST" else {}
                    payload = harness.handle(method, self.path, body)
                    payload.setdefault("ok", True)
                    self._send(200, payload)
                except Exception as exc:
                    self._send(400, {"ok": False, "error": str(exc)})

        return Handler


def maximize_window(window: Any) -> None:
    show = getattr(window, "showMaximized", None)
    if callable(show):
        show()
    activate = getattr(window, "requestActivate", None)
    if callable(activate):
        activate()
    raise_fn = getattr(window, "raise_", None)
    if callable(raise_fn):
        raise_fn()


def start_test_harness(application: Any, window: Any, backend: Any) -> TestHarness:
    from PySide6.QtCore import QTimer

    harness = TestHarness(application, window, backend)
    harness.start()
    QTimer.singleShot(0, lambda: maximize_window(window))
    quit_signal = getattr(application, "aboutToQuit", None)
    connect = getattr(quit_signal, "connect", None)
    if callable(connect):
        connect(harness.stop)
    setattr(application, "_test_harness", harness)
    return harness
