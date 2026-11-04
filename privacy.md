# Privacy policy

Astro Dwarf is a desktop controller and unattended imaging scheduler for Dwarf II, Dwarf 3, and Dwarf Mini telescopes. It runs on your computer. It has no user account, and it does not send usage reports, crash reports, or update checks to the people who maintain it.

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

The sections below describe the information the app stores, and the transfers that happen when you use a feature that needs them.

## Information stored on this computer

An installed copy keeps its library in the per-user application data folder for Astro Dwarf. On Windows that is `%APPDATA%\Astro Dwarf\Astro Dwarf`. macOS and Linux use the equivalent per-user folder. A source checkout uses the `data` folder beside the application, unless `ASTRO_DWARF_DATA` points somewhere else.

That folder holds:

- Telescope profiles (`devices`): display name, model, IP address, Wi-Fi name and password, Bluetooth password, site latitude and longitude, timezone, camera defaults, and mosaic position angle.
- Planned sessions, templates, and history: target names, sky coordinates, capture settings, and schedule times.
- App settings (`settings.json`): observing-day cutoff hour, the Stellarium remote-control address, the sky-chart choice, and the last selected telescope.
- A live mosaic in progress, plus pictures and album files you download from a telescope.

Appearance, pane layout, and the last sky chart view (right ascension, declination, and field of view) are stored in this computer’s Qt settings for Astro Dwarf, separate from that folder.

The app also appends a session log, `app-session.log`, in the working directory, or at the path in `ASTRO_DWARF_LOG` when that variable is set. Log lines can include a telescope address, site coordinates, target names, and command status. The log stays on this computer.

On Windows, asking the app to join a telescope hotspot adds a Wi-Fi profile for that network on this PC. The passphrase is the one saved on the telescope profile.

## When the app uses the network

Nothing is sent until you use a feature that needs a particular system.

**The telescope you configured.** Connect, live view, the album, and commands go to the IP address saved on that profile, over your local network or the telescope’s own hotspot. The app sends the site coordinates and passwords you saved, and the camera and mount commands you start. Preview frames and album files come back from that telescope. Bluetooth discovery talks only to a nearby Dwarf, using the Bluetooth password on the profile. That traffic does not go to the project.

**Stellarium on an address you set.** Importing the current target, or pushing a view, uses the Stellarium remote-control URL in Settings. The default is `http://localhost:8090`. The exchange stays on the address you chose.

**A place search you start.** A city or timezone search uses a timezone list shipped with the app. When that list has no match, the text you typed is sent to OpenStreetMap Nominatim at `https://nominatim.openstreetmap.org/search`, with a User-Agent of `AstroDwarf/` plus the app version. The reply is a place name and coordinates. Those coordinates are saved only if you keep them on a telescope profile. Nominatim’s rules are the [usage policy](https://operations.osmfoundation.org/policies/nominatim/) and the [OpenStreetMap Foundation privacy policy](https://osmfoundation.org/wiki/Privacy_Policy).

**The sky chart you open.** Sky uses Stellarium Web by default (`https://stellarium-web.org/`). The page loads inside the app. So the chart matches the telescope, the app writes the saved site latitude, longitude, timezone, and place name into that page, and turns off the page’s automatic location. Stellarium Web is operated by Stellarium Labs, shows its own cookie notice, and applies its own privacy policy, linked from that site. The embedded browser can keep that site’s cookies and local data on this computer. On Linux that profile is named `stellarium-web`.

Choosing Aladin Lite loads the chart library from `https://aladin.cds.unistra.fr/AladinLite/` and Digitized Sky Survey tiles from `https://alasky.cds.unistra.fr/DSS/DSSColor`. Those requests identify the sky coordinates on screen. The chart is served from this computer, and the site coordinates are used there to orient the horizon. The Simbad pointer on that chart can send an object query to the Strasbourg astronomical Data Centre (CDS). CDS describes the services at [cds.unistra.fr](https://cds.unistra.fr/).

**A target name from the telescope.** Firmware GOTO replies carry the target name only. While a named target is tracking and the coordinates are not already known, the app asks public catalogs for the matching sky position. The object name is sent to SIMBAD at `https://simbad.cds.unistra.fr/simbad/sim-tap/sync`. A name that contains a Gaia source id is sent to the ESA Gaia archive at `https://gea.esac.esa.int/tap-server/tap/sync`. The request uses a User-Agent of `AstroDwarf/` plus the app version. It does not include your site coordinates or the telescope address.

**A link you save from the chart.** Saving an `http` or `https` link downloads that address to this computer.

A Telescopius import reads a CSV file you choose. It does not contact Telescopius.

## Maintainer access

Telescope profiles, session plans, logs, and catalog lookups are not sent to the Astro Dwarf maintainers or to GitHub. Catalog and chart requests go to the services named above, under those services’ own policies.

`dwarf_python_api` is the local library that speaks to the telescope you configured. It does not add a separate cloud service.

## Removing the data

Uninstalling Astro Dwarf removes the program. Telescope profiles, sessions, and logs in the application data folder remain until you delete that folder. On Windows, a hotspot profile added for the telescope remains in Windows Wi-Fi settings until you remove it there. Qt settings for appearance, layout, and the last sky view remain in the system settings store for Astro Dwarf until you remove them.

## Changes

This policy describes the current application. When the network behavior changes, this file changes with it.

## Contact

Questions and corrections go to the project issues: [github.com/styelz/astro_dwarf/issues](https://github.com/styelz/astro_dwarf/issues).
