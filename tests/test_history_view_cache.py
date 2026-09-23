from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from astro_dwarf.qt_backend import AppBackend


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _bare() -> AppBackend:
    backend = AppBackend.__new__(AppBackend)
    backend._history_view = None
    backend._duration_suggestion = None
    backend.history_builds = 0
    backend.suggestion_builds = 0

    def build_history() -> list[dict[str, int]]:
        backend.history_builds += 1
        return [{"id": backend.history_builds}]

    def build_suggestion() -> dict[str, int]:
        backend.suggestion_builds += 1
        return {"run_count": backend.suggestion_builds}

    backend._build_history_view = build_history
    backend._build_duration_suggestion = build_suggestion
    return backend


def test_history_view_is_reused_until_invalidated() -> None:
    backend = _bare()
    first = backend._ensure_history_view()
    second = backend._ensure_history_view()
    _assert(first is second, "history snapshot is reused")
    _assert(backend.history_builds == 1, "history snapshot builds once")
    _assert(first == [{"id": 1}], "snapshot keeps the built rows")
    backend._invalidate_history_view()
    third = backend._ensure_history_view()
    _assert(third is not first, "invalidation drops the snapshot")
    _assert(backend.history_builds == 2, "next read rebuilds once")
    _assert(backend._duration_suggestion is None, "history invalidation drops the duration hint")


def test_duration_suggestion_is_reused_until_invalidated() -> None:
    backend = _bare()
    first = backend._ensure_duration_suggestion()
    second = backend._ensure_duration_suggestion()
    _assert(first is second and first["run_count"] == 1, "duration hint is reused")
    _assert(backend.suggestion_builds == 1, "duration hint builds once")
    backend._duration_suggestion = None
    third = backend._ensure_duration_suggestion()
    _assert(third["run_count"] == 2, "cleared hint rebuilds")
    _assert(backend.suggestion_builds == 2, "duration hint builds again")
