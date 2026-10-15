from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.test_harness import (
    LAB_DEVICE_IP,
    TestHarness,
    device_by_ip,
    device_ready,
    harness_enabled,
    harness_port,
    find_named,
    list_controls,
    pad_start_from_query,
    page_index_from_name,
    page_name_from_index,
    resolve_control,
    should_skip_names,
    should_skip_object,
    walk_objects,
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class Node:
    def __init__(self, name: str = "", parent: Node | None = None, **props):
        self._name = name
        self._parent = parent
        self._children: list[Node] = []
        self._props = dict(props)
        if parent is not None:
            parent._children.append(self)

    def objectName(self) -> str:
        return self._name

    def parent(self) -> Node | None:
        return self._parent

    def children(self) -> list[Node]:
        return list(self._children)

    def childItems(self) -> list[Node]:
        return list(self._children)

    def property(self, name: str) -> object:
        return self._props.get(name)

    def setProperty(self, name: str, value: object) -> None:
        self._props[name] = value


class Button(Node):
    def __init__(self, name: str = "", parent: Node | None = None, **props):
        props.setdefault("visible", True)
        props.setdefault("enabled", True)
        props.setdefault("text", name or "Button")
        super().__init__(name, parent, **props)
        self.clicked = False

    def click(self) -> None:
        self.clicked = True


def test_harness_enabled() -> None:
    _assert(harness_enabled({"ASTRO_DWARF_TEST_HARNESS": "1"}) is True, "env on")
    _assert(harness_enabled({"ASTRO_DWARF_TEST_HARNESS": "1"}, frozen=True) is False, "frozen off")
    _assert(harness_enabled({}) is False, "default off")
    _assert(harness_port({"ASTRO_DWARF_TEST_HARNESS_PORT": "9001"}) == 9001, "port override")
    _assert(harness_port({}) == 8765, "default port")


def test_device_ready_ignores_preview() -> None:
    _assert(device_ready({"connected": True}) is True, "connected is ready")
    _assert(device_ready({"connected": True, "connecting": False}) is True, "idle link")
    _assert(device_ready({"connected": False}) is False, "offline")
    _assert(device_ready({"connected": True, "connecting": True}) is False, "still linking")
    _assert(device_ready({"connected": True, "disconnecting": True}) is False, "dropping")


def test_device_by_ip() -> None:
    devices = [
        {"id": "other", "ip_address": "192.168.1.10"},
        {"id": "lab", "ip_address": "192.168.1.42"},
    ]
    found = device_by_ip(devices)
    _assert(found is not None and found["id"] == "lab", "default lab IP")
    _assert(device_by_ip(devices, "10.0.0.1") is None, "missing IP")
    _assert(device_by_ip(devices, LAB_DEVICE_IP)["id"] == "lab", "explicit lab IP")


def test_page_mapping() -> None:
    _assert(page_name_from_index(0) == "control", "control page")
    _assert(page_name_from_index(5) == "sky", "sky page")
    _assert(page_index_from_name("media") == 4, "media index")
    _assert(page_index_from_name("settings") is None, "settings blocked")
    _assert(page_index_from_name("6") is None, "settings index blocked")


def test_skip_settings_and_layout() -> None:
    _assert(should_skip_names("settingsPage", []) is True, "settings root")
    _assert(should_skip_names("ipField", ["astroWindow", "settingsPage"]) is True, "settings child")
    _assert(should_skip_names("panelDrag-status", []) is True, "panel drag")
    _assert(should_skip_names("panelEdge-preview", []) is True, "panel edge")
    _assert(should_skip_names("splitHandle", []) is True, "split handle")
    _assert(should_skip_names("layoutResetMenu-status", []) is True, "layout menu")
    _assert(should_skip_names("titleConnect", ["astroWindow"]) is False, "title connect kept")


def test_tree_walk_and_resolve() -> None:
    root = Node("astroWindow", visible=True)
    settings = Node("settingsPage", root, visible=True)
    Button("secretSetting", settings, text="SAVE")
    Node("panelDrag-status", root, visible=True)
    connect = Button("titleConnect", root, text="CONNECT")
    pad = Button("pad-stack", root, text="MOSAIC STACK")
    session = Node("session-abc", root, visible=True, text="")
    edit = Button("", session, text="EDIT")

    _assert(should_skip_object(settings) is True, "skip settings node")
    controls = list_controls(root)
    names = {item["objectName"] or item["name"] for item in controls}
    _assert("titleConnect" in names, "connect listed")
    _assert("pad-stack" in names, "pad listed")
    _assert("secretSetting" not in names, "settings control hidden")
    _assert("panelDrag-status" not in names, "layout chrome hidden")

    match = resolve_control(controls, "titleConnect")
    _assert(match is not None and match["objectName"] == "titleConnect", "resolve objectName")
    match = resolve_control(controls, "CONNECT")
    _assert(match is not None and match["_obj"] is connect, "resolve label")
    match = resolve_control(controls, "session-abc/EDIT")
    _assert(match is not None and match["_obj"] is edit, "resolve path")
    pad_match = resolve_control(controls, "pad-stack")
    _assert(pad_match is not None and pad_match["_obj"] is pad, "resolve pad")
    prefix = find_named(root, "session")
    _assert(prefix is session, "find_named matches session- prefix")


def test_gui_thread_marshal() -> None:
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    backend = MagicMock()
    backend.toast = MagicMock()
    backend.toast.connect = MagicMock()
    window = MagicMock()
    harness = TestHarness(app, window, backend)
    marker = {"ran": False}

    def work() -> str:
        marker["ran"] = True
        return "ok"

    result = harness.on_gui(work, timeout=5)
    _assert(result == "ok", "same-thread marshal runs inline")
    _assert(marker["ran"] is True, "work ran")

    posted = {"ran": False}

    def other() -> str:
        posted["ran"] = True
        return "bg"

    def worker() -> None:
        posted["result"] = harness.on_gui(other, timeout=5)

    thread = threading.Thread(target=worker)
    thread.start()
    deadline = time.monotonic() + 5
    while thread.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    thread.join(1)
    _assert(posted.get("result") == "bg", "background thread marshals onto GUI")
    _assert(posted["ran"] is True, "posted work ran")


def test_pad_query_aliases() -> None:
    _assert(pad_start_from_query("POWER") == "power_down", "POWER label")
    _assert(pad_start_from_query("pad-calibrate") == "calibrate", "objectName")
    _assert(pad_start_from_query("CALIBRATE") == "calibrate", "CALIBRATE label")
    _assert(pad_start_from_query("MOSAIC STACK") == "stack", "mosaic label")
    _assert(pad_start_from_query("PHOTO") is None, "PHOTO stays a mode button")
    _assert(pad_start_from_query("pad-photo") == "photo", "explicit photo pad")
    _assert(pad_start_from_query("CONNECT") is None, "non-pad label")
    _assert(pad_start_from_query("pad-stack-stop") == "stack-stop", "stack stop chip")
    _assert(pad_start_from_query("pad-track-stop") == "track-stop", "track stop chip")


def test_walk_includes_child_items() -> None:
    root = Node("astroWindow", visible=True)

    class VisualOnly:
        def __init__(self) -> None:
            self._kids = []

        def children(self) -> list:
            return []

        def childItems(self) -> list:
            return list(self._kids)

        def objectName(self) -> str:
            return "visualHost"

        def parent(self):
            return root

        def property(self, name: str) -> object:
            return True if name == "visible" else None

    host = VisualOnly()
    pad = Button("pad-power_down", None, text="POWER")
    pad._parent = host
    host._kids.append(pad)
    root._children.append(host)
    names = {obj.objectName() for obj in walk_objects(root) if hasattr(obj, "objectName")}
    _assert("pad-power_down" in names, "childItems reached the pad")


def test_click_uses_pad_hook_then_tree() -> None:
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    backend = MagicMock()
    backend.toast = MagicMock()
    backend.toast.connect = MagicMock()

    hooks = MagicMock()
    hooks.objectName = MagicMock(return_value="testHarness")
    hooks.padList = MagicMock(
        return_value=[
            {
                "objectName": "pad-power_down",
                "name": "POWER",
                "type": "button",
                "enabled": True,
                "visible": True,
                "value": "POWER",
                "path": "controlPage/pad-power_down",
            }
        ]
    )
    hooks.clickPad = MagicMock(return_value="pad-power_down")

    window = Node("astroWindow", visible=True)
    window.findChild = lambda *_args, **_kwargs: hooks
    harness = TestHarness(app, window, backend)

    clicked = harness.click("POWER")
    _assert(clicked["via"] == "pad", "POWER uses clickPad")
    hooks.clickPad.assert_called_with("power_down")

    names = {item["objectName"] for item in harness.controls()}
    _assert("pad-power_down" in names, "padList merged into controls")

    hooks.clickPad.return_value = "missing"
    pad = Button("pad-calibrate", window, text="CALIBRATE")
    tree = harness.click("pad-calibrate")
    _assert(tree == {"clicked": "pad-calibrate"}, "missing hook falls back to tree")
    _assert(pad.clicked is True, "tree click reached the pad")


def test_route_lookup_keeps_each_parser() -> None:
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    backend = MagicMock()
    backend.toast = MagicMock()
    backend.toast.connect = MagicMock()
    backend.devices = [{"id": "lab", "ip_address": "192.168.1.42"}]
    window = Node("astroWindow", visible=True, currentPage=0)

    class SizedWindow(Node):
        def __init__(self) -> None:
            super().__init__("astroWindow", visible=True, currentPage=0, width=800, height=600)
            self.resized: tuple[int, int] | None = None
            self.normal = False

        def showNormal(self) -> None:
            self.normal = True

        def resize(self, width: int, height: int) -> None:
            self.resized = (width, height)

    sized = SizedWindow()
    harness = TestHarness(app, window, backend)
    calls: list[tuple[object, ...]] = []

    def call_hook(name: str, *args: object) -> str:
        calls.append((name, args))
        return f"r:{name}"

    harness.call_hook = call_hook
    harness.state = lambda: {"page": "control"}
    harness.controls = lambda: [{"name": "pad"}]
    harness.items = lambda kind: [{"kind": kind}]
    harness.click = lambda *args: {"click": args}
    harness.drag = lambda *args: {"drag": args}
    harness.set_value = lambda *args: {"set": args}
    harness.go_to_page = lambda name: {"page": name}
    harness.snapshot = lambda: {"path": "snap.png"}
    harness.connect_device = lambda ip, ident: {"ip": ip, "id": ident, "action": "connect"}

    class EvalHooks:
        def property(self, name: str) -> object:
            if name == "skyEvalDone":
                return True
            if name == "skyEvalResult":
                return "3"
            return None

    harness.hooks = lambda: EvalHooks()

    _assert(harness.handle("GET", "/state/", {}) == {"page": "control"}, "state route")
    _assert(harness.handle("GET", "/controls", {}) == {"controls": [{"name": "pad"}]}, "controls route")
    _assert(
        harness.handle("GET", "/items?kind=media&kind=history", {}) == {"items": [{"kind": "history"}]},
        "items uses the last query value",
    )
    _assert(harness.handle("GET", "/items", {"kind": "templates"}) == {"items": [{"kind": "templates"}]}, "items body")
    _assert(
        harness.handle("POST", "/click", {"path": "POWER", "nx": None, "double": 1})
        == {"click": ("POWER", True, "left", 0.5, 0.5)},
        "click keeps a missing nx at 0.5",
    )
    _assert(
        harness.handle("POST", "/drag", {"name": "slider", "dx": 0, "dy": None})
        == {"drag": ("slider", 0.0, 80.0, "pointer")},
        "drag default dy",
    )
    _assert(
        harness.handle("POST", "/drag", {"name": "slider", "dy": 0, "mode": "wheel"})
        == {"drag": ("slider", 0.0, 0.0, "wheel")},
        "explicit zero dy",
    )
    _assert(harness.handle("POST", "/set", {"name": "gain", "value": 40}) == {"set": ("gain", 40)}, "set route")
    _assert(harness.handle("POST", "/page", {"name": "sky"}) == {"page": "sky"}, "page name fallback")
    _assert(harness.handle("POST", "/snapshot", {}) == {"path": "snap.png"}, "snapshot route")
    _assert(harness.handle("POST", "/window/maximize", {}) == {"action": "maximize"}, "maximize route")

    harness.window = sized
    resized = harness.handle("POST", "/window/resize", {"width": 900})
    _assert(sized.normal is True, "resize shows normal")
    _assert(sized.resized == (900, 620), "resize fills height from the minimum")
    _assert(resized == {"width": 800, "height": 600}, "resize reports the window size")

    framed = harness.handle("POST", "/panorama/frame", {"x1": 0.1, "y2": 0.4})
    _assert(framed == {"ok": True, "x1": 0.1, "y1": 0.0, "x2": 1.0, "y2": 0.4}, "panorama defaults")
    backend.updatePanoramaFrame.assert_called_with(0.1, 0.0, 1.0, 0.4)

    action = harness.handle("POST", "/device/action", {"name": "track"})
    _assert(action == {"operation": "track", "result": "r:requestAction"}, "action route")
    _assert(calls[-1] == ("requestAction", ("track", "track")), "action label defaults to the operation")
    _assert(
        harness.handle("POST", "/device/connect", {"ip": "192.168.1.42"})
        == {"ip": "192.168.1.42", "id": "", "action": "connect"},
        "connect route",
    )
    _assert(harness.handle("POST", "/device/disconnect", {}) == {"action": "disconnect"}, "disconnect route")
    _assert(calls[-1] == ("disconnectSelected", ()), "disconnect hook")
    _assert(harness.handle("POST", "/device/cancel", {}) == {"action": "cancel"}, "cancel route")
    _assert(harness.handle("POST", "/device/select", {"ip": "192.168.1.42"}) == {"id": "lab"}, "select by ip")
    _assert(calls[-1] == ("selectById", ("lab",)), "select hook")
    try:
        harness.handle("POST", "/device/select", {})
        missing = False
    except RuntimeError as exc:
        missing = "device id or ip required" in str(exc)
    _assert(missing, "select requires an id")
    _assert(harness.handle("POST", "/preview/center", {}) == {"nx": 0.5, "ny": 0.5}, "center defaults")
    _assert(calls[-1] == ("centerPreview", (0.5, 0.5)), "center hook")
    _assert(harness.handle("POST", "/joystick/nudge", {"angle": 90}) == {"angle": 90.0}, "nudge route")
    opened = harness.handle("POST", "/items/open", {"id": "s1"})
    _assert(opened == {"kind": "sessions", "id": "s1", "action": "edit", "result": "r:openItem"}, "open defaults")
    deleted = harness.handle("POST", "/items/delete", {"kind": "history", "id": "h1"})
    _assert(deleted == {"kind": "history", "id": "h1", "result": "r:deleteItem"}, "delete route")
    ran = harness.handle("POST", "/items/run", {"id": "s1"})
    _assert(ran == {"kind": "sessions", "id": "s1", "result": "r:runItem"}, "run route")
    _assert(
        harness.handle("POST", "/sky/harvest", {}) == {"action": "import", "result": "r:skyHarvest"},
        "harvest default",
    )
    viewed = harness.handle("POST", "/sky/view", {"ra_hours": 5.5, "dec_degrees": -30})
    _assert(viewed["ra_hours"] == 5.5 and viewed["dec_degrees"] == -30.0 and viewed["result"] == "r:skyView", "view route")
    _assert(harness.handle("POST", "/sky/lock", {"name": "M42"}) == {"result": "r:skyLock"}, "lock route")
    _assert(calls[-1] == ("skyLock", ("M42", 0.0, 0.0)), "lock defaults")
    _assert(harness.handle("POST", "/sky/menu", {"action": "goto"}) == {"action": "goto", "result": "r:skyMenu"}, "menu route")
    _assert(harness.handle("POST", "/sky/grid", {"columns": 0, "rows": 2}) == {"result": "r:skyGrid"}, "grid route")
    _assert(calls[-1] == ("skyGrid", (1, 2)), "zero columns falls through to 1")
    evaluated = harness.handle("POST", "/sky/eval", {"js": "1+2"})
    _assert(evaluated == {"started": "r:skyEval", "done": True, "result": "3"}, "eval route")
    _assert(calls[-1] == ("skyEval", ("1+2",)), "eval prefers js when script is empty")
    _assert(harness.handle("POST", "/confirm", {}) == {"action": "accept", "result": "r:confirmAction"}, "confirm default")
    try:
        harness.handle("PUT", "/state", {})
        unknown = False
    except RuntimeError as exc:
        unknown = str(exc) == "unknown PUT /state"
    _assert(unknown, "unknown route")


def test_connect_by_ip_helper_on_harness() -> None:
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    backend = MagicMock()
    backend.toast = MagicMock()
    backend.toast.connect = MagicMock()
    backend.devices = [{"id": "lab", "ip_address": "192.168.1.42", "connected": False}]
    backend.selectedDeviceId = "other"
    backend.selectedDevice = {"id": "other", "connected": False, "connecting": False}
    window = MagicMock()
    harness = TestHarness(app, window, backend)
    result = harness.connect_device()
    _assert(result["id"] == "lab", "selects lab device")
    backend.selectDevice.assert_called_with("lab")
    backend.connectDevice.assert_called_with("lab")


if __name__ == "__main__":
    test_harness_enabled()
    test_device_ready_ignores_preview()
    test_device_by_ip()
    test_page_mapping()
    test_skip_settings_and_layout()
    test_tree_walk_and_resolve()
    test_gui_thread_marshal()
    test_pad_query_aliases()
    test_walk_includes_child_items()
    test_click_uses_pad_hook_then_tree()
    test_route_lookup_keeps_each_parser()
    test_connect_by_ip_helper_on_harness()
    print("test_test_harness ok")
