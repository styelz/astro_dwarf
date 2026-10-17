<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

feat: enhance sky atlas functionality with zenith pane leveling and image handling
- Added `levelZenithPanes` function to ensure zenith panes remain level during rendering, improving visual accuracy.
- Introduced `imageQuadFromRing` function to correctly order image quadrants based on camera orientation.
- Updated drawing logic in `paintProjectedFov` to utilize new image handling functions for better alignment.
- Enhanced tests to validate zenith pane leveling and image handling, ensuring consistent behavior with Stellarium's grid.

feat: enhance mosaic stitching with coarse cataloging and edge pairing improvements
- Introduced a coarse cataloging mechanism to handle full-frame stills that exceed the fine stitching window, improving alignment accuracy.
- Updated edge pairing logic to utilize coarse stars and seeds when fine matches are unavailable, enhancing robustness in challenging stitching scenarios.
- Modified the `_stars` function to allow dynamic limits on star detection, improving flexibility in star handling.
- Added a new test to validate stitching recovery for full-frame images shifted outside the fine window, ensuring consistent performance across various conditions.