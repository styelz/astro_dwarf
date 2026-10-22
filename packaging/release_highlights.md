<u>Work In Progress Release</u>


If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

fix: parameters bug was causing video stream to fail if the Auto Parameters was selected and the device was rebooted.

feat: enhance telemetry handling with exposure and gain reporting
- Added functions to report exposure and gain values based on camera settings, improving telemetry accuracy.
- Updated `_decode_general_int_param` to utilize new reporting functions for exposure and gain parameters.
- Enhanced `camera_params_to_telemetry` to include checks for auto parameters, ensuring correct exposure and gain values are reported.
- Improved documentation for clarity on the new telemetry reporting logic.