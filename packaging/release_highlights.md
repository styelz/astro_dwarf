<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

feat: enhance telemetry decoding and device action handling
- Introduced a new dictionary for notify decoders in the TelemetryTap class to streamline command handling.
- Refactored the _decode method to utilize the new decoder structure, improving code readability and maintainability.
- Added a new method for decoding motor position, encapsulating related logic for better separation of concerns.
- Implemented a comprehensive _finish_device_action method in AppBackend to manage various device operations and telemetry updates, enhancing the overall device interaction experience.