# Per-projector mapping and masks

In **Show Control → Projection Mapping**, choose **Projector to Adjust** (1 Left,
2 Center, or 3 Right), then click **Open Mapping Controls**. The separate native
parameter panel has four pages:

- **Shape:** four-corner pinning/keystone, source crop, rotation and flips.
- **Mask:** enable a rectangle, ellipse/circle, or local image mask; adjust its
  center, width, height, rotation, inversion, level and feather/softness.
- **Edges:** soften all four edges together, or fade each edge separately.
  Edge Blend Curve changes the fade falloff for basic overlap blending.
- **Output:** resolution, track, individual blackout, brightness and gamma.

The controls are two-way links to the existing Output 1/2/3 settings, not a
second independent calibration. **Preview Mapped Projector** opens the selected
final software feed. Projector Review and the full 2x2 preview include mapping.
These preview buttons do not open physical projector windows.

## Draw a custom mask with the cursor

Choose a projector on **Projection Mapping**, then press **Draw Custom Mask
(Mouse)**. A separate editor shows that projector's current feed with a guide
grid. Blackout remains respected; the grid and handles stay visible even when
the feed is black. **Show Current Projector Feed** can be switched off for a
plain drawing guide.

1. Press **New Shape**, then click around the boundary to place points.
2. Click the first (blue) point, or **Close Shape**, to close the outline.
3. Drag a handle to move it. On a closed outline, click an edge to insert a new
   point. Select a handle and press **Delete Point** to remove it; **Undo**
   reverses a point-edit gesture.
4. Set **Soft Edge Width**, **Invert / Cut a Hole**, and **Visible Level** in the
   editor's draft controls. The overlay previews the shape and its soft boundary.
5. Press **Apply Mask** to send it to the selected projector, then **Save Show**
   in Show Control to persist calibration.

Drawing, moving points and draft controls do **not** change the live mask until
Apply. **Cancel / Reload** replaces the draft with the applied polygon; closing
the editor also does not apply it. Reopening starts from the applied points.
Apply enables the mask and selects **Custom Polygon** automatically. To bypass
the applied mask, turn off **Enable Mask** in that projector's Mask page.

One closed polygon of 3–32 points is supported per projector, including concave
shapes. Crossing, touching, duplicate or collapsed outlines cannot be applied;
the previous mask remains active. Use an image mask for multiple disconnected
regions or more complex holes. An empty/invalid active polygon fails closed to
black, even when inverted.

Unlike the rectangle/ellipse masks, the polygon is drawn in the **projector
output frame**, after corner-pin shaping. This keeps the cursor outline aligned
with the preview and allows masking physical regions independently of content
warping. The guide is normalized to the whole frame (stretched to 16:9 in the
editor); normalized coordinates still map to other output resolutions. Apply
resets the mask's center/size/rotation to neutral so the stored points match
the cursor positions. It does not reset projection corners, crop, edges, output
routing, brightness, cues or blackouts. After applying, the Mask page's transform
controls can additionally move/scale/rotate the polygon; reopening the drawing
editor shows the stored base points and applying again restores neutral mask
transforms.

## Shape adjustment

Coordinates are normalized: X increases to the right, Y increases upward.
The full-frame corners are bottom-left (0,0), bottom-right (1,0), top-right
(1,1), and top-left (0,1). Move the individual corner X/Y values to fit a planar
surface. Crossed/collapsed quadrilaterals or an empty crop are rejected: the
last valid mapping stays in use and Mapping Status explains the problem.

This is four-corner planar mapping, not a freeform mesh-warp or automatic camera
calibration system. Source crop selects content before mapping; masks remove
regions within the mapped projection. An ellipse with equal width and height
is circular in normalized canvas space; compensate width for a non-square
output aspect ratio when a physical circle is needed.

## Masks and soft edges

Masks are off by default. Enable Mask, select a shape, then adjust its position
and size. **Invert Mask** turns a visible region into a hole. **Masked Output
Level** controls the remaining visible picture. Feather fades inward at the
rectangle/ellipse boundary. Its units, and the edge fade widths, are fractions
of the mapped frame rather than pixels. Zero is a hard edge.

For complex shapes, load a static PNG/JPEG/BMP/TIFF/EXR mask. In luminance mode,
white is visible and black is blocked; gray is partial visibility, multiplied
by image alpha. Alpha mode uses only the file's transparency. Image Softness
applies a small weighted sampling filter. Image masks stretch within their
adjustable mask rectangle; use its width/height to control proportions. The
mask file remains external, and paths are local (relative paths use Libraryroot).
A missing/invalid enabled image mask fails closed to black, even when inverted;
its status is shown explicitly. Disabling the mask restores unmasked output.

All Edges Softness and the individual edge widths combine by taking the larger
width per edge. They feather the mapped picture boundary independently of the
mask. Actual projector overlap, black level, gamma and color matching must be
rehearsed on the venue hardware; black pixels do not eliminate a projector's
physical black-level light spill.

## Routing and saving

Mapping applies to direct displays and the 4K wall processor. Show Control
feeds are mapped once; the wall does not apply the mask a second time. Other
wall source modes (identical, panoramic and independent TOPs) use the same
per-projector calibration after their 1080p panel extraction. The confidence
quadrant itself is never masked; its three thumbnails show the mapped feeds.

Mapping is show-level calibration, separate from cue looks. In **Transport**,
choose a local `.json` **Show File**. After **Stop All** (and finishing any look
draft), press **Save Show**, or **Save Mapping + Cues to Show File** on the
Projection Mapping page. Both buttons use the same saver and store all three
projectors' corners, crop, rotation/flips, masks and applied polygon points,
feathering, brightness/gamma, resolution and routing with the cues. Image masks
and media remain external files; only their local paths are saved. Apply a
polygon draft before saving: an unapplied draft is not part of calibration.

Use **Load Show** to restore these settings. Loading also refreshes any open
polygon editor, turns master blackout on and disables audio; it does not open
projector windows. Missing calibration fields in an older show use the build's
defaults rather than inheriting values from the preceding show. An invalid show
is rejected before its calibration is applied. Saving over a valid existing
show creates the normal `.backup-<id>.json` sibling first.

## Reset mapping

Select **Projector to Adjust** in Projection Mapping. Individual reset buttons
are available there and on the corresponding **Open Mapping Controls** pages:

- **Reset Corner Pin:** full-frame rectangular corners.
- **Reset Source Crop:** the whole source frame.
- **Reset Rotation / Flips:** zero rotation, both flips off.
- **Reset Mask (Clear / Disable):** mask off, applied polygon and image path
  cleared, neutral position/size/inversion/level and default feather. If that
  projector's drawing editor is open, its draft is cleared too.
- **Reset Soft Edges:** all fades off and blend curve 1.
- **Reset Brightness / Gamma:** both 1.
- **Reset Resolution to 1080p:** 1920 × 1080.

**Reset ALL Mapping (Selected Projector)** combines these seven resets.
**Reset ALL Mapping (All 3 Projectors)** applies them to all outputs. A reset
in an individual projector's parameter panel always targets that projector,
even if the main selector points elsewhere. Full resets include resolution and
brightness/gamma; they do not change cue content, track selection, routing,
physical output mode, display assignments, audio or blackout switches.

Resets affect live calibration immediately but do not automatically write the
show file. **Save Show** to keep them, or **Load Show** to restore the last saved
calibration (and cues). Make live calibration edits only during appropriate
rehearsal/setup conditions: resetting a mask can expose previously hidden areas.

Native software checks: `touchdesigner/scripts/validate_projection_mapping.py`.
The validator uses disposable copies and temporary local fixtures, never the
operator's saved show file, audience windows or audio device.
