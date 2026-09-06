# Astro Dwarf

<img width="1920" height="1200" alt="image" src="https://github.com/user-attachments/assets/316e2647-663c-43c4-b64b-c303105f8e9d" />

Native, multi-device control and scheduling for Dwarf telescopes. The interface
uses **PySide6 and Qt Quick/QML** in a real desktop window; it does not use a
browser or webview.

## Included

- Multiple named Dwarf II, Dwarf 3, or Dwarf Mini profiles
- Independent per-device connection and scheduler state
- Live control dashboard with stream, logs, current step, and upcoming sessions
- Calendar planning with duration calculated from editable hardware overheads
- Reusable session templates and manually scheduled sessions
- Stellarium current-target and Telescopius CSV import
- Single, wide, and mosaic imaging models
- Native right-click session menus
- JSON persistence, immutable run history, and old `Astro_Sessions` import
- Typed wrapper for calibration, focus, polar alignment, GOTO, camera, imaging,
  motors, lights, reboot, and power commands from
  [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api)

## Run

```powershell
cd astro_dwarf
python -m pip install -e ".[device,test]"
python -m astro_dwarf.app
```

The app starts with safe Demo mode enabled. Disable Demo mode for a device in
Settings when its IP, model and location are configured.
The scheduler is deliberately stopped at launch; start it from the Control
page only when the telescope and session queue are ready.

## Telescope SDK

Hardware control uses [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api)
(see [Credits](#credits)). That library talks to Dwarf II, Dwarf 3, and Dwarf Mini
over the V3 protobuf/WebSocket protocol.

The SDK keeps global device configuration, so the app launches one isolated
Python process per physical telescope. All SDK calls are asynchronous from the
Qt UI. Worker stdout, SDK diagnostics and errors are forwarded into the visible
Live Log panel instead of blocking or disappearing in a terminal.

## Credits

Telescope commands in this app are provided by
[`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api), created and
maintained by [JC L. (`stevejcl`)](https://github.com/stevejcl). Thanks to JC
for making that API available.

## Storage

Runtime data is under `data/`:

```text
devices/    per-telescope and timing profiles
templates/  reusable imaging recipes
sessions/   scheduled and running session snapshots
history/    immutable completed-run records
```

Old scheduler JSON can be imported from Settings. Existing applications are
not modified or imported at runtime.

## Test

```powershell
pytest
```
