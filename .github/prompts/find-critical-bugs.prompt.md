---
description: "Find and fix critical or major correctness bugs in recent Astro Dwarf changes"
agent: "agent"
---

You are hunting correctness bugs in this DWARF 3 Qt HUD. Fix critical and major bugs you can prove. A bug counts when a concrete trigger makes the operator, a saved session, or an overnight run do the wrong thing. Do not open a PR, do not commit, and do not invent Slack.

This repo already has always-on instructions in [copilot-instructions.md](../copilot-instructions.md) and path-scoped rules in [sky-mosaic-astronomy.instructions.md](../instructions/sky-mosaic-astronomy.instructions.md). Follow those. Do not restate them. Do not edit historical files under `.cursor/plans/`.

## 0. Ledger (do this first)

Canonical ledger is the repo-root `MEMORIES.md` (gitignored).

- Read it. If missing, create it with the table below. Do not copy it into agent stores, the user store, or chats.
- Skip rows marked `fixed` unless the current code has regressed. For an `open` row, check only whether this window still contains that bug.
- After you prove a bug, append one row. A finished backlog slice with nothing to fix gets a `reviewed` row (path or slice, and that no bug was found). Do not rewrite the file.

```markdown
# Bug-finding memory

Tracks critical and major bugs reported across automation runs.

| Date | Status | Description |
| --- | --- | --- |
```

Date is today. Status is `fixed` or `open`. Description is one line: `file.symbol` + root cause + operator-visible effect.

## 1. Review window

This runs when the user is ready to push. They commit as they go, so new bugs are in the **unpushed commits**, not in a dirty working tree. Older bugs sit in code that was already pushed before this command existed.

In Windows PowerShell use `;`, not `&&`. Quote `@{upstream}`: unquoted `@{ }` is a hashtable.

1. `git status -sb`
2. If the branch has an upstream: `git log --oneline "@{upstream}..HEAD"` and `git diff --stat "@{upstream}...HEAD"`
3. If it has no upstream: `git log --oneline origin/main..HEAD` and `git diff --stat origin/main...HEAD`

That range is only the work about to be pushed. Do not stop at the last 15 commits. Most of this app was written before this command existed and is already on the remote, so a push diff will never show it. Each run also reads the next backlog slice below that has no `reviewed` row.

Rank files from the push diff stat before opening a patch. Then `git diff "@{upstream}...HEAD" -- <paths>` (or `origin/main...HEAD` when there is no upstream) only for the files you will trace. Do not load the full-tree diff.

If `git status` still shows uncommitted edits, include those paths too (`git diff --stat HEAD`, then `git diff HEAD -- <paths>`). A clean tree means there is nothing uncommitted to review.

Review the push range, that one backlog slice, and the caller chain of a suspected bug. Read the current functions in the slice, not old commits. Do not audit the whole tree. Do not reread a `reviewed` slice unless this push touches it.

Backlog, one slice per run, in this order:

1. `device_worker.py` — GOTO wait, mosaic pane advance, autofocus, burst and timelapse start
2. `device_telemetry.py` — activity, and record, burst, and timelapse returning to idle
3. `qt_backend.py` — `_restore_control_settings`, `_remember_control_settings`, `_scheduler_tick`, `_finish_live_mosaic`
4. `qt_backend.py` — `_sync_preview_for_capture` and the module-level `preview_*` / `mosaic_*` helpers above `AppBackend`
5. `services.py` — footprints, FOV, resume plan, sky-map view key
6. `domain.py` — session and mosaic planning that the backend calls
7. `storage.py` — history and live-mosaic JSON reads and writes
8. `stream_preview.py` — frame copy, letterbox mapping, tele footprint
9. `sky_atlas.py` — ICRS centres shared with GOTO and the overlay
10. `ControlPage.qml`, `SkyPage.qml`, `SkyWebView.qml`, `qml/components/StackTimer.qml` — idle, busy, and error state, and the centres sent to GOTO

| Layer | Files | Typical breakage |
| --- | --- | --- |
| Worker / firmware wait | `device_worker.py`, `device_telemetry.py` | False GOTO complete, latched AF, overnight hang, same-field mosaic panes |
| Backend orchestration | `qt_backend.py`, `services.py`, `domain.py` | Resume skips a pane, History dropped, settings restored onto a live stack, scheduler blocked or stacked on a capture |
| Persistence | `storage.py`, `data/live-mosaics/`, sessions/history JSON | Wipe on failure, silent truncation, cross-device bleed |
| Preview | `stream_preview.py`, live QML preview items | GUI freeze, wrong tap mapping, false tele-footprint |
| Sky mosaic | `services.py` footprints, `sky_atlas.py`, `SkyPage.qml`, `SkyWebView.qml` | Overlay numbers ≠ GOTO ICRS, Wide FOV spacing a tele stack |
| HUD | `qml/pages/ControlPage.qml`, `qml/components/StackTimer.qml`, shared `qml/components/` | Operator sees idle/busy/error wrong |

Ignore style, UX polish, theoretical nulls, "auth bypass" (local HUD), `dwarf_python_api` internals, the Settings page, and pane move/resize. If a diff is mostly those, skip the file. Read `data/` only to check a wipe or bleed; do not edit it.

## 2. What to fix

Same proof bar for both severities: user action + device or session state + the wrong outcome. Critical means lost work, the wrong sky, a hang, a freeze, or the wrong telescope. Major means the run continues, but the operator or the saved result is wrong. Both get fixed.

**Critical**

- Lost or skipped mosaic panes; later panes stacking the previous field
- History / live-mosaic JSON wiped so finished work cannot resume
- Overnight scheduler starting a session on top of a live stack, or skipping every due session after a failed mosaic
- Persisted CONTROL exposure/gain/mode rewritten onto an in-progress mosaic or swapped camera
- Autofocus or another long op left latched after firmware is idle
- Preview path that can freeze the window (GIL / `QQuickImageProvider` on the live path)
- GOTO / overlay / saved templates using different ICRS centres
- Multi-device action or settings applied to the wrong telescope

**Major**

- Parameter or unit mismatch (count, duration, gain, exposure, shooting mode) so the capture is not what was set
- Photo autofocus switching into DSO, or focus controls left active on fixed-focus Wide
- Completion or idle reported from dispatch, a stale notification, or a late STOPPING unwind
- HUD elapsed time, record state, or mode stuck or showing the wrong clock after firmware moved on
- Sky box, clipboard, or pane centres that disagree with the ICRS used for GOTO
- Resume, History, or the scheduler dropping or skipping work without deleting files

Do **not** treat these as software bugs:

- Indoor `CODE_ASTRO_GOTO_FAILED` (`-11505`) with table/roof/wall/cloud in live view
- Polar pos as recovery for a failed mosaic or GOTO
- Southern default PA `180` vs stored explicit `0`
- Overlay labels that match `mosaic_pane_footprints` (do not negate `up`/`right` to "fix" numbers)
- Firmware optional fields missing, when that failure is already reported without crashing

If you cannot name the trigger, drop it. If nothing in the window meets this bar, say so and stop. Do not stretch into nits.

## 3. Trace, then prove

Read the current functions, not just the diff. Follow QML → `qt_backend.py` → `device_worker.py` → normalized telemetry. QML must not be decoding SDK packets.

`tests/test_*.py` is tracked. Other files under `tests/` are gitignored. Add or extend one focused test when the bug is logic or persistence. Do not add a test for a live firmware race you cannot simulate, and do not run the suite.

Run only the narrowest matching tests for the bug you are proving (`test_mosaic_recovery.py`, `test_mosaic_plan.py`, `test_mosaic_pane_centers.py`, `test_sky_fov.py`, `test_capture_history.py`, `test_preview_stream.py`, `test_stack_action_guards.py`, `test_goto_stopping.py`, `test_exposure_running.py`, or another `tests/test_*.py` that covers the symbol). After a Python edit: `.\.venv\Scripts\python.exe -m compileall -q astro_dwarf`. Touched QML: `pyside6-qmllint` when available. Optional smoke: `$env:ASTRO_DWARF_TEST_EXIT_MS=4000; .\.venv\Scripts\python.exe app.py`.

**Harness only** when the claimed breakage is what the operator sees (HUD, dialog, list, sky overlay, preview, live connect). Do not drive the Qt window with OS mouse or browser tools. Follow the Lab device section of [copilot-instructions.md](../copilot-instructions.md), plus:

- Check the terminals folder first. If a harness `app.py` is already up, use it. Never start a second instance.
- Start from this checkout only if needed: `$env:ASTRO_DWARF_TEST_HARNESS=1; .\.venv\Scripts\python.exe app.py` (background). Client: `.\.venv\Scripts\python.exe scripts\harness.py`.
- Lab telescope is `192.168.1.42`. Connect only if the bug needs the live device. Do not invent a second device.
- After connect, keep the first `/state` with `device.ready` or `connected`, then read `/state` once more a few seconds later before calibrate, GOTO, mosaic, track, or stack. If tracking or busy turned on by itself, stop and report that. `preview.playing` does not skip that second reading. Do not poll for preview unless the bug is preview.
- Indoor scene: snapshot first. `nudge 90` only if live view is the table. Sky work needs stars; if the scene is indoor or clouded out, stop that firmware path and say so.
- Leave Settings and pane chrome alone.
- **Do not power down.** Leave the lab connection up.
- After a harness check: report `/state` plus a window snapshot. Never commit `data/devices/*.json` or log location, credentials, or tokens.

Say when a remaining check still needs the live telescope.

## 4. Fix

- Narrow, high-confidence fix for a proven critical or major bug only.
- Re-run the same test or harness path after the fix.
- Do not mix refactors. Do not bump `VERSION`. Do not edit the installed `dwarf_python_api` package. Do not edit `data/`.
- Do not create a PR. Do not commit unless the user asks in this chat.

## 5. Report

Lead with what you found, or say that nothing in the push range or the backlog slice met the bar. For each bug: severity (`critical` or `major`), trigger, root cause, what changed, how you verified, and any live-device gap. Name the backlog slice you covered and the `MEMORIES.md` row you added.
