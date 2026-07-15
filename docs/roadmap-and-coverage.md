# Roadmap and category coverage

"Every effect" is not a finish line: visual techniques, TouchDesigner operators, GPU APIs, hardware, and third-party tools continue to change. TD ImageFX measures coverage with a maintained taxonomy and an authoring/update system that can absorb new methods without redesigning the library.

## Coverage rubric

Each technique progresses through these levels:

| Level | Meaning |
| --- | --- |
| Cataloged | Named, categorized, sourced, licensed, and tagged; may be documentation-only |
| Prototype | Demonstrates the technique but may lack the full effect contract |
| Packaged | Valid manifest, immutable version, declared assets and dependencies |
| Verified | Automated validation plus native TouchDesigner compile, preview, and benchmark coverage |
| Stable | Backward-compatible interface, production documentation, presets/examples, rollback-ready artifact |

Counting raw shader files is not meaningful coverage. A category is healthy when it has useful breadth, consistent controls, representative previews, measured target-hardware behavior, and composable packages.

## v0.2.0 catalog

Version 0.2.0 contains **66 current effects across 13 manifest categories**, backed by **78 immutable package versions**. The twelve original v0.1 effects retain their `1.0.0` packages beside upgraded `1.1.0` versions. Current discovery and generated artifacts use the latest version per effect ID; exact historical versions remain available to version-aware calls and project locks.

| Category | Count | Packages |
| --- | ---: | --- |
| Blur | 6 | Box Blur, Chromatic Blur, Directional Blur, Gaussian Blur, Radial Blur, Tilt Shift |
| Color | 9 | Channel Mixer, Duotone, Exposure, Gradient Map, HSV Shift, Levels, Lift Gamma Gain, Posterize, Temperature Tint |
| Distortion | 10 | Bulge Pinch, Displacement Map, Flow Field Warp, Kaleidoscope, Lens Distortion, Mirror, Polar Coordinates, Ripple, Twirl, Wave Warp |
| Glitch | 5 | Block Shift, Digital Noise, RGB Split, Scan Tear, Slice Shift |
| Light | 3 | Bloom, Edge Glow, Glow |
| Lighting | 1 | Normal Lighting |
| Motion | 1 | Optical Flow Warp |
| Sharpen | 2 | Sharpen, Unsharp Mask |
| Simulation | 4 | Cellular Automata, Fluid Ink, Particle Advection, Reaction Diffusion |
| Spatial | 1 | Depth Parallax |
| Stylize | 10 | Edge Detect, Emboss, Frosted Glass, Halftone, Ordered Dither, Pixelate, Scanlines, Sepia, VHS, Vignette |
| Temporal | 10 | Echo, Feedback Kaleidoscope, Feedback Rotate, Feedback Trails, Frame Blend, Motion Smear, Recursive Zoom, Stutter, Temporal Glitch, Time Displacement |
| Transition | 4 | Directional Wipe, Luma Wipe, Noise Dissolve, Radial Wipe |

The generated [effect gallery](gallery.md) provides previews and package metadata for the latest 66-version catalog; `gallery.json` is the programmatic index. Immutable history is represented by the version directories and manifests rather than duplicate gallery rows.

## Processing coverage

The v0.2 manifest contract distinguishes graph shape from user-facing category. These counts describe the latest 66 versions, all of which explicitly declare their processing contract. The twelve retained `1.0.0` manifests predate that object and resolve through the schema-v1 conservative defaults:

| Processing model | Count | Coverage |
| --- | ---: | --- |
| `single_pass` | 40 | Color transforms, UV distortion, print/display styling, wipes, and lightweight glitches |
| `multi_pass` | 12 | Blur, bloom/glow, sharpening, edge lighting, depth/normal, and flow-assisted spatial effects |
| `temporal` | 10 | Feedback, echo, frame blend, stutter, motion smear, recursive and time-displacement effects |
| `simulation` | 4 | Cellular, reaction-diffusion, particle, and fluid-like iterative systems |
| `adapter` | 0 | Contract reserved; no external-runtime adapter is bundled in v0.2 |

Capabilities make routing and trust needs searchable: v0.2 uses `multi_pass`, `history`, `second_input`, `transition`, `displacement`, `depth`, `normal`, `flow`, and `simulation`. The schema also reserves `audio`, `native_plugin`, `network`, and `python` for future packages that declare corresponding permissions. Relative GPU-cost labels help browsing, while the generated [benchmark report](benchmarks.md) records hardware-specific measurements.

## Taxonomy status

| Area | v0.2 status | Important gaps |
| --- | --- | --- |
| Transform and framing | Partial through mirror, polar, lens, ripple, and other distortion tools | Translate/rotate/scale/crop/fit, corner pin, projection mapping |
| Color and tone | Strong foundation with exposure, levels, white balance, channel mixing, gradient mapping, HSV, duotone, posterize | Curves, LUT workflow, color-management adapters, selective correction |
| Blur and focus | Six single/multi-pass effects | Bokeh/depth-aware blur, edge-aware blur, quality tiers |
| Detail and morphology | Sharpen, unsharp mask, edge detect, emboss | Dilate/erode, distance fields, matte morphology |
| Distortion and lens | Broad foundational coverage | Heat haze, mesh/deformation adapters, higher-quality chromatic optics |
| Pixel, print, and display style | Pixelate, ordered dither, halftone, scanlines, VHS, frosted glass | ASCII, stipple, engraving, CRT/phosphor families, film/projector emulation |
| Glitch and corruption | Five spatial/animated glitches plus temporal variants | Motion-aware datamosh-like processing, sorting, codec adapters |
| Light and relighting | Bloom/glow, edge glow, normal lighting | Lens flare, volumetric light, environment/depth-aware relighting |
| Transitions | Four wipe/dissolve families | Burn/liquid/pixel/geometric and motion-aware transitions |
| Temporal and feedback | Ten packaged temporal effects | Long-delay buffers, slit-scan, explicit timeline/cache adapters |
| Motion analysis | Optical-flow warp and flow-assisted techniques | Vector export, tracking, stabilization, quality/fallback tiers |
| Simulation | Four reference systems | More robust advection, fluid solvers, growth systems, quality controls |
| Depth and spatial | Depth parallax and normal lighting | Height fields, projection, point clouds, camera mapping, volumetric slices |
| Keying, matting, and compositing | Not yet packaged | Luma/chroma/difference keys, despill, alpha repair, blend modes, layer stacks |
| Particles and point clouds | Particle-advection simulation only | Image-to-particle, instancing, depth clouds, fragmentation |
| Segmentation and ML | Research only | Model metadata, offline/online trust boundaries, fallback behavior |
| Input and control | Rack time and mix modulation | Audio, MIDI, OSC, DMX, sensors, control-surface adapters |
| Output and calibration | Kept outside the effect core | Warping, mapping, multi-display, recording/streaming adapters |
| External plugins | Adapter contract only | C++ TOPs, vendor SDKs, signing/ABI matrix, commercial licensing |
| Learning techniques | Gallery, examples, architecture, authoring contract | Annotated recipes, comparisons, performance labs |

## v0.2.0 platform milestone

The catalog expansion is paired with infrastructure so it remains usable:

- a searchable TouchDesigner browser with category/tag filters, favorites, compatibility, processing model, GPU cost, and target-COMP creation;
- an eight-slot rack with reordering, per-slot/global bypass, reset/reload, validated presets, shared time, and sine/triangle/saw mix modulation;
- processing-aware native generation for pass chains and feedback/history graphs;
- `tools/new_effect.py` for non-overwriting single-pass, multi-pass, temporal, simulation, and adapter scaffolds;
- `tools/build_gallery.py`, `tools/check_gallery.py`, and `tools/benchmark_report.py` for generated discovery and regression/performance artifacts;
- `tools/package_release.py` for deterministic latest-66 ZIPs containing the license, third-party notices, manifest, and declared assets, plus SHA-256 metadata and release-tag-pinned update-feed staging;
- `tools/verify_repository.py` and CI coverage for all 78 immutable manifests and native entrypoints, plus latest-66 previews, baselines, benchmarks, feeds, tests, and version metadata;
- a native `.toe`, 78 versioned package `.tox` files (66 current and 12 historical), four core `.tox` files, and a notify-only Update Manager.

## Release roadmap

### 0.3 - compositing and production controls

- Keying, despill, matte refinement, morphology, blend modes, alpha repair, and layer-stack recipes.
- Transform/framing packages and calibration-friendly adapters.
- Version-aware preset migration and rack-level project-lock reporting.
- Additional preview fixtures for alpha, HDR/negative color, dynamic resolution, and temporal reset behavior.
- Broader cross-platform TouchDesigner/GPU validation and explicit quality tiers.

### 0.4 - advanced spatial and control systems

- Optical-flow analysis/export, tracking, stabilization, and capability-based fallbacks.
- Image-to-particle, instancing, depth/height-field, point-cloud, and 3D projection adapters.
- Audio, MIDI, OSC, DMX, camera, and sensor modulation examples separated from immutable effect packages.
- Extended simulation quality controls and deterministic initialization.

### 0.5 - curated ecosystem updates

- Signed-feed format, key-rotation procedure, and publisher trust UI.
- Curated source monitors for releases, shaders, plugins, and techniques.
- License/attribution review queues for discovered content.
- Isolated evaluation strategy where TouchDesigner and plugin constraints permit it.
- Staged downloads with explicit activation, restart handling, and transactional rollback.

### 1.0 - production contract

- Freeze and document effect API 1.x compatibility guarantees.
- Production-ready browser, rack, presets, project-lock migration, offline bundle, update, and rollback workflows.
- Supported TouchDesigner build/OS/GPU matrix with repeatable target-hardware verification.
- Authoring templates and contribution review for every supported content type.
- A meaningful stable set across color, spatial, temporal, compositing, control, simulation, and 3D categories.

Roadmap versions describe intent, not release promises. Security or compatibility work can move earlier than visual breadth.

## Adding a category

Before creating many effects in a new category:

1. Define its common input/output roles and alpha/color behavior.
2. Choose representative techniques at low, medium, and high GPU cost.
3. Add test media and measurable performance scenarios.
4. Scaffold and package one reference effect through the complete lifecycle.
5. Build its `.tox`, preview, benchmark sample, and gallery entry.
6. Validate composability in the browser and eight-slot rack.
7. Document external licenses, permissions, dependencies, and fallback behavior.

This prevents a large folder of examples from becoming an unusable library.

## Prioritization

Prefer work that improves many packages at once:

1. authoring contract, validator, locks, and rollback;
2. browser/rack usability, presets, and common modulation;
3. alpha, color, resolution, temporal-reset, and performance correctness;
4. missing foundational categories such as keying and compositing;
5. advanced effects with special hardware or external dependencies.

A new effect should fill a real creative gap or demonstrate a reusable method; near-duplicates should normally be presets or parameter modes.
