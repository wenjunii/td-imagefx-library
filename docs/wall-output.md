# 4K wall output: three projectors + confidence monitor

Open the canonical `TD_ImageFX_Library.toe` and select
`/project1/imagefx_demo/wall_output`. Its **Sources** and **Wall Output** custom
parameter pages control the new module. This is downstream of the visual
workflow, not an effect that can be moved into a cue's processing chain.
The existing wide `show_control/audience_atlas` remains available for direct
multi-display setups; do not use that atlas for the 2x2 processor.

## Fixed pixel map

One borderless, native-pixel **3840x2160** Perform Window carries four tiles.
Coordinates below are from the **top left**; ranges exclude their upper bound.

| Output | Tile | X range | Y range | Destination |
| --- | --- | --- | --- | --- |
| 1 | Top-left | 0–1920 | 0–1080 | Left projector |
| 2 | Top-right | 1920–3840 | 0–1080 | Center projector |
| 3 | Bottom-left | 0–1920 | 1080–2160 | Right projector |
| 4 | Bottom-right | 1920–3840 | 1080–2160 | Confidence monitor |

`p1_out`, `p2_out`, `p3_out`, and `comp_monitor_out` are 1920x1080.
`layout_master_4k` packs them with exact integer texel reads, not interpolated
sampling across a tile boundary. It is a GLSL TOP implementing the specified
2x2 layout, with no gutters, scaling or reversed scan order at the packing step.
`out1_wall_4k` is the final TOP; `wall_window` displays it.

## Choose sources

| Source Mode | Operation |
| --- | --- |
| Show Control (default) | Uses `show_control/out1_projector` through `out3_projector`, after cue mixing, corner pins, grades, crops, edge fades and blackouts. Choose Identical / Panoramic / Independent on Show Control's Routing page as before. |
| Identical | Copies **Master / Panorama TOP Path** to all three projectors. Default `../out1_image` is the demo's finished effect workflow. |
| Panoramic | Divides Master TOP into exact normalized intervals [0, 1/3), [1/3, 2/3), [2/3, 1]. Use a 5760x1080 master for three native 1920x1080 slices. Other sizes are scaled and visibly reported. |
| Independent | Uses the three **Projector TOP Path** fields, each naming an image/video/render TOP. Relative paths are relative to `wall_output`; absolute operator paths also work. |

Use **Fit** to letterbox, **Fill** to crop, or **Stretch** to distort an input
into its tile. These operate before packing. Native 1920x1080 feeds (or a native
5760x1080 panorama) stay 1:1. All output tiles remain fixed at 1080p even if an
upstream render is 4K. Existing Show Control output sizes should normally be
1920x1080 for this processor. SelectTOPs, movie inputs and camera/render outputs
are valid sources; missing/non-TOP/local feedback paths fall back to black and
are reported. Do not connect wall output back into any upstream source graph.

Video remains live: the module does not cache frames or alter cue timing/audio.
Decode media through existing ImageFX/Show Control or your own Movie File In TOPs.
In Panoramic mode use genuinely wide media or design the effect canvas at 5760x1080;
stretching an ordinary 16:9 clip into it does not create extra picture content.

## Confidence monitor

Q4 shows the three **actual final projector feeds**, including blackout, as
three 640x360 previews at the top. A 1920x400 strip would stretch 16:9 images if
filled; this implementation uses 1920x360 to preserve their shape. Below it are
FPS, frame cook time, GPU memory in MB, last-frame dropped-frame count, source
mode, blackout/calibration state, and show transport/time/selected-cue status.
The selected cue is the next/editor selection, not necessarily the currently
running cue (several tracks can run together).

**Enable Confidence Quadrant** can black Q4 independently. **Show Diagnostics**
hides the text while retaining the previews. Diagnostics never enter Q1–Q3.
Missing performance channels display `N/A`, not a fabricated zero. Frame time
is TouchDesigner process cook time, not measured HDMI/processor latency.

## Safe hardware setup

1. Set the PC's processor/EDID output to **3840x2160**, extended desktop, with a
   refresh rate supported by the complete GPU/cable/adapter/processor chain.
2. Configure the processor to **2x2**, with output order TL, TR, BL, BR. Disable
   zoom, overscan, bezel compensation, rotation and aspect crop for initial testing.
   Connect outputs 1–3 to the left/center/right projectors and 4 to the monitor.
3. Click **Check Display / Refresh List**. Read **Connected Displays**, then set
   **4K Processor Display Index** to the correct TouchDesigner index. It may not
   match the number in Windows display settings. Default -1 is deliberately
   unassigned. A non-3840x2160 display is rejected, and the primary desktop is
   protected unless **Allow Primary Display** is explicitly enabled.
4. Keep **Projector Blackout** on, then press **OPEN 4K WALL (Perform Mode)**.
   The Window COMP uses Fill, native DPI pixels, no borders, no cursor and V-sync.
   Opening this window closes this demo's legacy wide audience window.
5. Enable **Numbered Calibration Pattern**, then release wall blackout. In Show
   Control mode also release its **Master Blackout**. Verify large labels 1/2/3,
   yellow top-left and cyan bottom-right markers, and uncut white outside borders.
   Q4 must show only the confidence interface. Fix any processor swaps or scaling.
6. Turn calibration off and run a real cue. Rehearse all three pictures and audio,
   including blackouts, pause/resume, display reconnection and heavy transitions.
   **CLOSE 4K WALL** or Escape closes the output window without stopping cue audio.

Enable Projector Feeds off and Projector Blackout on both black only Q1–Q3.
Blackout wins over the test pattern. In Show Control mode its Master Blackout
also overrides wall calibration, so diagnostics cannot accidentally defeat an
audience safety control. Startup forces wall blackout on, calibration off and
the wall window closed. Changing display selection/primary override closes it;
check and reopen explicitly. Closing the window does not stop cues or mute audio.

Wall settings are stored in the TOE when you save it; the current **Save Show**
JSON contains cue/show mapping, not these wall-specific settings. A canonical
rebuild resets wall defaults. Keep a separate local performance TOE alongside
the canonical TOE, or explicitly set library/rack/browser Root Folder controls
to this checkout when saving elsewhere: blank Root Folder means the TOE's own
folder. Back up show JSON/media; never overwrite the canonical library with the
dev harness. Performance TOEs and private media should not be added to Git.

There was no connected 4K processor during implementation validation. Software
pixel tests do not establish cable bandwidth, refresh stability, processor output
order, projector sync or show-safe GPU/audio performance. This fixed four-tile
output gives **1080p per destination**, not 4K per destination. A suitable
TouchDesigner license is required for UHD TOPs; an EDID emulator does not remove
a software resolution limit or increase hardware bandwidth.

## QLab / external playback

This repository's Show Control section is native TouchDesigner, not QLab itself.
For externally authored QLab media use the same **top-left pixel rectangles**
above when preparing a 3840x2160 master, and verify with the calibration pattern.
No QLab workspace, Mac output or network video routing is created by this module.
If QLab plays a prepacked master directly to the processor, Q4 must be authored
in that master; it will not contain TouchDesigner's live statistics automatically.
Only one application should own the processor's physical video output at a time.

## Rebuild and validate

`build_show_control.py` creates the wall module **after** taking the cue deck
template snapshot. Both the canonical builder and harness installer use it;
preloaded cues therefore do not duplicate fullscreen windows or diagnostics.
The controller is embedded in the TOE and source fingerprints are included in
the native validation record. Nothing in the dance-puppet experiment is used.

`validate_wall_output.py` uses a disposable copy and synthetic TOPs to check
UHD dimensions, exact quadrant pixels/seams, panoramic slicing, independent and
identical routing, fit modes, confidence isolation, controls, calibration,
missing-input fallback and fail-closed opening. The complete live suite includes
it. Hardware opening is deliberately not part of automated validation.
`validate_deferred()` additionally exercises real frame-delivered button pulses
and the display-policy change callback in a disposable copy.

References: [Perform CHOP](https://derivative.ca/UserGuide/Perform_CHOP),
[Window COMP](https://docs.derivative.ca/Window_COMP),
[Monitor class](https://derivative.ca/UserGuide/Monitor_Class),
[GLSL input sampling](https://docs.derivative.ca/Write_a_GLSL_TOP).
