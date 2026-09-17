#!/usr/bin/env python3
"""CLI for the env-gated Astro Dwarf UI test harness."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8765"


def _url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def request(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(_url(base, path), data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            raise SystemExit(f"harness error {exc.code}: {raw}") from exc
        raise SystemExit(payload.get("error") or raw) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"harness not reachable at {base}: {exc.reason}") from exc
    return json.loads(raw)


def _print(payload: dict) -> int:
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok", True) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drive the Astro Dwarf UI test harness")
    parser.add_argument(
        "--url",
        default=os.environ.get("ASTRO_DWARF_TEST_HARNESS_URL", DEFAULT_URL),
        help="Harness base URL (default http://127.0.0.1:8765)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("state", help="Window, device, preview, and toast state")
    sub.add_parser("controls", help="Visible interactive controls")
    items = sub.add_parser("items", help="List sessions, templates, history, or media")
    items.add_argument("kind", nargs="?", default="sessions")

    click = sub.add_parser("click", help="Click a control by objectName, label, or path")
    click.add_argument("name")

    setter = sub.add_parser("set", help="Set a field, combo, spinbox, or check")
    setter.add_argument("name")
    setter.add_argument("value")

    page = sub.add_parser("page", help="Open control, calendar, sessions, history, media, or sky")
    page.add_argument("name")

    sub.add_parser("snapshot", help="Grab the Qt window to a PNG")

    connect = sub.add_parser("connect", help="Connect the lab telescope (default 192.168.1.42)")
    connect.add_argument("--ip", default="192.168.1.42")
    connect.add_argument("--id", default="")
    sub.add_parser("disconnect")
    sub.add_parser("cancel")
    select = sub.add_parser("select")
    select.add_argument("--id", default="")
    select.add_argument("--ip", default="")

    center = sub.add_parser("center", help="Wide-view Dual Lenses Locating tap")
    center.add_argument("nx", type=float)
    center.add_argument("ny", type=float)
    nudge = sub.add_parser("nudge", help="Joystick nudge angle in degrees")
    nudge.add_argument("angle", type=float)

    open_item = sub.add_parser("open")
    open_item.add_argument("kind")
    open_item.add_argument("id")
    open_item.add_argument("--action", default="edit")
    delete = sub.add_parser("delete")
    delete.add_argument("kind")
    delete.add_argument("id")
    run = sub.add_parser("run")
    run.add_argument("kind")
    run.add_argument("id")

    harvest = sub.add_parser("sky-harvest")
    harvest.add_argument("action", nargs="?", default="import")
    view = sub.add_parser("sky-view")
    view.add_argument("ra_hours", type=float)
    view.add_argument("dec_degrees", type=float)
    lock = sub.add_parser("sky-lock")
    lock.add_argument("name")
    lock.add_argument("ra_hours", type=float)
    lock.add_argument("dec_degrees", type=float)
    menu = sub.add_parser("sky-menu")
    menu.add_argument("action", choices=("overlay", "preview", "dblclick", "track"))

    action = sub.add_parser("action", help="Device command: power_down, calibrate, …")
    action.add_argument("operation")
    action.add_argument("--label", default="")
    confirm = sub.add_parser("confirm")
    confirm.add_argument("action", nargs="?", default="accept", choices=("accept", "cancel"))

    args = parser.parse_args(argv)
    base = args.url

    if args.cmd == "state":
        return _print(request(base, "GET", "/state"))
    if args.cmd == "controls":
        return _print(request(base, "GET", "/controls"))
    if args.cmd == "items":
        return _print(request(base, "GET", f"/items?kind={args.kind}"))
    if args.cmd == "click":
        return _print(request(base, "POST", "/click", {"name": args.name}))
    if args.cmd == "set":
        return _print(request(base, "POST", "/set", {"name": args.name, "value": args.value}))
    if args.cmd == "page":
        return _print(request(base, "POST", "/page", {"page": args.name}))
    if args.cmd == "snapshot":
        return _print(request(base, "POST", "/snapshot"))
    if args.cmd == "connect":
        return _print(request(base, "POST", "/device/connect", {"ip": args.ip, "id": args.id}))
    if args.cmd == "disconnect":
        return _print(request(base, "POST", "/device/disconnect"))
    if args.cmd == "cancel":
        return _print(request(base, "POST", "/device/cancel"))
    if args.cmd == "select":
        return _print(request(base, "POST", "/device/select", {"id": args.id, "ip": args.ip}))
    if args.cmd == "action":
        return _print(
            request(
                base,
                "POST",
                "/device/action",
                {"operation": args.operation, "label": args.label or args.operation},
            )
        )
    if args.cmd == "center":
        return _print(request(base, "POST", "/preview/center", {"nx": args.nx, "ny": args.ny}))
    if args.cmd == "nudge":
        return _print(request(base, "POST", "/joystick/nudge", {"angle": args.angle}))
    if args.cmd == "open":
        return _print(request(base, "POST", "/items/open", {"kind": args.kind, "id": args.id, "action": args.action}))
    if args.cmd == "delete":
        return _print(request(base, "POST", "/items/delete", {"kind": args.kind, "id": args.id}))
    if args.cmd == "run":
        return _print(request(base, "POST", "/items/run", {"kind": args.kind, "id": args.id}))
    if args.cmd == "sky-harvest":
        return _print(request(base, "POST", "/sky/harvest", {"action": args.action}))
    if args.cmd == "sky-view":
        return _print(request(base, "POST", "/sky/view", {"ra_hours": args.ra_hours, "dec_degrees": args.dec_degrees}))
    if args.cmd == "sky-lock":
        return _print(
            request(
                base,
                "POST",
                "/sky/lock",
                {"name": args.name, "ra_hours": args.ra_hours, "dec_degrees": args.dec_degrees},
            )
        )
    if args.cmd == "sky-menu":
        return _print(request(base, "POST", "/sky/menu", {"action": args.action}))
    if args.cmd == "confirm":
        return _print(request(base, "POST", "/confirm", {"action": args.action}))
    parser.error(f"unknown command {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
