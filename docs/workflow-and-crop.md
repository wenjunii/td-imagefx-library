# Workflow ordering and Final Crop

Open the canonical `TD_ImageFX_Library.toe`, select `/project1/imagefx_demo`,
and open the **Workflow** custom parameter page.

1. **Select Stage to Move** chooses one of the 16 stages.
2. **Move Earlier / Later** moves it one place; **Move First / Last** moves it
   to an end of the chain.
3. **Current Order** shows the sequence. The visible network is laid out in
   the same order from left to right.
4. **Reset Default Order** restores the sequence below, without resetting
   artistic controls, module enables, source files or rack selections.

Default: source → Chromatic Particle Field → Calligraphic Shadow → Ink Orbit
Canvas → Ink Dream Flow → Ink Brush Flow → Ink Radial Flow → Ink Flow Fusion →
Random Particles → Glitch Fusion → Color Adjustment → Color Switch → Motion Studio → eight-slot
FX rack → Two-Image Composition → Layer Composite → Final Crop → output.

Two-Image Composition has separate 15-stage A/B workflows (everything except
recursive composition). See the [composition guide](color-switch-composition.md).
Old captured 14-stage orders are upgraded by inserting the new, disabled stages
without changing the relative order of the existing stages.

Every stage stays in the chain, even when bypassed, so its position is retained.
**Apply Video Effects** bypasses the rack at its current position. The rack moves
as one stage; its own eight Up/Down slot controls reorder effects *inside* it.
Rack auxiliary inputs are not rewired. No media or new operators are loaded by
a workflow move. Reordering feedback/stateful effects may change their history;
reset those effects if you want a clean starting frame.

The chain is rooted at the TOP named `source_image`. To use another TOP while
retaining the ordering controls, give that source this name (rename the original
first if you want to keep it), then press a workflow move/reset button. Do not
connect a downstream result back into this source or the compositor's second
input. Changing order during a show can cause a visible cut: prepare and capture
looks during rehearsal, then transition between cues.

## Layer Composite: put effects on either layer

Each layer now has an independent Source menu:

| Source | Meaning |
| --- | --- |
| Auto (File / Input) | Use its file when supplied; otherwise input 1 for backdrop or input 2 for top |
| Effects Result (Input 1) | Use the result from all stages currently before Layer Composite |
| Second TOP Input | Use an optional externally connected image/video TOP |
| Image / Video File | Use that layer's file picker; blank means transparent |
| Transparent | Hide that layer |

For effects over a backdrop, choose the backdrop file and set **Top Source** to
**Effects Result (Input 1)**. For an image over the effects, set **Backdrop Source**
to **Effects Result** and choose the top file. Opacity, grading, placement and
flicker apply only to the top. An opaque top source covers the backdrop; lower
**Top Opacity** or use an alpha-bearing source to reveal it.

“Effects Result” never refers to downstream stages. For example, moving Layer
Composite first lets later effects process the two-layer result. Disabled Layer
Composite bypasses its input 1 exactly. Unselected file paths do not block cues.

## Final Crop

Enable **Final Crop Enabled** on the demo, then select `final_crop` and its
**Crop** page. The reusable module is `touchdesigner/core/FinalCrop.tox`.

- **Aspect:** Free / Manual, Same as Source, 16:9, 9:16, square, 4:3, 3:4,
  21:9, 4:5, 5:4, 3:2, 2:3, or Custom Ratio.
- **Custom Ratio Width / Height:** proportions, not output pixel dimensions;
  enabled when the custom aspect is selected.
- **Trim Left / Right / Top / Bottom:** percentages of the original input.
  Trims apply first, then the largest selected-aspect rectangle is fitted inside.
- **Anchor X/Y:** placement of the aspect rectangle within the trimmed region;
  0 is left/bottom, 1 is right/top. It has no visible effect on an axis without
  extra space, or in Free / Manual mode.
- **Crop to Size:** removes the trimmed pixels and changes output dimensions.
- **Mask Outside (Keep Canvas):** preserves input size and position, making
  everything outside the crop transparent.
- **Fit Crop (Keep Canvas):** enlarges the cropped region to fit the original
  canvas without stretching, using transparent letterboxing when necessary.
- **Reset Crop:** neutral free/manual crop, zero trims, centered anchors, and
  Crop to Size; does not change the module's enable or workflow position.
- **Preview Final Crop:** opens the module's own output. If moved earlier,
  this preview precedes any later stages.

Pixel dimensions are rounded down when needed for aspect ratios. Overlapping
trims are reduced proportionally so at least one pixel survives on each axis;
the status reports this adjustment. Source resolution remains set on the demo's
Output page. Example: a 1920×1080 canvas cropped to square becomes 1080×1080 in
Crop to Size, or remains 1920×1080 in either fixed-canvas mode. For a projector
with a fixed canvas, prefer Mask Outside or Fit Crop and calibrate show mapping
after setting your crop. This module does not rewrite source media files.

## Show cues and compatibility

**Capture Demo Effects Into Cue** records workflow order, source selections,
crop controls, enables, and the rack preset. Each cue deck restores its own
sequence; changing the rehearsal demo does not rewire an already playing cue.
Crop controls support parameter cues such as `final_crop/Left` and
`final_crop/Aspect`. Order itself is captured per visual cue, not interpolated
as a parameter cue. Audio routing and three-output mapping remain downstream.

Old shows without order data use the **new default order** and bypass Final
Crop. This intentionally changes Layer Composite from its previous first
position. To reproduce an older look, move Layer Composite first and recapture
that cue. Do not assume an old layered cue is visually identical until rehearsed.

Validation covers portable geometry (including randomized extremes), every
source choice, native crop pixels and dimensions through 4K, stage wiring,
retained rack settings, changed order's rendered result, real deferred move/reset
button events, and cue capture/restore. It cannot guarantee frame rate for every
combination; benchmark your actual show and output hardware.
