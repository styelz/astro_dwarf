# Astro Dwarf

Tired of babysitting a Dwarf all night? Astro Dwarf is a desktop controller and unattended imaging scheduler for [Dwarf II](https://dwarflab.com/), Dwarf 3, and Dwarf Mini.

[Project site](https://styelz.github.io/astro_dwarf/) · [Installers](https://github.com/styelz/astro_dwarf/releases/latest)

## What it does

- Schedule unattended DSO imaging sessions — a Dwarf 3 scheduler and sequencer that also covers Dwarf II and Mini
- Run several telescope profiles from one desktop, each with its own IP, location, and session queue
- Live Control HUD: view, device status, camera settings, commands, upcoming queue, and log
- Session planning by hand, from templates, from Stellarium's current target, or from a Telescopius CSV
- Tele/wide cameras, mosaics, Dual Lenses Locating, Polar / EQ, and polar-alignment pose
- Media album of real astro sessions on the telescope (thumbnails, capture details, stacked-frame download) plus files already saved locally

Duration includes hardware overheads you can edit per telescope (slew, settle, calibration, focus, and so on). Calendar, Sessions, History, Media, and Settings sit alongside Control.

<p align="center">
  <a href="https://styelz.github.io/astro_dwarf/#screens">
    <img src="docs/screens/tour.webp" alt="Astro Dwarf page tour: Control, calendar, sessions, media, sky map, and settings" width="800">
  </a>
</p>

<p align="center">
  <a href="https://styelz.github.io/astro_dwarf/#screens">Interactive slideshow on the project site</a>
  · Control · Calendar · Sessions · Media · Sky · Settings
</p>

Hardware commands go through [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api) on the **`multi_V3`** branch (V3 protobuf/WebSocket protocol). Connect sends time, timezone, and site location; DSO sessions use shooting mode 2. Live camera parameters can be read from the telescope HTTP API on port `8082` after the WebSocket session is up. The Media page lists astro sessions from that same HTTP album API and can download stacked frames; still photos are still available there over FTP. Polar / EQ shows the last azimuth and altitude correction after solving, and Polar Pos homes the mount into the polar-alignment pose.

## Installers

Unsigned builds are on [GitHub Releases](https://github.com/styelz/astro_dwarf/releases). Pushing a **new** version in the root `VERSION` file on `main` publishes a replacement set (previous `v*` releases and tags are removed). You can also run **Build OS installers** in Actions to rebuild and replace the current tag.

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

Linux uses host EGL (not GLX) so the window still opens when XWayland or NVIDIA cannot match a GLX FBConfig. Stellarium Web needs that EGL context for WebGL. GTK module warnings such as `xapp-gtk3-module` are harmless. If graphics still fail, try `ASTRO_DWARF_QT_SOFTWARE=1 astro-dwarf`. WSL uses the software path by default; `ASTRO_DWARF_QT_SYSTEM=1` forces host graphics there. To force the old GLX path: `QT_XCB_GL_INTEGRATION=xcb_glx astro-dwarf`.

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

Astro Dwarf is an unofficial third-party tool. It is not affiliated with, endorsed by, or supported by [DwarfLab](https://dwarflab.com/) or [Stellarium Labs](https://stellarium-labs.com/).

Sky targeting talks to [Stellarium](https://stellarium.org/) desktop Remote Control when that plugin is running, and the SKY page loads [Stellarium Web](https://stellarium-web.org/) (operated by Stellarium Labs) as a sky map. Observing lists can be imported from a [Telescopius](https://telescopius.com/) CSV you export.

This project is licensed under the [MIT License](LICENSE).

Telescope commands come from [`dwarf_python_api`](https://github.com/stevejcl/dwarf_python_api) by [JC L. (`stevejcl`)](https://github.com/stevejcl).
