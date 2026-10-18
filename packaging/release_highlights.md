<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

refactor: remove skyToolsEnabled property and related logic
- Eliminated the skyToolsEnabled property from multiple components, simplifying the codebase.
- Updated navigation and context menu logic to remove dependencies on skyToolsEnabled, enhancing clarity and reducing complexity.
- Adjusted related properties and functions to ensure consistent behavior without the skyToolsEnabled flag.

feat: add calendar time conflict detection for session overlap
- Introduced `calendarTimeConflicts` method in `AppBackend` to determine if two sessions overlap based on their start and end times.
- Added `calendar_time_conflicts` function in `services.py` to handle the logic for checking time conflicts with a defined slack period.
- Updated `CalendarPage.qml` to utilize the new conflict detection logic, ensuring accurate lane assignment for overlapping sessions.
- Enhanced comments in the QML file for clarity on session overlap criteria.

feat: enhance HistoryPage and SessionsPage with group member handling and tap gesture improvements
- Added `groupMemberIds` and `setMemberDetails` functions to manage group member IDs and their expanded states in HistoryPage.
- Updated `toggleGroup` function to utilize new member handling logic for better group expansion behavior.
- Improved `canExpandAll` and `canCollapseAll` properties for more intuitive group management.
- Modified SessionsPage to change tap gesture handling, enhancing user interaction with group elements.

feat: enhance AppBackend with known pointing and session handling improvements
- Added `_known_pointing_for_name` method to retrieve coordinates for known pointing names without catalog lookup.
- Introduced `_active_pointing_session` to manage active sessions and improve session retrieval logic.
- Enhanced `lockSkyToTrackedTarget` method to utilize known pointing information for better sky lock handling.
- Implemented `_emit_known_sky_lock` to streamline sky lock emissions based on known coordinates.

feat: enhance session management with mosaic group assignment and separation logic
- Added `assign_scheduled_mosaic_group` function to assign unique mosaic IDs to scheduled sessions, preventing ID collisions.
- Implemented `separate_repeated_mosaic_runs` method to split planned repeats sharing the same mosaic ID, ensuring distinct handling of each run.
- Updated `AppBackend` to integrate new methods for improved session handling and logging of changes in mosaic runs.

feat: enhance goto handling and telemetry state management
- Introduced `goto_search_cleared` function to determine when the firmware has exited a target search, improving response to GOTO commands.
- Updated `TelemetryTap` to maintain a synthetic idle state for `goto_released`, preventing premature state changes during ongoing searches.
- Refactored plate-solving retry logic to ensure retries only occur after confirming the search has cleared, enhancing reliability in GOTO operations.

feat: add fixed panes functionality for mosaic handling
- Introduced `fixed_panes` flag in `AppBackend` to ensure chart centers remain static during mosaic operations, enhancing accuracy in target tracking.
- Updated JavaScript logic in `services.py` and `sky_atlas.py` to respect the `fixed_panes` setting, preventing unintended movements of the viewing field while the telescope adjusts its angle.
- Improved comments for clarity on the behavior of fixed panes in relation to the chart and telescope operations.

feat: enhance session interruption handling and user feedback
- Added checks for session interruption in `_wait_for_capture_end`, `run_session`, and `_stack_mosaic` methods to raise `InterruptedError` when a stop signal is received.
- Updated `AppBackend` to handle new `stop_astro` action, ensuring proper session termination and user notifications.
- Enhanced session finish logic to differentiate between user-initiated stops and normal completions, improving clarity in session outcomes.
- Modified QML properties to reflect the new stop action, ensuring UI accurately represents session states.

feat: refactor workflow step handling and enhance autofocus logic
- Introduced `workflow_step_labels` function to streamline the generation of workflow step labels based on session parameters, improving clarity and maintainability.
- Updated `_run_session_steps` to utilize the new label generation function, ensuring consistent step ordering and handling.
- Enhanced autofocus logic to provide clearer feedback on autofocus failures and retries, improving session robustness.
