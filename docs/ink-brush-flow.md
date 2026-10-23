# Ink Brush Flow

A separate module based on Ink Dream Flow, now prioritizing the **right-hand
output** in the supplied particle-method video: soft blue-white currents,
fine curling particle wisps, luminous cores and dark cavities. The previous
hard cellular seams, dry brush hatching and warm-paper default are replaced.
Chinese ink-brush styling is optional, not imposed on the reference look.
The module ID/name stays unchanged for existing networks and cues.
The reference video is not redistributed; no tutorial code or third-party
particle engine is bundled.

## Run

1. Open the newly rebuilt `TD_ImageFX_Library.toe`, not a numbered backup.
2. Select `/project1/imagefx_demo` and enable **Ink Brush Flow Enabled**.
3. For the pure look, disable other module toggles and **Apply Video Effects**.
4. Select `/project1/imagefx_demo/ink_brush_flow` to edit the custom pages.
5. View `/project1/imagefx_demo/out1_image`.

The reusable `touchdesigner/core/InkBrushFlow.tox` accepts an input TOP to
establish resolution. In the demo it is between Ink Dream Flow and the optional
Ink Radial Flow stage, followed by Ink Flow Fusion. Dream, Brush and Radial
modules start bypassed, preserving existing looks.
For layering rather than replacement, choose **Input Image / Paper** background
or lower the module's **Effect Mix**. **Transparent Ink** provides straight RGBA
for an Over TOP.

## Full inherited controls

Every parameter and range in [Ink Dream Flow](ink-dream-flow.md) is retained:
master bypass/mix, time/seed, composition, independent liquid and particles,
ink surface, four RGBA palette colors, paper, animated glitter and the separate
**Static Glitter / Static Highlights / Static Shimmer** layers. Defaults now use
a deep navy background, pale-blue current/particle colors, finer particles,
soft edges, matching liquid/particle speeds and no dry brush/granulation.
Both glitter layers start off; enable either, both, or neither.
**Timing → Animation Speed (1 = Original)** independently scales all generated
motion and shimmer: 0.5× is slower, 2× is faster, and 1× preserves existing looks.
It retains the individual layer speeds and current composition when changed;
0× holds the current frame and increasing it resumes without a jump.
See the [shared timing controls](ink-dream-flow.md#controls).
The **Dot Pattern / Dot Pattern Motion** pages add a separately switchable
flowing-dot sheet with 24 adjustable values, including RGBA components. Choose
overlay/masked dots or dots on their own background; Brush's current field
drives **Follow Module Flow**. Both glitter layers can highlight the dots.
See the [shared pattern controls](ink-dream-flow.md#flowing-dot-pattern).

## Brush Currents page

| Parameter | Purpose |
| --- | --- |
| Particle Currents Enabled | Switch off the extra current renderer while retaining the inherited Dream effects |
| Soft Current Amount | Blend smooth contour sheets into the liquid and particle masks |
| Current / Cavity Scale | Set spacing of currents and dark pockets; higher gives finer structures |
| Soft Current Width | Widen/narrow the softly fading ribbons |
| Wispy Streak Length | Set the integration span; inherited Particle Streak Length also contributes |
| Fine Particle Wisps | Blend ordinary grains into short curling, converging particle trails |
| Current Curl | Bend the field and change the balance of curl versus convergence |
| Current Contrast | Sharpen/soften ribbon density and strand contrast |
| Current Core Glow | Brighten luminous liquid cores; values above one can clip to white |
| Soft Current Haze | Add a softer wash-colored luminous layer around currents |

The new defaults provide the dark, luminous reference-inspired look. Reduce
Core Glow for a quieter look, increase Particle Softness for smoother wisps,
or increase Current Width/Haze for cloudier currents. For traditional ink,
choose warm Paper Color and dark Ink/Wash/Particle colors, lower Core Glow
to zero, and add Granulation/Dry Brush. For particles alone, switch Liquid Ink
off; the core glow and haze respect that switch. These are manual settings,
not preset buttons. Old captured looks retain their saved palette/controls;
reset the module's custom values to get the new defaults, then recapture.
Size and density are artistic controls, not an explicit simulated particle count.

**Static Shimmer** has the same five controls as Ink Dream Flow: Amount,
Speed/Reverse, Sharpness, Minimum Brightness and Phase Variation. Grains stay
stationary while their brightness twinkles. Amount zero restores the old still
texture; Speed zero freezes its pulse independently. See [static glitter](ink-dream-flow.md#static-glitter).

## Cue integration and testing

The module has 144 writable values. **Capture Look** saves eligible effect
values and the demo toggle, with time managed by the cue clock. Parameter
cues can target `ink_brush_flow/Brushweb`, `ink_brush_flow/Brushwidth`,
`ink_brush_flow/Particleamount`, `ink_brush_flow/Inkcolorr`,
`ink_brush_flow/Staticglitteramount`, `ink_brush_flow/Staticglittershimmer`,
`ink_brush_flow/Brushglow`, or any other eligible value. Cue time
drives the inherited manual clock, including pause/resume and repeatable seeking.

`validate_ink_brush_flow.py` uses the shared Dream validator to sweep every
control's accepted values, ranges and rendered response, with additional brush
isolation. It checks both glitter layers and stationary shimmer, time freeze/replay, transparent output,
master bypass/mix and native 1080p/4K rendering. Tests create and remove their
own temporary copies; they do not save your project.

This is a bounded deterministic **procedural flow-field renderer**, not a
physical fluid/particle simulation or an exact reconstruction of the video's
network. Smooth density contours and bounded curl-field trail sampling replace
the cellular renderer, without accumulated state or simulation warm-up.
Fine trail integration and both glitter layers cost more GPU time. Rehearse the
full cue chain and all connected projectors before selecting show resolution;
successful 4K rendering is not a guarantee of sustained multi-output frame rate.

For a center-emitting variation retaining all these controls, use the separate
[Ink Radial Flow](ink-radial-flow.md) module. This does not change Brush's renderer
or its saved control values.
