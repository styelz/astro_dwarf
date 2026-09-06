# Astro Dwarf

<img width="1920" height="1200" alt="image" src="https://github.com/user-attachments/assets/5749c6b7-ab12-4150-a6c0-b24357c99e05" />

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

## Install

Successful installer builds automatically increment the patch version, bake it
into the app, and publish unsigned installers on the
[GitHub Releases page](https://github.com/styelz/astro_dwarf/releases).
That happens on every push to `main`, or when you run **Build OS installers**
from Actions (choose patch, minor, or major). The version is shown in the
title bar and Settings.

- **Windows x64:** download and run `AstroDwarf-Setup-<version>-win64.exe`.
  Windows SmartScreen may show an unrecognized-app warning; choose **More info**
  and **Run anyway**.
- **macOS Apple Silicon:** open the `.dmg`, drag Astro Dwarf to Applications,
  then right-click the installed app and choose **Open** the first time to
  approve the unsigned app in Gatekeeper.
- **Linux x64:** choose the portable `.AppImage`, Debian/Ubuntu `.deb`, or
  Fedora/RHEL `.rpm`. The package installers place the app under
  `/opt/astro-dwarf`.

```bash
# Portable AppImage
chmod +x AstroDwarf-*-linux-x86_64.AppImage
./AstroDwarf-*-linux-x86_64.AppImage

# Debian or Ubuntu
sudo apt install ./AstroDwarf-*-linux-amd64.deb

# Fedora or RHEL
sudo dnf install ./AstroDwarf-*-linux-x86_64.rpm
```

The installers include ffmpeg for the Dwarf 3 and Dwarf Mini RTSP live view.

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
