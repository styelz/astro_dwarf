<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

feat: update visibility of colour settings based on theme lock status
- Made the COLOURS setting group visibility dependent on the themeLocked property, enhancing user interface responsiveness to theme changes.
feat: enhance session template and capture handling
- Added new fields to the SessionTemplate class for action and timing configurations, including burst and timelapse settings.
- Introduced a `stored_capture_fields` function to streamline the retrieval of session action and timing data from both dictionaries and session objects.
- Updated various components in the AppBackend and storage modules to utilize the new capture fields, ensuring consistent handling of session data across the application.
- Modified the SessionDialog and SessionsPage to improve user interaction with session creation and management.