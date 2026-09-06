"""Astro Dwarf native multi-telescope controller."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _read_version() -> str:
    override = os.environ.get("ASTRO_DWARF_VERSION")
    if override:
        return override

    version_file = Path(__file__).resolve().parent.parent / "VERSION"
    if version_file.is_file():
        return version_file.read_text(encoding="utf-8").strip()

    try:
        return version("astro-dwarf")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _read_version()
