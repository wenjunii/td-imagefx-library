# Ink Dream Flow

A separate, original GPU module inspired by the motion in `Timeline 1.mp4`:
curling liquid marbling, fine pigment particles, soft wet edges and dry fibers.
The default palette is indigo ink on warm procedural Xuan paper. Reference
video and artwork are not copied into this repository.

## Run it

1. Open the newly built **TD_ImageFX_Library.toe** (not a numbered backup).
2. Select `/project1/imagefx_demo`. Turn **Ink Dream Flow Enabled** on.
3. For the pure new look, turn off the other module toggles and **Apply Video Effects**.
4. Select `/project1/imagefx_demo/ink_dream_flow` to edit its custom pages.
5. View `/project1/imagefx_demo/out1_image`.

The reusable component is `touchdesigner/core/InkDreamFlow.tox`. In another
network, connect a TOP to establish its output resolution. Its **Module Enabled**
toggle is independent; in the demo it follows the parent's **Ink Dream Flow Enabled**
control. It starts bypassed in the demo to preserve existing looks.

## Controls

| Page | Controls |
| --- | --- |
| Ink Dream Flow | Master enable, dry/wet mix, background selection |
| Timing | Auto/manual time, reversible time scale, repeatable random seed |
| Composition | Center X/Y, scale, rotation, coverage, spread, ribbon stretch |
| Liquid Flow | Separate liquid switch, deformation, speed/reverse, direction, drift, vortex curl, turbulence, wandering |
| Ink Surface | Marbling, filament frequency, deep ink, diluted wash, bleeding edges, pigment pooling, granulation, dry brush |
| Particles | Separate particle switch, opacity, density, size, softness, speed/reverse, random wandering, flow distortion, spread, streak length |
| Glitter | Separate switch, amount, density, grain size/softness, brightness, RGBA color, surface choice, threshold, edge softness, spread |
| Glitter Motion | Independent drift speed/reverse, direction, flow distortion, wandering, seed, shimmer amount/speed |
| Glitter Highlights | Star amount, length, rotation, glow amount/radius |
| Paper | Fiber strength, grain scale, edge aging |
| Palette | Independent RGBA for deep ink, wash, particles and paper |

**Background** offers procedural paper, the input image (for actual Xuan paper
or scenic artwork), or transparent ink. Set **Mix** to 1 for a pure transparent
layer; lower mix values intentionally blend in the input. Paper controls apply
only to procedural paper. Use an Over TOP for the straight-alpha transparent output.

Liquid, pigment and glitter work together or separately. Density zero, particle opacity zero,
or particle-color alpha zero removes particles. Particle **Size** and **Density**
are independent artistic values, not a particle count. Composition transforms
also stretch the grains. Particle **Spread** distributes pigment beyond the
liquid, including when ink coverage is low.

With **Auto Time** on, **Time Scale = 0** freezes at effective time zero. To hold a particular moment,
disable **Auto Time** and set **Manual Time**. Set liquid and particle speeds to zero to
freeze their layers. Particles use the same family of flow fields but retain an
independent clock. With glitter enabled, also set **Glitter Drift Speed** and
**Shimmer Speed** to zero to freeze its motion. Seed and time reproduce a frame without simulation warm-up.
Speed edits can jump phase; animate Manual Time for a continuous speed ramp.

## Glitter

Glitter starts **off**. On `/project1/imagefx_demo/ink_dream_flow`, open the
**Glitter** page and turn **Glitter Enabled** on. **Glitter Surface** selects
deep ink, diluted wash, pigment particles, or their combination. It respects
those layers' switches, strength and color alpha. **Surface Threshold** selects
stronger regions; **Surface Edge Softness** softens that selection.
**Glitter Outside Ink** spreads highlights into the composition envelope: at
zero, empty paper stays empty even with Threshold = 0; at one, glitter can render
on its own with the liquid and pigment layers off.

**Glitter Grain Size** uses output pixels, with a fixed 16-pixel grid and
independent density. **Amount** controls coverage; **Brightness** controls the
highlight color intensity. Switch off, Amount = 0, Density = 0, Brightness = 0,
or glitter-color alpha = 0 removes glitter exactly. Brightness above one brightens
highlights and can clip to white in standard 8-bit output.

**Glitter Motion** has separate drift and shimmer clocks. Drift direction,
flow distortion and wandering control grain movement; Shimmer Amount = 0 gives
steady highlights. Drift speed zero holds the grains while shimmer can still
animate, and shimmer speed zero holds their sparkle while drift can still move.
The surface can keep moving with liquid/pigment even when glitter clocks are zero.
The glitter seed selects a repeatable grain pattern. Composition controls shape
the surface, while glitter grain sizing remains based on the output resolution.

**Glitter Highlights** adds sparse cross-shaped stars and soft halos. Star length
and glow radius scale with grain size, with bounded support around each cell.
For a quiet silver ink look, start with Amount 0.5, Density 0.4, Size 1.6,
Brightness 1.4, Shimmer 0.5 and Star Amount 0.1. For gold, set the glitter color
to approximately RGB (1.0, 0.72, 0.3). These are manual settings.

## Starting looks

- **Quiet dream:** defaults, then Coverage 0.32 and both speeds 0.12.
- **Liquid marbling:** Coverage 0.72, Spread 1.2, Marbling 0.95, Vortex Curl 2.2,
  Filament Frequency 32, Particle Opacity 0.25.
- **Dispersing pigment:** liquid off, Particle Size 2.5, Density 0.7, Spread 0.6,
  Flow Distortion 0.85, Random Wandering 0.7.

These are manual settings, not additional preset buttons.

## Show cues and validation

Show Control's **Capture Look** includes this module and its demo switch.
Parameter cues accept e.g. `ink_dream_flow/Coverage`,
`ink_dream_flow/Flowamount`, `ink_dream_flow/Inkcolorr`,
`ink_dream_flow/Glitteramount`, and `ink_dream_flow/Glittercolorr`.
Show time drives manual time during an active cue, including pause/resume.
In show cues, adjust **Liquid Speed** and **Particle Speed** for motion rate;
the cue clock owns manual time, so the Auto Time scale does not apply there.
Glitter drift and shimmer speeds also work under the cue clock; Capture Look
includes every glitter value and its enable switch.
The cue loader preserves each module's enable expression when resetting effect
parameters, so captured on/off choices remain live when decks are reused.

`validate_ink_dream_flow.py` creates a temporary test copy, sweeps all 85 writable
control, checks bypass, alpha, zero endpoints, glitter surface isolation,
independent glitter clocks and deterministic seeking, and
renders at 1080p and 4K. It removes only its own test container and never saves
the TOE. It is included in `validate_live_suite.py`.

This bounded procedural flow-field renderer is **not a physical fluid simulation**.
It recreates the visual character, not exact video frames. Pixel checks do not
certify sustained performance for three 4K projectors: rehearse the full cue
chain on the actual display setup.
