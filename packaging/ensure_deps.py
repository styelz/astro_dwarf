"""Tell start scripts whether the private venv still matches pyproject.toml.

Exit 0 if packages are present and importable. Exit 1 if pip install is needed.
Prints a short reason on stdout so the start script can show it.
"""
from __future__ import annotations

import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
EXTRA = "device"


def _requirement_name(raw: str) -> str:
    text = raw.split("#", 1)[0].strip()
    if not text:
        return ""
    if " @ " in text:
        text = text.split(" @ ", 1)[0]
    return re.split(r"[\s<>=!~;\[]", text, maxsplit=1)[0].strip()


def _declared_requirements() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    reqs = [str(item) for item in data.get("project", {}).get("dependencies", [])]
    extras = data.get("project", {}).get("optional-dependencies", {})
    reqs.extend(str(item) for item in extras.get(EXTRA, []))
    return [item.strip() for item in reqs if item and item.strip() and not item.strip().startswith("#")]


def _missing_packages() -> list[str]:
    try:
        from packaging.requirements import Requirement
    except ImportError:
        Requirement = None  # type: ignore[assignment]

    missing: list[str] = []
    for raw in _declared_requirements():
        if Requirement is not None:
            try:
                req = Requirement(raw)
                have = version(req.name)
                if req.specifier and have not in req.specifier:
                    missing.append(f"{req.name} {have} (need {req.specifier})")
                continue
            except PackageNotFoundError:
                missing.append(_requirement_name(raw) or raw)
                continue
            except Exception:
                pass
        name = _requirement_name(raw)
        if not name:
            continue
        try:
            version(name)
        except PackageNotFoundError:
            missing.append(name)
    return missing


def _smoke_ok() -> bool:
    from contextlib import redirect_stderr, redirect_stdout
    from io import StringIO

    try:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            import PySide6  # noqa: F401
            from dwarf_python_api.lib.dwarf_utils import (  # noqa: F401
                perform_enter_astro_mode,
                perform_read_camera_params_http_v3,
            )
    except Exception:
        return False
    return sys.version_info >= (3, 11)


def main() -> int:
    if not PYPROJECT.is_file():
        print("pyproject.toml is missing")
        return 1
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required")
        return 1
    try:
        missing = _missing_packages()
    except Exception as exc:
        print(f"Could not read package list: {exc}")
        return 1
    if missing:
        print("Need " + ", ".join(missing))
        return 1
    if not _smoke_ok():
        print("Installed packages are incomplete or cannot be imported")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
