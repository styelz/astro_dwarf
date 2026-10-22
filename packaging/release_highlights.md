<u>Work In Progress Release</u>


If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

fix: parameters bug was causing video stream to fail if the Auto Parameters was selected and the device was rebooted.

feat: enhance telemetry handling with exposure and gain reporting
- Added functions to report exposure and gain values based on camera settings, improving telemetry accuracy.
- Updated `_decode_general_int_param` to utilize new reporting functions for exposure and gain parameters.
- Enhanced `camera_params_to_telemetry` to include checks for auto parameters, ensuring correct exposure and gain values are reported.
- Improved documentation for clarity on the new telemetry reporting logic.

feat: enhance stop notice handling and improve user feedback during session interruptions
- Introduced new logic to manage stop notices for various operations, ensuring they remain visible until the corresponding tasks are completed.
- Added functions to determine when a stop notice should stay active based on the state of the telescope and session.
- Updated QML properties to reflect the new stop notice details, improving user feedback during session interruptions.

feat: improve preview handling for DSO and photo mode transitions
- Updated logic in `preview_should_restore_dso` and `preview_should_preserve_shooting_mode` to clarify conditions for returning to DSO after photo mode.
- Introduced new functions `preview_reopens_via_photo_mode` and `preview_stack_encoder_blocks_tele` to manage encoder states and ensure proper transitions between modes.
- Enhanced logging to provide better feedback during live view transitions, particularly when handling stacking encoders.
- Improved documentation for clarity on the new preview handling logic and its impact on user experience.