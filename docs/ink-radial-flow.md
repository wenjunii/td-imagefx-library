# Ink Radial Flow

A separate, center-emitting variation of [Ink Brush Flow](ink-brush-flow.md).
Soft expanding liquid rings, spiral particle wisps, luminous cores and organic
wandering take inspiration from the supplied central-vortex image. Warm coral,
magenta, cyan-white and gold defaults are adjustable. No reference image,
figures, tutorial code or third-party engine are bundled.

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

All 120 writable Ink Brush Flow values and their ranges are present: timing,
seed, composition, liquid, pigment particles, ink surface, paper, four palette
colors, all ten Brush Currents controls, animated glitter, static glitter, static
highlights and the five Static Shimmer controls. No controls were removed.

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

The module has 130 writable values. **Capture Look** saves eligible effect
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
and show-cue capture/glitter checks.

This is a bounded deterministic procedural flow-field effect, not a physical
fluid simulation or exact reconstruction of the artwork. Smoothly periodic
angular harmonics avoid a polar seam, and a softened origin avoids a center
singularity. No feedback warm-up is required. Rehearse the complete cue chain
with every projector; successful 4K rendering does not prove sustained
multi-output performance.
