<u>Work In Progress Release</u>

If you find any bugs or have any suggestions for the application, please create an issue here:
[https://github.com/styelz/astro_dwarf/issues/new/choose](https://github.com/styelz/astro_dwarf/issues/new/choose)

- Media has a DARKS library. It lists the dark sets stored on the telescope, and TAKE DARKS saves a new set of 10 frames for the camera, exposure, gain, and size you choose. Tracking stops while that set is saved. Deleting a set removes it from the telescope, and a later stack that needs it will ask again. DWARF Mini has no wide library.
- A stack skips the dark prompt when the telescope already has a matching set. It retries the start once. If the telescope still refuses that set, the stack fails instead of asking you to take the same darks again.
- TRACK with a sky target locked slews to that target and tracks against Earth's rotation. With no target locked, TRACK is object tracking only, and a warning says it will not follow the stars. Tracking stays unavailable while a megastack is running.
- A new stack starts at zero after a disconnect. A leftover frame count from the run that just ended is not counted as the first frame of the next one.
- The stack preview keeps its frames when another app has focus. A hidden or minimized window still drops them.
- Resuming a mosaic uses the stack count saved on that pane. A reconnect no longer substitutes the capture default of 50 frames.
- A plate-solve that is still searching stays on that search until it finishes or the 10 minute cap.
- If the control link drops during a mosaic pane, the app rejoins that pane and reads the telescope again. A frozen frame count is not treated as a shutter that is still open, so the remaining panes are not skipped.
- The media viewer can zoom a still up to 8×. The scroll wheel and a pinch zoom toward the pointer, a drag pans the frame, and a double-click resets the view. Album tiles and the viewer show the file size.
- After a custom mosaic, the live view stays on PREPARING STITCH until the pane stills have downloaded. The mosaic is then stitched on its own.
- A privacy policy is published with the project. It describes what stays on this computer and which lookups leave it.
