<u>Work In Progress Release</u>

Night planning updates, plus a few device fixes from testing.

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

- UX: Scheduled list shows planned and running only. Finished runs stay on History unless Include finished is on.
- UX: Place a template or a copy on a night from one dialog. Copy Night duplicates this telescope's planned night onto the next night.
- UX: Reset asks whether to keep the recorded run on History or discard it.
- Fix: The scheduler only starts sessions for tonight. A leftover session from an earlier night is left alone.
- Fix: A device mosaic that stopped early is started again. One that already finished is left done.
- Fix: Panorama no longer errors when the framing close is rejected after the shoot has started.
- Fix: DWARF Mini polar position only moves pitch. Rotation has no home sensor.
