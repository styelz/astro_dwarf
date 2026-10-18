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

