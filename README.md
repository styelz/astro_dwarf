# Astro Dwarf

<img width="1920" height="1200" alt="image" src="https://github.com/user-attachments/assets/b658353d-5d8d-4027-aa38-cf6498fea76c" />

Desktop app for controlling and scheduling [Dwarf II](https://dwarflab.com/), Dwarf 3, and Dwarf Mini telescopes. Each telescope is a separate profile with its own IP, location, and session queue.

The Control page shows live view, device status, camera settings, commands, the upcoming queue, and a log. Calendar, Templates, History, and Settings are the other pages.

Sessions can be created by hand, from templates, from Stellarium's current target, or from a Telescopius CSV. Duration includes hardware overheads you can edit per telescope (slew, settle, calibration, focus, and so on). Tele/wide cameras and mosaics are supported.

Hardware commands go through [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api).

## Run from source

Needs [Python 3.11+](https://www.python.org/downloads/) and Git.

```text
git clone https://github.com/styelz/astro_dwarf.git
cd astro_dwarf
./start.sh          # macOS / Linux
.\start.bat         # Windows
```

The first run creates a local `.venv` and installs packages. Later runs skip that and start the app.

Set each telescope's IP, model, and location in Settings. The scheduler stays stopped until you start it from Control. Dwarf 3 and Mini live view needs `ffmpeg` on `PATH` (installers already include it). With the camera set to Wide, double-click a spot on the live view and the telescope slews the tele camera onto it (the official app's Dual Lenses Locating).

## Installers

Unsigned builds are on [GitHub Releases](https://github.com/styelz/astro_dwarf/releases). Pushing a change to the root `VERSION` file on `main` publishes a new set; you can also run **Build OS installers** in Actions.

- **Windows x64:** `AstroDwarf-Setup-<version>-win64.exe`. Per-user install to `%LOCALAPPDATA%\Astro Dwarf`; no admin required. SmartScreen may warn on an unrecognized app: **More info** → **Run anyway**. Uninstall any older Program Files copy first.
- **macOS Apple Silicon:** open the `.dmg`, drag to Applications, then right-click the app and choose **Open** the first time (unsigned / Gatekeeper).
- **Linux x64:** portable `.AppImage`, Debian/Ubuntu `.deb`, or Fedora/RHEL `.rpm`. Package installs go to `/opt/astro-dwarf`.

```bash
chmod +x AstroDwarf-*-linux-x86_64.AppImage
./AstroDwarf-*-linux-x86_64.AppImage

sudo apt install ./AstroDwarf-*-linux-amd64.deb
sudo dnf install ./AstroDwarf-*-linux-x86_64.rpm
```

## Data

When run from source, files live under `data/` in the repo. Installed copies use the OS app-data directory.

```text
devices/    telescope profiles and timing
templates/  reusable session recipes
sessions/   scheduled and running sessions
history/    completed runs
```

Old `Astro_Sessions` JSON can be imported from Settings. The old app's files are not changed.

## Credits

Telescope commands come from [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api) by [JC L. (`stevejcl`)](https://github.com/stevejcl).
