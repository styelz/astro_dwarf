<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

feat: enhance sky atlas functionality with new chart handling features
- Added new functions `chartField` and `fitChart` to improve chart interaction and layout management.
- Introduced `separationDeg` for calculating angular separation between celestial objects.
- Updated `viewCenteredOnTarget` to utilize the new separation logic for better accuracy.
- Implemented status messages for chart loading in the HTML file, improving user feedback during loading processes.
- Enhanced error handling and retry logic for the Aladin initialization process.