<u>Work In Progress Release</u>

Night planning updates, plus a few device fixes from testing. Custom mosaic refactor.

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

feat: enhance custom mosaic orientation and session handling
- Added new functions to manage the orientation of running custom mosaics, ensuring proper alignment and locking of the mosaic center.
- Implemented a helper function to create a custom mosaic sky item for better session management.
- Updated session handling logic to incorporate the new mosaic orientation features, improving user experience during mosaic operations.
- Enhanced existing functionality to ensure seamless integration with the current session management system.

feat: enhance object tracking and telemetry handling
- Introduced new functions for managing object tracking states and responses, including handling box tracking and initialization codes.
- Updated telemetry logic to ensure proper state management during sidereal and object tracking.
- Enhanced QML components to support new tracking functionalities and improve user interactions.
- Added tests to validate object tracking behavior and response handling, ensuring robustness in tracking scenarios.