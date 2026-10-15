<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

fix: optimize skyAtlasUrl handling to prevent unnecessary reloads
- Changed skyAtlasUrl property to be constant, avoiding notifications on app settings changes.
- Updated QML components to capture the skyAtlasUrl once, preventing reloads that could disrupt the Aladin interface.
- Enhanced the handling of map components to ensure they remain built during provider switches, improving stability.