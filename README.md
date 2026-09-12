# Astro Dwarf - Multi Device Controller and Scheduler

Desktop app for controlling and scheduling [Dwarf II](https://dwarflab.com/), Dwarf 3, and Dwarf Mini telescopes. Each telescope is a separate profile with its own IP, location, and session queue.

The Control page shows live view, device status, camera settings, commands, the upcoming queue, and a log. Calendar, Sessions, History, Media, and Settings are the other pages. Media lists real astro sessions on the telescope (thumbnails, capture details, download) and files already saved locally.

Sessions can be created by hand, from templates, from Stellarium's current target, or from a Telescopius CSV. Duration includes hardware overheads you can edit per telescope (slew, settle, calibration, focus, and so on). Tele/wide cameras and mosaics are supported.

<img width="1920" height="1200" alt="image" src="https://github.com/user-attachments/assets/47288be4-c3c4-437b-9ec5-ccc7d02f8a81" />

Hardware commands go through [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api) on the **`multi_V3`** branch (V3 protobuf/WebSocket protocol). Connect sends time, timezone, and site location; DSO sessions use shooting mode 2. Live camera parameters can be read from the telescope HTTP API on port `8082` after the WebSocket session is up. The Media page lists astro sessions from that same HTTP album API and can download stacked frames; still photos are still available there over FTP. Polar / EQ shows the last azimuth and altitude correction after solving, and Polar Pos homes the mount into the polar-alignment pose.

## Run from source

Needs [Python 3.11+](https://www.python.org/downloads/) and Git.

```text
git clone https://github.com/styelz/astro_dwarf.git
cd astro_dwarf
./start.sh          # macOS / Linux
.\start.bat         # Windows
```

The first run creates a local `.venv` and installs packages, including `dwarf_python_api@multi_V3`. Later runs skip that unless the V3 helpers are missing. If you already had an older venv, delete `.venv` or run `pip install -e ".[device]"` inside it.

Set each telescope's IP, model, and location in Settings. The scheduler stays stopped until you start it from Control. Dwarf 3 and Mini live view needs `ffmpeg` on `PATH` (installers already include it). With the camera set to Wide, double-click a spot on the live view and the telescope slews the tele camera onto it (the official app's Dual Lenses Locating).

## Installers

Unsigned builds are on [GitHub Releases](https://github.com/styelz/astro_dwarf/releases). Pushing a change to the root `VERSION` file on `main` publishes a new set; you can also run **Build OS installers** in Actions.

- **Windows x64:** `AstroDwarf-Setup-<version>-win64.exe` (also in a `.zip`). Per-user install to `%LOCALAPPDATA%\Astro Dwarf`; no admin required. SmartScreen may warn on an unrecognized app: **More info** → **Run anyway**. Uninstall any older Program Files copy first. For a copy that does not need installing, extract `AstroDwarf-<version>-win64-portable.zip` and run `AstroDwarf\AstroDwarf.exe`.
- **macOS Apple Silicon:** open the `.dmg`, drag to Applications, then right-click the app and choose **Open** the first time (unsigned / Gatekeeper). The `.pkg` also installs `astro-dwarf` on `PATH` (`/usr/local/bin`).
- **Linux x64:** portable `.AppImage`, Debian/Ubuntu `.deb`, Fedora/RHEL `.rpm`, or Arch Linux `.pkg.tar.zst`. Package installs go to `/opt/astro-dwarf` and put `astro-dwarf` (and `AstroDwarf`) on `PATH`.

```bash
chmod +x AstroDwarf-*-linux-x86_64.AppImage
./AstroDwarf-*-linux-x86_64.AppImage

sudo apt install ./AstroDwarf-*-linux-amd64.deb
sudo dnf install ./AstroDwarf-*-linux-x86_64.rpm
sudo pacman -U ./AstroDwarf-*-linux-x86_64.pkg.tar.zst
astro-dwarf
```

Linux installers start with software Qt Quick so the window still opens when the host GPU stack cannot initialize GLX (common on NVIDIA and XWayland). GTK module warnings such as `xapp-gtk3-module` are harmless. To use the host OpenGL driver instead: `ASTRO_DWARF_QT_SYSTEM=1 astro-dwarf`.

## Data

When run from source, files live under `data/` in the repo. Installed copies use the OS app-data directory.

```text
devices/    telescope profiles and timing
settings.json  shared night cutoff and Stellarium URL
templates/  reusable session recipes
sessions/   scheduled and running sessions
history/    completed runs
album/      stacked frames and stills downloaded from the telescope
```

Old `Astro_Sessions` JSON can be imported from Settings. The old app's files are not changed.

## Credits

Telescope commands come from [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api) by [JC L. (`stevejcl`)](https://github.com/stevejcl).
