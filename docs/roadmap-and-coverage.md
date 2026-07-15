# Roadmap and category coverage

“Every effect” is not a finish line: visual techniques, TouchDesigner operators, GPU APIs, hardware, and third-party tools continue to change. TD ImageFX therefore measures coverage with a maintained taxonomy and an authoring/update system that can absorb new methods without redesigning the library.

## Coverage rubric

Each technique progresses through these levels:

| Level | Meaning |
| --- | --- |
| Cataloged | Named, categorized, sourced, licensed, and tagged; may be documentation-only |
| Prototype | Demonstrates the technique but may lack the full effect contract |
| Packaged | Valid manifest, immutable version, declared assets and dependencies |
| Verified | Automated validation plus manual TouchDesigner visual/performance test |
| Stable | Backward-compatible interface, production documentation, presets/examples, rollback-ready artifact |

Counting raw shader files is not meaningful coverage. A category is healthy when it includes useful breadth, consistent controls, test media, performance information, and composable packages.

## v0.1.0 foundation

The first release provides twelve packaged GLSL effects:

| Category | Stable foundation packages |
| --- | --- |
| Color | Duotone, Posterize, HSV Shift |
| Distortion | Wave Warp, Twirl, Kaleidoscope |
| Glitch | RGB Split, Block Shift |
| Stylize | Pixelate, Scanlines, Vignette |
| Transition | Noise Dissolve |

This set deliberately tests several contract shapes: direct color transforms, UV deformation, spatial sampling, procedural patterns/noise, time-friendly controls, and a two-source transition.

## Full taxonomy

| Area | Techniques to cover | v0.1 status |
| --- | --- | --- |
| Transform and framing | translate, rotate, scale, crop, fit/fill, tile, mirror, corner pin, polar/log-polar | Planned |
| Color and tone | levels, curves, exposure, contrast, white balance, HSV, LUT, duotone, threshold, posterize | Starter coverage |
| Blur and focus | Gaussian, box, directional, radial, zoom, bokeh, tilt-shift, luma/depth blur | Planned |
| Detail and morphology | sharpen, unsharp mask, edge detect, emboss, dilate, erode, outline, distance field | Planned |
| Distortion and lens | wave, twirl, ripple, bulge, lens, chromatic lens, heat haze, noise/displacement maps | Starter coverage |
| Reflection and symmetry | mirror, kaleidoscope, infinite tiling, polar repeats, Droste-style recursion | Starter coverage |
| Pixel and print style | pixelate, dither families, halftone, ASCII, mosaic, stipple, engraving | Starter coverage |
| Display emulation | scanlines, CRT curvature, phosphor mask, VHS, film grain, projector/LED texture | Starter coverage |
| Glitch and corruption | RGB split, block shift, datamosh-like motion, frame tear, bit/crush simulation, sorting | Starter coverage |
| Keying and matting | luma/chroma/difference key, despill, edge refinement, garbage matte | Planned |
| Compositing and masks | blend modes, channels, mattes, alpha repair, layer stacks, multipass routing | Planned |
| Transitions | dissolve, wipe, reveal, displacement, burn, liquid, pixel, luma, geometric, motion-aware | Starter coverage |
| Temporal and feedback | delay, echo, trails, stutter, freeze, frame blend, feedback transforms, slit-scan | Planned |
| Motion analysis | optical flow, motion vectors, frame difference, tracking, stabilization | Planned |
| Particles and point clouds | image-to-particles, instancing, depth clouds, fragmentation, trails | Planned |
| 3D image treatments | height fields, projection, parallax, camera mapping, volumetric slices | Planned |
| Simulation | reaction-diffusion, cellular automata, flow fields, fluid-like advection, growth | Planned |
| Generative synthesis | noise, shapes, patterns, fields, procedural textures feeding image effects | Planned |
| Segmentation and ML | person/background, depth estimation, style/feature adapters, model metadata | Research; optional dependencies |
| Input and control | audio, MIDI, OSC, DMX, mouse/touch, cameras, sensors, network events | Modulation layer planned |
| Animation | LFO, envelope, keyframe, clock/beat, trigger, sequencer, random walk, preset morph | Modulation layer planned |
| Output and calibration | color management, mapping, warping, multi-display, recording/streaming adapters | Planned; keep separate from effect core |
| External plugins | C++ TOPs, vendor SDKs, commercial packages, AI runtimes | Adapter/catalog model planned |
| Learning techniques | annotated networks, snippets, recipes, comparisons, performance labs | Planned |

## Release roadmap

### 0.2 — expand the usable TouchDesigner shelf

- Expand testing and portability coverage for the reusable effect COMPs shipped in v0.1.0.
- Add a searchable palette/browser with previews and compatibility badges.
- Extend the shipped four-slot FX Rack with reordering and preset save/load.
- Add modulation inputs for LFO, noise, audio level/spectrum, MIDI, and OSC examples.
- Add visual regression fixtures for alpha, aspect ratio, color ramps, and edge behavior.
- Exercise the public notification feed in CI and retain the local fixture for offline checks.

### 0.3 — temporal and compositing breadth

- Feedback, trails, frame delay, stutter, echo, and time-remap packages.
- Masks, blend modes, keying/matting, alpha utilities, and multilayer recipes.
- Version-aware preset migration and rack-level lock reporting.
- Performance telemetry using TouchDesigner cook/GPU information with opt-in local display only.

### 0.4 — advanced spatial systems

- Optical-flow-assisted effects and transitions.
- Image-to-particle, instancing, depth/height-field, and point-cloud adapters.
- Reaction-diffusion, cellular automata, and flow-field packages.
- Quality tiers and capability-based fallback implementations.

### 0.5 — curated ecosystem updates

- Signed feed format/key-rotation procedure and publisher trust UI.
- Curated source monitors for releases, shaders, plugins, and techniques.
- License/attribution workflow and review queue for discovered content.
- Sandboxed or isolated evaluation strategy where TouchDesigner and plugin constraints permit it.
- Stable update notifications and staged downloads with transactional rollback.

### 1.0 — production contract

- Freeze and document effect API 1.x compatibility guarantees.
- Production-ready browser, rack, presets, project lock/migration, offline bundle, update, and rollback workflows.
- Supported TouchDesigner build matrix and repeatable target-hardware verification.
- Authoring templates and contribution review process for every supported content type.
- A meaningful stable set across color, spatial, temporal, compositing, control, simulation, and 3D categories.

Roadmap versions describe intent, not release promises. Security or compatibility work can move earlier than visual breadth.

## Adding a category

Before creating many effects in a new category:

1. Define its common input/output roles and alpha/color behavior.
2. Choose representative techniques at low, medium, and high GPU cost.
3. Add test media and measurable performance scenarios.
4. Package one reference effect through the complete lifecycle.
5. Validate composability in a rack before expanding the category.
6. Document external licenses/dependencies and fallback behavior.

This prevents a large folder of examples from becoming an unusable library.

## Prioritization

Prefer work that improves many packages at once:

1. authoring contract, validator, locks, and rollback;
2. browser/rack usability and common modulation;
3. alpha, color, resolution, and performance correctness;
4. broad foundational effect categories;
5. advanced effects with special hardware or external dependencies.

A new effect should fill a real creative gap or demonstrate a reusable method; near-duplicates should normally be presets or parameter modes.
