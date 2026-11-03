<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

- Media can stack selected astronomy sessions that share a camera, binning, filter, and target. The telescope saves the result as a new session under RESTACKED.
- A running megastack shows how long it has been going, and refreshing the album keeps that status.
- Cancelling a connect that has not reached the telescope finishes right away.
- Temperature stays blank until the sensor reports a real reading.
- DWARF II, DWARF 3, and DWARF Mini each use their own shutter limits and filter wheel. DWARF II stops at 15s on tele and 1s on wide and has no Duo-Band. DWARF 3 goes to 120s. Mini goes to 180s, and its dark shutter is not offered as a filter.

## Code signing policy

This project uses the [SignPath Foundation](https://signpath.org/) for code signing.

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org/).

Windows installers are the files submitted for that signature. The certificate is issued to SignPath Foundation, and the private key stays on SignPath’s hardware security module. Each release is built from this public repository and approved before it is signed.

- Committer, reviewer, and approver: [styelz](https://github.com/styelz)

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

[Privacy policy](https://github.com/styelz/astro_dwarf/blob/main/privacy.md)
