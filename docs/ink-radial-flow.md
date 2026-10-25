# Ink Radial Flow

A separate, center-emitting variation of [Ink Brush Flow](ink-brush-flow.md).
Soft expanding liquid rings, spiral particle wisps, luminous cores and organic
wandering take inspiration from the supplied central-vortex image. Warm coral,
magenta, cyan-white and gold defaults are adjustable. No reference image,
figures, tutorial code or third-party engine are bundled.

## Optional Particle Field

**Particle Field → Particle Field Enabled** is **off by default**. With it off,
this module uses its original renderer, including the original composition,
movement, palette, textures and defaults. Turning it on applies a point-sprite
treatment to that same foreground; it does not change any flow coordinates,
timing, seed, current contours or radial phases. Turning it back off restores the
unconverted view at the current animation time, without restarting.

| Control | Purpose |
| --- | --- |
| Particle Field Enabled | Convert the completed foreground into points; off preserves the original |
| Particle Columns | 8–500 columns of point cells across the output |
| Point Shape | Round point, square pixel or cross spark |
| Point Depth Variation | Per-point size and brightness variation |
| Field Cell Fill | Fraction of occupied cells; zero removes the converted foreground |
| Field Point Size | Point radius within each cell, independent of the original pigment size |
| Point Motion Speed / Reverse | -3 to +3; try 1 to move points, negative reverses, 0 holds positions |

These controls do not change the original **Particles** page. Point Motion Speed
starts at **0** for compatibility. Set it to **1** for flow-aligned point
wandering; negative values reverse, zero holds the
current positions. Rate changes preserve the current point phase. The underlying
composition is not warped by this extra motion. Each point center moves along
a bounded local path, keeping its shape intact (not persistent physics).
The liquid/current layers, pigment wisps, glow, optional dot pattern and both
glitter layers pass through the conversion together. Paper/input background is
retained; **Transparent Ink** provides a particle foreground for compositing.
Use the existing layer switches, palette and animation controls as before.
This is a procedural particle rendering treatment, not an additional physical
particle simulation.

Old cue looks missing `Particlefieldenabled` use false and keep the original
look. New Capture/Update Cue Look operations save the switch and field settings
for Recall, GO and export. The previous always-particle revision is superseded;
original defaults and renderer behavior are restored. The point clock is saved
alongside the main animation clock for Recall, GO and export.

## Optional Feedback

The **Feedback** page is **off by default**, independent of Particle Field.
Enable it for fading motion trails on either the original flow or its point
version. Adjust **Feedback / Trail Mix**, **History Retention**, **Trail Zoom**,
**Trail Rotation**, and **Trail Offset X/Y**. **Reset Feedback** clears the trail.
Retention near 0.95 gives longer trails; 0 removes them. Mix 0 is exact bypass.
Zoom/rotation/offset describe a 60-fps history step and scale with elapsed
animation time. Pausing the animation holds the history.

Cue load, re-enable, resolution changes and large time seeks clear history.
Feedback parameters are saved, but previous GPU frames are not: a recalled
cue/export builds fresh trails from its saved starting phase. A captured still
can therefore show trails that need time to develop again. Reset after deliberate
small manual seeks when a clean first frame is required. Feedback adds two GPU
passes and a history texture; its render branch is bypassed when off. Test the complete show at output
resolution before performance.

## Run

1. Open the rebuilt `TD_ImageFX_Library.toe`, not a numbered backup.
2. Select `/project1/imagefx_demo` and turn on **Ink Radial Flow Enabled**.
3. For the pure look, turn off other modules and **Apply Video Effects**.
4. Select `/project1/imagefx_demo/ink_radial_flow` to edit its custom pages.
5. View `/project1/imagefx_demo/out1_image`.

The demo stage starts bypassed and sits between Ink Brush Flow and Ink Flow
Fusion. The reusable `touchdesigner/core/InkRadialFlow.tox` accepts any input
TOP to establish resolution. **Input Image / Paper** uses that input as a
background; **Transparent Ink** gives straight RGBA for an Over TOP. **Module
Enabled** bypasses the entire module; **Effect Mix** blends with the input.

## Every inherited control retained

All writable Ink Brush Flow values and their ranges are present: timing,
seed, composition, liquid, pigment particles, ink surface, paper, four palette
colors, all ten Brush Currents controls, animated glitter, static glitter, static
highlights, the five Static Shimmer controls and the 24 dot-pattern values.
No controls were removed.
**Timing → Animation Speed (1 = Original)** also scales the radial animation,
particles, dots and shimmer together, without changing their individual speed
controls. Default 1× preserves existing looks; 0.5× is half speed and 2× is double.
Rate changes keep the current composition; 0× holds it until speed is increased.
See the [shared timing controls](ink-dream-flow.md#controls) for range and phase behavior.

**Dot Pattern / Dot Pattern Motion** retain the shared color, spacing, shape,
folding, clock, composite and surface controls. **Follow Module Flow** uses the
radial module's coordinate deformation; selecting an ink/wash surface confines
the dots to the radiating ribbons. Both glitter layers can highlight this
pattern. See the [shared pattern controls](ink-dream-flow.md#flowing-dot-pattern).

Both glitter layers start off. Enable **Glitter Enabled** for drifting sparkles,
or **Static Glitter Enabled** for stationary grains. Static Shimmer Amount
changes their brightness, not their position; amount zero stays still and
speed zero freezes the pulse. Stars, glow, color, opacity, surface masks,
thresholds, density and size are inherited unchanged.

**Composition Center X/Y** positions the radiation origin. Zero is the frame
center, positive X right, positive Y up; coordinates are in height-relative
screen units. Pattern Scale, Rotation, Ribbon Stretch and Composition Spread
remain available. Stretch 1 gives circular rings; other values make them oval.

## Ten additional controls

| Control | Purpose |
| --- | --- |
| Center Radiation Enabled | Switch the radial variant on/off while keeping the inherited brush effects |
| Radial / Brush Blend | 1 = radial currents, 0 = the inherited brush renderer |
| Radiating Ring Frequency | Number/spacing of concentric contour cycles; higher is finer |
| Outward Speed / Inward Reverse | Positive = expand out from the center; negative = contract inward |
| Spiral Twist / Reverse | Curl the waves and particle field around the center; zero is less spiral |
| Organic Ring Wandering | Distort smooth rings into organically wandering contours |
| Central Opening Radius | Size of the softened central opening/light and center damping |
| Central Light Amount | Additional ink-colored center light, respecting Liquid Ink/ink opacity |
| Palette Atmosphere | Warm-to-wash background gradient and soft central color; only affects procedural paper |
| Outer Ring Fade | Additional soft falloff toward the outside, alongside Composition Spread |

These are on **Radial Flow** and **Radial Light**. Existing Brush Currents
controls remain separate; they still shape ribbon width, wisps, core glow and
haze. Turning Center Radiation off or blend to zero exactly gives the brush
renderer with the current inherited values, including this module's palette.

Radial motion uses the inherited **Liquid Speed** and **Particle Speed** clocks,
multiplied by Outward Speed. Set both inherited speeds to zero to freeze the
flow and pigment layers. Outward Speed zero stops phase expansion but other
wandering/curl controls can still animate. For a complete freeze use **Auto
Time off** with a fixed Manual Time, or Time Scale zero; glitter has its own
drift and shimmer controls. Negative inherited speeds also reverse time.

For geometric circles: Organic Ring Wandering 0, Spiral Twist 0, Flow Deformation
0, Dream Wandering 0, Directional Drift 0, Ribbon Stretch 1. For the reference's
softer vortex: use the defaults, increase Central Opening Radius/Haze and lower
ring frequency. Particle-only rendering is available with Liquid Ink off.

## Show cues and validation

The module has 169 writable values plus a feedback reset pulse. **Capture Look** saves eligible effect
values plus the demo enable toggle; Auto/Manual Time and module enable are
managed by the cue clock and routing rather than duplicated in the look.
Parameter cues can target `ink_radial_flow/Radialspeed`,
`ink_radial_flow/Radialspiral`, `ink_radial_flow/Centerx`,
`ink_radial_flow/Particleamount`, `ink_radial_flow/Inkcolorr`,
`ink_radial_flow/Staticglitteramount`, or any other eligible value. Cue time
drives Manual Time, including pause/resume and seeking.

`validate_ink_radial_flow.py` extends the shared rendered-control sweep with
exact radial-off/zero brush fallback, outward/inward ring phase direction,
center-safe finite pixels, all inherited glitter checks, range endpoints,
transparent output and 1080p/4K dimensions. Its temporary copies are removed,
and it never saves the live project. The full live suite includes this module
and show-cue capture/glitter checks. `validate_flow_feedback.py` separately checks
moving point support and feedback controls/reset across advancing frames.

This is a bounded deterministic procedural flow-field effect, not a physical
fluid simulation or exact reconstruction of the artwork. Smoothly periodic
angular harmonics avoid a polar seam, and a softened origin avoids a center
singularity. No warm-up is required with Feedback off. Optional Feedback builds
trails from prior frames. Rehearse the complete cue chain
with every projector; successful 4K rendering does not prove sustained
multi-output performance.
