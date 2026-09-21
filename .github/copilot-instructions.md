# Astro Dwarf Repository Instructions

## Product and UI direction

- Preserve Astro Dwarf's compact, futuristic telescope HUD identity while making interactions clearer, faster, and more polished.
- Treat `astro_dwarf/qml/Theme.qml` as the source of truth for color, typography, spacing, shape, and motion. Prefer theme tokens over literal values.
- Improve shared controls in `astro_dwarf/qml/components/` before duplicating styling or behavior in pages.
- Keep screens information-dense and operational. Do not turn the app into a marketing-style or card-heavy interface.
- Retain the user-selectable hue and brightness behavior. New tinted colors should derive from `Theme.hsl`; semantic success, warning, and danger colors may remain fixed.
- Make state visible through concise labels, status color, focus treatment, and device-reported feedback. Include useful offline, empty, loading, busy, stale, success, and error states.
- Keep controls keyboard-usable, give icon-only controls tooltips and accessible names, preserve visible focus, and avoid shrinking primary targets below the existing shared-control sizes.
- Use restrained motion from `Theme.quick`, `Theme.normal`, and `Theme.slow`; animation must communicate state and must not resize or shift the surrounding layout.
- Check layouts at the minimum window size (`1040x620`) as well as the normal desktop size. Text must elide or wrap intentionally and controls must not overlap.

## Architecture

- Keep QML presentation in `astro_dwarf/qml/`, backend state and Qt models in `qt_backend.py`, hardware orchestration in `device_worker.py`, and packet normalization in `device_telemetry.py`.
- Keep device telemetry normalized at the worker/backend boundary. QML should consume stable backend fields instead of decoding SDK packets or inventing hardware state.
- Prefer real device telemetry for activity and completion state. UI-side pending state is only short-lived command feedback.
- Do not modify the installed `dwarf_python_api` package. Wrap or adapt SDK behavior inside this repository and fail defensively when SDK internals or optional fields differ.
- Preserve multi-device isolation: actions, telemetry, session state, and persisted settings must remain scoped to the intended telescope.
- Keep unattended scheduling non-blocking. Hardware warnings that can be safely bypassed should be logged and surfaced without stalling an overnight run.
- Reuse existing models, helpers, and QML components. Add an abstraction only when it removes meaningful duplication or centralizes behavior.

## Verified device behavior

- Treat the DWARF 3 wide camera as fixed-focus. Autofocus, infinity focus, and manual focus operate the telephoto motor; hide or disable focus controls for Wide and reject unsupported backend requests.
- Keep focus behavior shooting-mode aware. In Photo mode, normal autofocus must not switch to DSO mode or replace the user's exposure settings. In DSO mode, retain astronomical autofocus and infinity behavior. Firmware shooting mode `2` is DSO; mode `8` is Sun, not generic astro.
- Manual focus is an incremental, acknowledged motor operation. Keep direction fixed for a requested move, tolerate stale or reverse telemetry, bound retries, and do not report completion until the requested position is confirmed.
- Long-running operation completion must come from firmware replies or device state transitions. Do not leave UI activity latched when autofocus or another operation returns to idle, and do not treat command dispatch alone as completion.

## Live preview and targeting

- Keep frame-rate limiting and frame coalescing ahead of `QImage.copy()`, enhancement, hub updates, and repaint work. Hidden, minimized, background, or superseded frames should be discarded before expensive GUI-thread processing.
- Preserve the direct `LiveFrames`/`QQuickPaintedItem` preview path. Do not route high-rate frames through a Python `QQuickImageProvider`; render-thread GIL contention can freeze the window after focus or visibility changes.
- Map pointer coordinates through the exact `PreserveAspectFit` rectangle used to paint the frame, excluding letterbox regions. Overlays and hit testing must use the same geometry.
- For DWARF 3 wide-view centering, send normalized clicks directly as firmware Dual Lenses Locating coordinates in the `1920x1080` linkage space. Do not add the PictureMatching offset to the command. Use PictureMatching telemetry only for the tele-footprint overlay, and accept its `1920x1080` or doubled `3840x2160` coordinate space.
- Do not show a centered tele-footprint fallback while calibration telemetry is unavailable; wait for a valid device-reported rectangle so the UI does not imply false alignment.

## Bug fixes and code quality

- Fix root causes and keep changes narrow. Do not mix unrelated refactors into UI or hardware fixes.
- Treat firmware replies, disconnects, stale telemetry, missing optional SDK features, and malformed persisted data as expected failure modes; report actionable errors without crashing the app.
- Preserve public backend properties, signals, persisted JSON formats, and command semantics unless a migration is explicitly part of the task.
- Never edit generated or local runtime content under `build/`, `dist/`, `*.egg-info/`, `data/`, `data.bak/`, `.venv/`, or `_enhance_compare/` as source code.
- Do not expose device credentials, tokens, location details, or local data in logs, fixtures, or commits.

## Validation

- Python syntax: `python -m compileall -q astro_dwarf`. That only proves the files parse.
- QML syntax: `pyside6-qmllint` on touched files when available.
- Window boot: `$env:ASTRO_DWARF_TEST_EXIT_MS=4000; .\.venv\Scripts\python.exe app.py` on Windows. On macOS/Linux use `ASTRO_DWARF_TEST_EXIT_MS=4000 python app.py`. That only proves the process can start and exit. It does not show sluggishness, a lockup, or tracking that starts on connect.
- A change that can freeze the HUD, stall the GUI thread, or change connect, tracking, busy, or preview state is checked with the harness. After connect, keep the first `/state` and a second `/state` a few seconds later. If tracking or busy is on and this test did not start it, stop and report that. For a freeze or sluggish report, confirm the window still accepts a harness `page` or `click`, and include `/state` plus a snapshot. Say what that check did not cover.
- Add the narrowest offline behavior check for the change. Hardware that cannot be exercised locally needs defensive parsing and a synthetic-event test where practical. State the live-device gap.
- Do not consider generated build artifacts a validation method or commit them unless packaging is explicitly requested.

## Historical Cursor context

- Files in `.cursor/plans/` document completed design and hardware decisions. Use them as rationale and architectural context, but verify the current implementation before assuming a listed task is still active or incomplete.
