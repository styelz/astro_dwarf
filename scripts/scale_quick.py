"""Short timings that separate HUD work from the harness object walk."""

from __future__ import annotations

import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8765"


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict, str]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    started = time.perf_counter()
    error = ""
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        payload = {}
        error = str(exc)
    return int((time.perf_counter() - started) * 1000), payload, error


def step(label: str, method: str, path: str, body: dict | None = None) -> dict:
    elapsed, payload, error = call(method, path, body)
    row = {"step": label, "ms": elapsed, "ok": not error and elapsed <= 1000, "error": error}
    print(json.dumps(row), flush=True)
    return payload


def main() -> int:
    shape = sys.argv[1] if len(sys.argv) > 1 else "crowded"
    print(json.dumps({"shape": shape}), flush=True)
    step("state", "GET", "/state")
    for kind in ("sessions", "templates", "history"):
        payload = step(f"items-{kind}", "GET", f"/items?kind={kind}")
        print(json.dumps({"count": kind, "n": len(payload.get("items") or [])}), flush=True)
    step("controls", "GET", "/controls")
    step("page-calendar", "POST", "/page", {"page": "calendar"})
    step("open-night", "POST", "/items/open", {"kind": "night", "id": "2026-06-15"})
    snap = step("snapshot-night", "POST", "/snapshot")
    path = str((snap or {}).get("path") or "")
    if path:
        dest = Path.home() / "AppData" / "Local" / "Temp" / f"astro-scale-{shape}.png"
        shutil.copyfile(path, dest)
        print(json.dumps({"saved": str(dest)}), flush=True)
    step("page-sessions", "POST", "/page", {"page": "sessions"})
    step("expand-sessions", "POST", "/click", {"name": "scheduled-header-expand-all"})
    step("page-history", "POST", "/page", {"page": "history"})
    step("search", "POST", "/set", {"name": "Search history", "value": "quasar-needle"})
    time.sleep(0.35)
    step("state-after-search", "GET", "/state")
    step("resize-min", "POST", "/window/resize", {"width": 1040, "height": 620})
    step("page-calendar-min", "POST", "/page", {"page": "calendar"})
    step("snapshot-min", "POST", "/snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
