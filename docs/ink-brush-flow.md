# Ink Brush Flow

A separate module based on Ink Dream Flow, with interconnected, curling,
fibrous particle currents inspired by the **right-hand output** in the supplied
particle-method video. It retains the Chinese ink-brush/wash series palette,
paper texture, breathing room and broken pigment edges. The reference video
is not redistributed; no tutorial code or third-party particle engine is bundled.

## Run

1. Open the newly rebuilt `TD_ImageFX_Library.toe`, not a numbered backup.
2. Select `/project1/imagefx_demo` and enable **Ink Brush Flow Enabled**.
3. For the pure look, disable other module toggles and **Apply Video Effects**.
4. Select `/project1/imagefx_demo/ink_brush_flow` to edit the custom pages.
5. View `/project1/imagefx_demo/out1_image`.

The reusable `touchdesigner/core/InkBrushFlow.tox` accepts an input TOP to
establish resolution. In the demo it is between Ink Dream Flow and Ink Flow
Fusion. Both Dream and Brush modules start bypassed, preserving existing looks.
For layering rather than replacement, choose **Input Image / Paper** background
or lower the module's **Effect Mix**. **Transparent Ink** provides straight RGBA
for an Over TOP.

## Full inherited controls

Every parameter and range in [Ink Dream Flow](ink-dream-flow.md) is retained:
master bypass/mix, time/seed, composition, independent liquid and particles,
ink surface, four RGBA palette colors, paper, animated glitter and the separate
**Static Glitter / Static Highlights** layers. A few defaults differ for the
brush-current look (wider coverage, finer grains, longer streaks).
Both glitter layers start off; enable either, both, or neither.

## Brush Currents page

| Parameter | Purpose |
| --- | --- |
| Brush Currents Enabled | Switch off the extra brush renderer while retaining the inherited effects |
| Interconnected Current Amount | Blend the ribbon-network structure into the liquid field |
| Current Network Scale | Number/spacing of winding cells; higher means finer networks |
| Current Ribbon Width | Widen/narrow the currents |
| Particle Brush Length | Lengthen pigment flecks; inherited Particle Streak Length also contributes |
| Fine Brush Fibers | Add broken ink fibers and fine particle wisps |
| Extra Brush Curl | Additional curling of the currents and grain orientation |
| Current Contrast | Sharpen/soften the current network |

For subtle traditional ink, use the defaults on warm paper. For a bright
reference-like look, choose a dark Paper Color and pale blue Ink, Wash and
Particle colors; lower Granulation/Dry Brush for softer wisps. For particles
alone, switch Liquid Ink off. These are manual settings, not preset buttons.
Size and density are artistic controls, not an explicit simulated particle count.

## Cue integration and testing

**Capture Look** saves all 113 writable values and the demo toggle. Parameter
cues can target `ink_brush_flow/Brushweb`, `ink_brush_flow/Brushwidth`,
`ink_brush_flow/Particleamount`, `ink_brush_flow/Inkcolorr`,
`ink_brush_flow/Staticglitteramount`, or any other eligible value. Cue time
drives the inherited manual clock, including pause/resume and repeatable seeking.

`validate_ink_brush_flow.py` uses the shared Dream validator to sweep every
control's accepted values, ranges and rendered response, with additional brush
isolation. It checks both glitter layers, time freeze/replay, transparent output,
master bypass/mix and native 1080p/4K rendering. Tests create and remove their
own temporary copies; they do not save your project.

This is a bounded deterministic **procedural flow-field renderer**, not a
physical fluid/particle simulation or an exact reconstruction of the video's
network. Long streaks and both glitter layers cost more GPU time. Rehearse the
full cue chain and all connected projectors before selecting show resolution;
successful 4K rendering is not a guarantee of sustained multi-output frame rate.
