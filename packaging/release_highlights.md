<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

feat: enhance sky atlas functionality with zenith pane leveling and image handling
- Added `levelZenithPanes` function to ensure zenith panes remain level during rendering, improving visual accuracy.
- Introduced `imageQuadFromRing` function to correctly order image quadrants based on camera orientation.
- Updated drawing logic in `paintProjectedFov` to utilize new image handling functions for better alignment.

feat: enhance mosaic stitching with coarse cataloging and edge pairing improvements
- Introduced a coarse cataloging mechanism to handle full-frame stills that exceed the fine stitching window, improving alignment accuracy.
- Updated edge pairing logic to utilize coarse stars and seeds when fine matches are unavailable, enhancing robustness in challenging stitching scenarios.
- Modified the `_stars` function to allow dynamic limits on star detection, improving flexibility in star handling.

feat: add completion view readiness logic
- Introduced `completion_view_ready` function to determine when the finished mosaic picture can be displayed, ensuring it only shows settled pane stills.
- Updated `AppBackend` to integrate the new completion view logic, including retry mechanisms for completion view readiness.

feat: add target panel title functionality to enhance user interface
- Introduced `target_panel_title` function to dynamically generate the title for the control TARGET panel based on session and device states.
- Updated `AppBackend` with a new slot `targetPanelTitle` to expose the title generation logic to the QML layer.
- Modified `ControlPage.qml` to utilize the new `targetPanelTitle` function, improving the display of active session and device information.