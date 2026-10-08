# Color Switch and Two-Image Composition

Both modules are optional stages in the main workflow and start **off**. They do
not use the rejected dance/mocap prototypes. Open the newly built
`TD_ImageFX_Library.toe`, select `/project1/imagefx_demo`, and enable the desired
module on the **Demo** page. Older open TOEs will not acquire new modules until
you open the rebuilt file.

## Replace a selected color

Enable **Color Switch Enabled**, then enter `color_switch`.

1. Set **Color to Select** to the input color and **Replace With Color** to its
   replacement. The color swatches open TouchDesigner's standard color picker.
2. Alternatively, open **Sample Color → View Input for Sampling**, set **Sample
   Position X/Y**, and press **Sample Input Color at Position**. Coordinates are
   normalized: X=0 left, X=1 right; Y=0 bottom, Y=1 top. Sampling is a single
   explicit readback, never a per-frame tracking operation.
3. Start with **RGB Color Distance**, then increase **Color Tolerance** until the
   desired region is selected. **Selection Edge Softness** blends the boundary.
4. **Hue (Across Shades)** selects a hue regardless of brightness. The saturation
   cutoff prevents gray/white regions from being selected accidentally; use RGB
   matching to replace black, gray or white.
5. **Preserve Original Shading** keeps relative light/dark detail. At zero, selected
   pixels become the exact replacement color. **Replacement Amount** blends with
   the original. **Preview Selected Pixels** displays the selection mask; turn it
   off before using the image in the show.

Input alpha is preserved. Sampling a transparent or invalid pixel leaves the
selected color unchanged and reports the reason. This is color-based selection,
not object recognition: similarly colored regions are replaced together.
Pure black uses the chosen replacement color even with shading preservation on,
because black has no relative brightness to preserve.

## Two images on one screen

Enable **Two-Image Composition Enabled**, then enter `image_composition`.

- On **Image A** and **Image B**, choose the two media files. Images and silent
  videos are supported. Auto prefers the file; otherwise A uses upstream input 1
  and B uses optional input 2. File, input and transparent choices are explicit.
- **Layout** offers Side by Side, Top/Bottom, Picture in Picture, Overlay, and
  Manual Rectangles. Split presets are 1:1, 2:1, 1:2, 3:1 and 1:3; Manual Split
  uses **Manual A Share**. A is left or top by default; **Swap** exchanges positions.
- Each **Crop A/B** page has free/manual trims, source aspect, 16:9, 9:16, square,
  4:3, 3:4, 21:9, 4:5, 5:4, 3:2, 2:3, and a custom ratio. Cropping happens before
  that source's effects. Overlapping trims retain at least one pixel.
- **Fit** letterboxes, **Fill** crops to fill its frame, and **Stretch** may distort
  the image. The Placement pages control fit/fill anchors and horizontal/vertical
  flips. In Manual Rectangles, Left/Bottom and Width/Height are canvas fractions.
- Opacity, visibility, gap, outer margin, background color/alpha and overlap order
  remain adjustable. **Reset Layout Only** does not reset media, crops or effects.

Click **Edit Image A Effects** or **Edit Image B Effects**. Each opens an independent
workflow with the existing dedicated effects, Color Switch, and an eight-slot FX
rack. Enable the desired effects on that branch's **Effects** page, then select the
individual child module to edit it. Branch effects start off, including all rack
slots. The two chains can be reordered independently on their **Workflow** pages.
Recursive Two-Image Composition is deliberately excluded from the branches.

The main Workflow page can move composition before or after other effects. Stages
before composition affect its upstream input, not separately loaded image files.
Stages after it affect the combined screen. Final Crop can still crop the complete
result. The existing Layer Composite remains available for backdrop/foreground
overlays and flicker; it has not been replaced.

Output follows input 1's canvas dimensions (the main HD/4K/Custom setting), or
1920x1080 when imported alone. Crop and layout do not change that canvas size.
Two active effect chains cost more than one: rehearse actual effects, media and
projector resolution before show use. Effects requiring auxiliary depth/flow/mask
inputs still need those inputs configured in the corresponding branch rack.

## Video, cues, and saved looks

The A/B playback pages provide play/pause, loop, speed/reverse, seek, restart and
reload. In manual-time mode, each file follows `start + manualTime * speed`;
play/restart are disabled. Embedded video audio is not routed to speakers: use
the existing audio cues. Static images naturally do not move with playback.

Capture Look stores both branches, their orders/racks, media paths, composition,
and color selection. Recall/Update/New/Cancel work off-air as before. Reused decks
clear omitted file paths and reset omitted settings. Old looks preserve their
previous relative order, with the two new stages inserted disabled.

Examples of parameter-cue targets:

- `color_switch/Tocolorr`
- `image_composition/Aopacity`
- `image_composition/Split` (select Manual Split first)
- `image_composition/a_effects/calligraphic_shadow/Glitteramount`
- `image_composition/b_effects/color_switch/Tolerance`

Media paths remain local. Cue preflight and readiness include selected branch
media; disabled/hidden or unselected files do not block playback. No credentials,
source photos, videos or show files are copied into the public source tree.

## Verification

Portable tests cover layout bounds/presets, control contracts, media selection,
path validation, cue targets and legacy-order migration. Native checks in
`validate_color_composition.py` exercise real GPU pixels, independent A/B effects,
crop/fit behavior, toggles and numeric endpoints in temporary copies, never the
saved show settings. The consolidated deferred runner also checks live file
loading, both video transports, pulse delivery, branch rack selection, and cue
round trips. Generate the standard AV fixture as shown in the README first.
These tests do not certify multi-output show performance.
