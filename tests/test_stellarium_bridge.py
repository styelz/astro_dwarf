from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.domain import Target
from astro_dwarf.services import StellariumClient


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _response(ok: bool = True, payload: dict | None = None, text: str = "ok") -> Mock:
    response = Mock()
    response.ok = ok
    response.text = text
    response.json.return_value = payload or {}
    if ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = RuntimeError("http error")
    return response


def test_available_ok_and_fail() -> None:
    client = StellariumClient("http://localhost:8090")
    with patch("astro_dwarf.services.requests.get", return_value=_response(True)) as get:
        _assert(client.available() is True, "live rc")
        get.assert_called_once()
        _assert(get.call_args.args[0].endswith("/api/main/status"), str(get.call_args))
    with patch("astro_dwarf.services.requests.get", side_effect=OSError("down")):
        _assert(client.available() is False, "offline rc")


def test_focus_name_and_j2000() -> None:
    client = StellariumClient("http://127.0.0.1:8090")
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.focus_target("M 31")
        _assert(post.call_args.args[0].endswith("/api/main/focus"), str(post.call_args))
        _assert(post.call_args.kwargs["data"]["target"] == "M 31", str(post.call_args))
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.focus_j2000(1.0, -20.0)
        data = post.call_args.kwargs["data"]
        vec = json.loads(data["position"])
        _assert(len(vec) == 3, str(vec))
        ra = 1.0 * 15.0 * math.pi / 180.0
        dec = -20.0 * math.pi / 180.0
        _assert(math.isclose(vec[0], math.cos(dec) * math.cos(ra), abs_tol=1e-9), str(vec))
        _assert(math.isclose(vec[2], math.sin(dec), abs_tol=1e-9), str(vec))


def test_location_and_fov_and_push() -> None:
    client = StellariumClient("http://localhost:8090/")
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.set_location(-37.8, 144.9, "DWARF 3")
        data = post.call_args.kwargs["data"]
        _assert(data["latitude"] == "-37.8", str(data))
        _assert(data["longitude"] == "144.9", str(data))
        _assert(data["name"] == "DWARF 3", str(data))
        _assert(post.call_args.args[0].endswith("/api/location/setlocationfields"), str(post.call_args))
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.set_fov(2.95)
        _assert(post.call_args.args[0].endswith("/api/main/fov"), str(post.call_args))
        _assert(post.call_args.kwargs["data"]["fov"] == "2.95", str(post.call_args))
    target = Target(name="M 42", ra_hours=5.5, dec_degrees=-5.4)
    with patch("astro_dwarf.services.requests.post", return_value=_response(True)) as post:
        client.push_view(target, -37.8, 144.9, "DWARF 3", 2.95)
        paths = [call.args[0] for call in post.call_args_list]
        _assert(any(item.endswith("/api/location/setlocationfields") for item in paths), str(paths))
        _assert(any(item.endswith("/api/main/focus") for item in paths), str(paths))
        _assert(any(item.endswith("/api/main/fov") for item in paths), str(paths))


def main() -> int:
    test_available_ok_and_fail()
    test_focus_name_and_j2000()
    test_location_and_fov_and_push()
    print("stellarium client tests ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
