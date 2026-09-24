"""Time HUD page switches against a seeded scale library.

Expects the app already listening on 127.0.0.1:8765. Prints one JSON object
per step: name, milliseconds, ok, and a short error when the call fails.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
BUDGET_MS = 1000


def request(method: str, path: str, body: dict | None = None, timeout: float = 60) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        error = ""
        ok = bool(payload.get("ok", True))
    except Exception as exc:
        payload = {}
        error = str(exc)
        ok = False
    elapsed = int((time.perf_counter() - started) * 1000)
    row = {"step": path, "ms": elapsed, "ok": ok and elapsed <= BUDGET_MS, "raw_ok": ok, "error": error}
    if body and body.get("name"):
        row["name"] = body.get("name")
    if body and body.get("page"):
        row["name"] = body.get("page")
    print(json.dumps(row), flush=True)
    return payload


def click(name: str) -> dict:
    return request("POST", "/click", {"name": name})


def page(name: str) -> dict:
    return request("POST", "/page", {"page": name})


def controls() -> list[dict]:
    payload = request("GET", "/controls")
    return list(payload.get("controls") or [])


def named(prefix: str) -> str:
    for item in controls():
        label = str(item.get("name") or "")
        if label.startswith(prefix):
            return label
    return ""


def main() -> int:
    shape = sys.argv[1] if len(sys.argv) > 1 else "spread"
    print(json.dumps({"shape": shape}), flush=True)
    request("GET", "/state")
    page("sessions")
    request("POST", "/snapshot")
    click("sessions-tab-templates")
    request("POST", "/snapshot")
    click("sessions-tab-scheduled")
    click("scheduled-header-expand-all")
    click("scheduled-header-collapse-all")
    click("SELECT ALL")
    edit = named("EDIT ")
    if edit:
        click(edit)
        click("sessionCancel")
    else:
        print(json.dumps({"step": "edit-selected", "ok": False, "error": "no edit button"}), flush=True)
    items = request("GET", "/items?kind=sessions")
    rows = items.get("items") or []
    if rows:
        request("POST", "/items/open", {"kind": "sessions", "id": rows[0]["id"], "action": "edit"})
        click("sessionSave")
    page("history")
    request("POST", "/snapshot")
    for text in ("q", "qu", "qua", NEEDLE := "quasar-needle"):
        request("POST", "/set", {"name": "Search history", "value": text})
        time.sleep(0.35)
        request("GET", "/state")
    request("POST", "/set", {"name": "Filter by outcome", "value": "Failed"})
    request("GET", "/state")
    request("POST", "/set", {"name": "Filter by outcome", "value": "All outcomes"})
    click("history-expand-all")
    click("history-collapse-all")
    click("SELECT ALL")
    page("calendar")
    request("POST", "/snapshot")
    for _ in range(3):
        click("Next month")
    request("POST", "/items/open", {"kind": "night", "id": "2026-06-15", "action": "edit"})
    request("POST", "/snapshot")
    request("POST", "/window/resize", {"width": 1040, "height": 620})
    for name in ("sessions", "history", "calendar", "control"):
        page(name)
    request("POST", "/window/maximize")
    page("sessions")
    click("SELECT ALL")
    delete = named("DELETE ")
    if delete:
        click(delete)
        request("POST", "/confirm", {"action": "accept"})
    page("sessions")
    click("sessions-tab-templates")
    click("SELECT ALL")
    delete = named("DELETE ")
    if delete:
        click(delete)
        request("POST", "/confirm", {"action": "accept"})
    page("history")
    request("POST", "/set", {"name": "Search history", "value": ""})
    time.sleep(0.35)
    click("SELECT ALL")
    delete = named("DELETE ")
    if delete:
        click(delete)
        request("POST", "/confirm", {"action": "accept"})
    leftover = {
        "sessions": len((request("GET", "/items?kind=sessions").get("items") or [])),
        "templates": len((request("GET", "/items?kind=templates").get("items") or [])),
        "history": len((request("GET", "/items?kind=history").get("items") or [])),
    }
    print(json.dumps({"leftover": leftover}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
