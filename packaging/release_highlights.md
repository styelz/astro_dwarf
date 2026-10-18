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

feat: enhance mosaic functionality with new display logic and camera handling
- Introduced `mosaic_replaces_sheet` and `mosaic_session_should_drop_previous_sheet` functions to manage mosaic state transitions effectively.
- Added `mosaic_keep_camera_until_stack_frame` and `mosaic_camera_hold_timeout_s` functions for improved camera handling during mosaic operations.
- Updated `mosaic_preview_keep_live_sheet` and related methods to ensure proper handling of live and stored images in the mosaic display.
- Enhanced `ControlPage.qml` to dynamically determine the camera source for mosaic previews, improving user interface responsiveness.

feat: improve plate-solving handling and mosaic preview logic
- Introduced `_goto_solve_stalled` and `_retry_stalled_plate_solve` functions to manage plate-solving timeouts and retries effectively.
- Enhanced `_await_operation` to handle stalled plate-solving scenarios, raising appropriate errors for better error management.
- Updated mosaic preview logic to ensure the contact sheet remains visible during ongoing sessions and captures, improving user experience.
- Refactored related functions to streamline the handling of mosaic state transitions and improve clarity in the codebase.