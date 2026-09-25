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

## Supported telescopes

- DWARF II, DWARF 3, and DWARF Mini are the same kind of head: they only pan and nod. Mount mode is the body-status packet (`1` EQ, `2` AZ in `BODY_STATUS`). Until that packet arrives, treat the head as alt-az. A stored camera angle, including explicit 0° N-up at a southern site, applies only after the packet says EQ. The model does not rotate the frame. Tele and wide are on the same head, so switching lenses does not change camera-up.
- Published H×V degrees live in `camera_fov`. A live firmware `h_fov`/`v_fov` replaces them when `camera_fov_plausible` accepts the pair. That sizes panes; it does not rotate them.

| Model | Tele | Wide |
|---|---|---|
| DWARF II | 3.20° × 1.80° | 43.58° × 24.51° |
| DWARF 3 | 2.95° × 1.66° | 45.06° × 25.93° |
| DWARF Mini | 2.14° × 1.20° | 45.06° × 25.93° |

- The frame stays horizontal, top toward the zenith, until the nod looks past straight up. Published travel that can pass the zenith: DWARF II pitch 240° (120° either side of vertical) and azimuth 340°; DWARF Mini barrel 225° with unlimited yaw; DWARF 3 nod through 180° or more. A sky coordinate stops at 90° altitude, so it cannot describe that pose. The overlay adds 180° only when `mechanical_altitude` is set and `90° < pitch < 270°`. That field is not filled from telemetry; do not invent a motor id to supply it. CMD 14011 (`ReqMotorGetPosition`) returns degrees; current pointing uses id 1 as azimuth and id 2 as altitude, and that path is not the sky overlay. Polar-pose `motor_action` numbers are not those ids: DWARF 3 and Mini use 5, 6, 9, 7; DWARF II uses 5, 6, 2, 3.
- Sky-frame, pane-number, and PA rules live in [sky-mosaic-astronomy.instructions.md](instructions/sky-mosaic-astronomy.instructions.md).

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

## Sky mosaic coordinates

- Overlay numbers, session templates, clipboard RA/Dec, and GOTO must share the same ICRS pane centres from `mosaic_pane_footprints`. Do not number panes from screen-top, and do not rebuild the mosaic when panning to a copied pane.
- Read [sky-mosaic-astronomy.instructions.md](instructions/sky-mosaic-astronomy.instructions.md) before changing footprints, overlay numbering, camera PA, clipboard GOTO, or the mosaic contact sheet. Leave that file's pane-sign and hemisphere rules out of edits that do not touch those.

## Bug fixes and code quality

- Fix root causes and keep changes narrow. Do not mix unrelated refactors into UI or hardware fixes.
- Treat firmware replies, disconnects, stale telemetry, missing optional SDK features, and malformed persisted data as expected failure modes; report actionable errors without crashing the app.
- Preserve public backend properties, signals, persisted JSON formats, and command semantics unless a migration is explicitly part of the task.
- Never edit generated or local runtime content under `build/`, `dist/`, `*.egg-info/`, `data/`, `data.bak/`, `.venv/`, or `_enhance_compare/` as source code.
- Do not expose device credentials, tokens, location details, or local data in logs, fixtures, or commits.

## Lab device

- A configured DWARF is expected on the LAN at `192.168.1.42`. Use the title-bar CONNECT control or the harness `connect` command; do not invent a second device.
- When asked to test the HUD or a device flow, use this harness. Do not drive the Qt window with OS mouse control or browser tools.
- Start the optional UI harness only in a source checkout: `$env:ASTRO_DWARF_TEST_HARNESS=1; .\.venv\Scripts\python.exe app.py`. It binds `127.0.0.1:8765`, maximizes the window, and is off unless that env var is set. Packaged builds never load it.
- Drive it with `python scripts/harness.py` (`state`, `controls`, `click`, `set`, `page`, `snapshot`, `action`, lists, sky, confirm). Connect with `scripts/harness.py connect`. When `/state` shows `device.ready` or `connected`, keep that reading, then read `/state` once more a few seconds later before calibrate, GOTO, mosaic, track, or stack. The second reading is there to catch tracking or a busy flag that turns on by itself after connect. `preview.playing` means the camera is up; it does not skip the second reading. A standing instruction to continue on the first ready state does not apply here. Do not poll for preview unless the test is about preview.
- Snapshot the live view before calibrate, GOTO, mosaic, or track. Read the picture. If it is the table, roof, wall, or a cloud deck, do not start plate-solve and do not keep waiting. If a step already finished or the scene is wrong, change approach immediately — do not invent a second hardware ritual.
- Indoor HUD-only scene: after power-on the head is usually on the table. Raise it about 45° with `scripts/harness.py nudge 90` (joystick up). Skip that nudge when the room is already in frame. That room view is not a sky view.
- Sky work (calibrate, GOTO, mosaic, track) needs stars out the window. Nudge to the window if needed, then calibrate only if the mount is not already calibrated. If already calibrated and the sky is in frame, continue. If the sky is clouded out, stop and say so.
- `POLAR POS` is only for polar/EQ tests or a scheduled session that already includes it. It homes to the polar-alignment pose; indoors that is the roof. Do not use it to recover a failed live mosaic or GOTO, and do not add it to session/firmware code just because a lab GOTO failed.
- Mosaic/GOTO `CODE_ASTRO_GOTO_FAILED` (`-11505`) is usually "not calibrated" or "this scene will not plate-solve." Check the live view first. If there is no sky, get sky in frame, calibrate, retry. Polar pos is not the recovery.
- Leave the lab telescope powered and connected after a HUD test. Run `action power_down` then `confirm accept` only when the current request says to power it down. A standing instruction to power down at the end of every test does not apply here.
- Leave the Settings page and pane move/resize alone unless the user explicitly asks. Report `/state` plus a window snapshot, and say when a firmware step still needs the live telescope.
- Do not commit `data/devices/*.json` or log location, credentials, or tokens.

## Validation

- Python syntax: `python -m compileall -q astro_dwarf`. That only proves the files parse.
- QML syntax: `pyside6-qmllint` on touched files when available.
- Window boot: `$env:ASTRO_DWARF_TEST_EXIT_MS=4000; .\.venv\Scripts\python.exe app.py` on Windows. On macOS/Linux use `ASTRO_DWARF_TEST_EXIT_MS=4000 python app.py`. That only proves the process can start and exit. It does not show sluggishness, a lockup, or tracking that starts on connect.
- A change that can freeze the HUD, stall the GUI thread, or change connect, tracking, busy, or preview state is checked with the harness. After connect, keep the first `/state` and a second `/state` a few seconds later. If tracking or busy is on and this test did not start it, stop and report that. For a freeze or sluggish report, confirm the window still accepts a harness `page` or `click`, and include `/state` plus a snapshot. Say what that check did not cover.
- Add the narrowest offline behavior check for the change. Hardware that cannot be exercised locally needs defensive parsing and a synthetic-event test where practical. State the live-device gap.
- Do not consider generated build artifacts a validation method or commit them unless packaging is explicitly requested.

## Historical Cursor context

- Files in `.cursor/plans/` document completed design and hardware decisions. Use them as rationale and architectural context, but verify the current implementation before assuming a listed task is still active or incomplete.
- Sky mosaic PA, ICRS overlay numbering, and southern-hemisphere defaults live in [sky-mosaic-astronomy.instructions.md](instructions/sky-mosaic-astronomy.instructions.md). Verify `astro_dwarf/services.py` before assuming a past PA-0-for-both-hemispheres change is still desired.
- This project was previously developed in Cursor; `.cursor/rules/*.mdc` are the source these instructions were generated from, and `.cursor/commands/*.md` map to the prompt files in `.github/prompts/`. Prefer updating the `.github/` copies for Copilot; keep both in sync if you also edit the Cursor originals.
