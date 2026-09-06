from __future__ import annotations

import os
import sys


def _ensure_standard_streams() -> None:
    # PyInstaller's Windows GUI bootloader intentionally leaves these unset.
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def main() -> int | None:
    _ensure_standard_streams()
    if "--worker" in sys.argv or os.getenv("ASTRO_DWARF_WORKER") == "1":
        from .device_worker import main as worker_main

        worker_main()
        return None

    from .app import run

    return run()


if __name__ == "__main__":
    raise SystemExit(main())
