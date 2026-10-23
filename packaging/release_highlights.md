<u>Work In Progress Release</u>


If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

- **Fixed connection issues.** improve photo mode initialization and handling of camera states.

- **Live video after a restart.** With Auto Parameters turned on, restarting the telescope could stop the live video from coming back. That is fixed.

- **Shutter time and gain.** The exposure and gain on screen now match what the camera is actually using, including when Auto Parameters is on.

- **Stopping a job.** When you stop a slew, calibration, focus, a recording, or a session, the stop message stays on screen until the telescope has finished that job.

- **Live view and deep-sky mode.** Opening live view after a deep-sky stack brings the picture back, then returns you to deep-sky mode. The same happens when you come back from a normal photo and deep-sky was the mode you had set. A stack, tracking, panorama, or sun shot that is already running is left as it is.

- **Mosaic photos and live view.** The grid of pane photos and the live view stay with the mosaic you are shooting. They follow the current pane, stay up while that session is running, and clear when you move on to another session.
