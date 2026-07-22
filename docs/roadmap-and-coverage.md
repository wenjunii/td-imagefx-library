# Roadmap and category coverage

“Every effect” is not a finish line. Visual techniques, TouchDesigner operators, GPU APIs, hardware, and third-party tools continue to change. TD ImageFX measures coverage through a maintained taxonomy plus an authoring/update system that can absorb new methods without redesigning the library.

## Coverage rubric

| Level | Meaning |
| --- | --- |
| Cataloged | Named, categorized, sourced, licensed, and tagged; may be documentation-only |
| Prototype | Demonstrates the technique but may lack the complete effect contract |
| Packaged | Valid manifest, immutable version, declared implementation assets and dependencies |
| Native verified | Compiles/runs in a named TouchDesigner environment with reviewed preview and benchmark coverage |
| Stable | Backward-compatible interface, production documentation, representative tests/presets, and rollback-ready artifact |

Counting shader files is not meaningful coverage. A healthy category needs useful breadth, consistent controls, representative media, explicit image/state contracts, measured target-hardware behavior, and composable packages.

## v0.3.0 source catalog

The current source contains **96 current effects across 18 manifest categories**, backed by **124 immutable package versions**. Twenty-eight older versions remain beside their successors, including the twelve original v0.1 packages, fourteen temporal/simulation `1.0.0` packages, and retained Despill/Vignette versions superseded by compatible slider-response fixes.

| Category | Count | Current packages |
| --- | ---: | --- |
| Blur | 9 | Bilateral, Bokeh, Box, Chromatic, Depth-Aware, Directional, Gaussian, Radial, Tilt Shift |
| Color | 13 | Channel Mixer, Color Decision List, Curves, Duotone, Exposure, Gradient Map, HSV Shift, Levels, Lift Gamma Gain, LUT 3D, Posterize, Temperature Tint, Tone Map |
| Composite | 5 | Alpha Composite, Blend Modes, Channel Shuffle, Edge Extend, Matte Composite |
| Distortion | 10 | Bulge Pinch, Displacement Map, Flow Field Warp, Kaleidoscope, Lens Distortion, Mirror, Polar Coordinates, Ripple, Twirl, Wave Warp |
| Glitch | 5 | Block Shift, Digital Noise, RGB Split, Scan Tear, Slice Shift |
| Key | 4 | Chroma Key, Despill, Difference Key, Luma Key |
| Light | 3 | Bloom, Edge Glow, Glow |
| Lighting | 1 | Normal Lighting |
| Mask | 4 | Gradient Mask, Noise Mask, Radial Mask, Shape Mask |
| Matte | 4 | Alpha Repair, Dilate, Erode, Feather |
| Motion | 1 | Optical Flow Warp |
| Sharpen | 2 | Sharpen, Unsharp Mask |
| Simulation | 4 | Cellular Automata, Fluid Ink, Particle Advection, Reaction Diffusion |
| Spatial | 1 | Depth Parallax |
| Stylize | 10 | Edge Detect, Emboss, Frosted Glass, Halftone, Ordered Dither, Pixelate, Scanlines, Sepia, VHS, Vignette |
| Temporal | 10 | Echo, Feedback Kaleidoscope, Feedback Rotate, Feedback Trails, Frame Blend, Motion Smear, Recursive Zoom, Stutter, Temporal Glitch, Time Displacement |
| Transform | 6 | Corner Pin, Crop Feather, Fit Fill, Perspective Warp, Tile Repeat, Transform 2D |
| Transition | 4 | Directional Wipe, Luma Wipe, Noise Dissolve, Radial Wipe |

Latest-version processing coverage is 68 single-pass, 14 multi-pass, 10 temporal, and 4 simulation packages. No external-runtime adapter package is bundled.

The v0.3 source and generated artifacts are synchronized. All 96 current effects, including the 30 new effects and 14 stateful upgrades, have native compile, preview, baseline, and benchmark coverage from the recorded TouchDesigner `2025.32820` Windows build. That is **native verified** for the named environment, not a claim of stability on every production GPU, driver, resolution, or color pipeline.

## What v0.3 adds

### Production image operations

- Six transform/framing effects cover common 2D placement, crop/feather, corner pin, repeat, fit/fill, and perspective workflows.
- Five compositing effects cover two-source alpha/blend operations, dedicated-matte compositing, channel routing, and edge extension.
- Four key effects provide chroma, luma, and difference keying plus despill.
- Four matte effects provide alpha repair, morphology, and feathering.
- Four mask generators provide gradient, radial, shape, and noise masks.
- Curves, CDL, tone map, and 3D LUT extend the color pipeline.
- Bilateral, bokeh, and depth-aware blur extend focus and edge-aware processing.

All 30 are experimental while their behavior and performance are evaluated across representative images and target GPUs.

### Stateful correctness

Every temporal and simulation effect now has a `1.1.0` package with:

- private state separated from public rendering;
- declared state/render pass paths;
- real Reset behavior and reset metadata;
- deterministic or fixed-step declarations where applicable;
- warmup and known-limitation metadata;
- corrected cellular and Gray-Scott state evolution where prior implementation behavior was incomplete.

### Contract and tooling

The additive schema-v1 contract now represents semantic ports, image color/alpha/format/sampling, determinism, reset/warmup, provenance, pass scale/iterations/quality tiers, and state/render separation. The browser surfaces much of this metadata and can filter by maturity, processing model, capability, and input readiness. The rack routes second-image, displacement, depth, normal, flow, and mask buses; supports manual time; and resets all declared histories.

Updater and release work adds source/feed binding, duplicate-key and size defenses, channel/compatibility/lock reporting, deterministic transactional release preparation, release provenance/checksums, immutable-history enforcement, and a broader Python/OS CI matrix.

## Taxonomy status and gaps

| Area | v0.3 source status | Important gaps |
| --- | --- | --- |
| Transform and framing | Six dedicated packages plus distortion tools | Mesh/bezier deformation, camera-aware projection, calibration/warping adapters |
| Color and tone | 13 effects including curves, CDL, LUT, tone map | OCIO/color-management adapter, gamut mapping, selective/secondary correction, LUT asset UX |
| Blur and focus | Nine effects including bilateral, bokeh, depth-aware | Physically based depth of field, adaptive kernels, validated quality tiers |
| Detail and morphology | Sharpen/unsharp plus dilate, erode, feather, alpha repair | Distance fields, skeletonization, connected-region cleanup |
| Keying and despill | Chroma/luma/difference keys and despill | Screen modeling, edge color, garbage/core matte workflow, temporal key stabilization |
| Compositing | Alpha/matte composite, blend modes, channel shuffle, edge extend | Layer stacks, transform-per-layer recipes, premultiply audit tools, deep compositing |
| Masks | Four generated mask families | Vector/paint masks, tracked masks, signed-distance primitives, mask combination recipes |
| Distortion and lens | Broad foundational coverage | Heat haze, mesh adapters, higher-quality optics and chromatic aberration |
| Pixel/print/display style | Ten stylize tools | ASCII, stipple, engraving, CRT/phosphor, film/projector emulation |
| Glitch and corruption | Five immutable effects plus a reusable 24-style Glitch Fusion core covering sorting, datamosh-like smear, VHS/CRT, hold, dropout, compression, channel, and data corruption | True inter-frame datamosh, motion-aware corruption, codec/container adapters |
| Light and relighting | Bloom/glow, edge glow, normal lighting | Lens flare, volumetric light, environment/depth-aware relighting |
| Transitions | Four wipe/dissolve families | Burn/liquid/pixel/geometric and motion-aware transitions |
| Motion and animation | Reusable 40-style Motion Studio core covering transform, camera, wave, warp, stepped, procedural, and trailed movement | Motion tracking, curve-editor integration, path import, audio/control adapters |
| Temporal and feedback | Ten upgraded stateful packages | Long-delay buffers, slit scan, timeline/cache adapters, dropped-frame policies |
| Motion analysis | Optical-flow warp and flow-assisted effects | Vector estimation/export, tracking, stabilization, quality/fallback tiers |
| Simulation | Four upgraded reference systems | Robust pressure/fluid solver, substeps/quality tiers, validation at varied resolution/frame rate |
| Depth and spatial | Depth parallax and normal lighting | Height fields, point clouds, camera projection, volumetric slices |
| Particles and point clouds | Random-move image particles, ink-flow water particles, and particle-advection simulation | Instancing, fragmentation, depth clouds |
| Cultural and painterly style | Minimal Chinese ink work and ink wash with procedural paper/pigment controls | Curated brush libraries, calligraphy-aware stroke analysis, additional reviewed traditions |
| Segmentation and ML | Research only | Model/package metadata, offline/online trust boundaries, deterministic fallback |
| Input and control | Rack time and mix modulation | Audio, MIDI, OSC, DMX, camera/sensor adapters |
| Output and calibration | Outside effect core | Mapping, multi-display calibration, recording/streaming adapters |
| External plugins | Adapter contract only | C++ TOP ABI/signing matrix, vendor SDK policy, commercial licensing |
| Learning techniques | Gallery and authoring/architecture docs | Annotated recipes, comparisons, interactive performance labs |

## Known v0.3 limitations

- Native validation currently represents TouchDesigner `2025.32820` on Windows and one GPU/driver benchmark environment; other production targets require their own validation records.
- The 30 new production-oriented effects are experimental, not a promise of studio-qualified keying/color science.
- No bundled package currently publishes quality tiers even though the schema can validate them.
- Rack semantic routing covers image buses only; audio/control/data inputs need dedicated adapters.
- Browser input readiness is metadata-based and cannot prove upstream encoding, color space, or content quality.
- Update checking is notification-only. It does not download, install, activate, or migrate packages.
- The project does not autonomously scrape and import shaders/plugins/techniques from the internet. New sources require curation, license review, security review, and packaging.
- CI validates ordinary Python across three operating systems; native TouchDesigner/GPU validation still requires named Windows/macOS machines and drivers.

## Roadmap

### 0.4 — validation matrix and advanced spatial/control systems

- Automate multi-resolution, warmed steady-state benchmarks and native validation across named TouchDesigner, GPU, driver, and operating-system environments.
- Add representative alpha, HDR/negative, odd-resolution, auxiliary-input, and dynamic-resolution preview/test fixtures.
- Implement and measure quality tiers for the most expensive multi-pass, blur, temporal, and simulation packages.
- Add optical-flow estimation/export, tracking, stabilization, and capability-based fallbacks.
- Expand the random-move and ink-flow particle cores toward instancing, fragmentation, point clouds, depth/height fields, and camera-projection adapters.
- Provide audio, MIDI, OSC, DMX, camera, and sensor modulation examples outside immutable effect packages.

### 0.5 — curated ecosystem updates

- Signed-feed format, key-rotation procedure, and publisher trust UI.
- Curated monitors for official releases, approved shader repositories, plugins, and techniques.
- License/attribution/security review queues for discoveries.
- Staged downloads with explicit activation, restart handling, smoke tests, and transactional rollback.
- Offline bundle/export workflow for locked production projects.

### 1.0 — production contract

- Freeze and document effect API 1.x compatibility guarantees.
- Production-ready browser, rack, preset migration, project-lock migration, update, and rollback workflows.
- Supported TouchDesigner build/OS/GPU matrix with repeatable target-hardware verification.
- Authoring templates and contribution review for every supported content type.
- A stable, quality-reviewed set across color, transform, blur, key/matte/composite, temporal, simulation, spatial, and control categories.

Roadmap versions describe intent, not release promises. Security, compatibility, or regression work can move earlier than visual breadth.

## Adding a category or technique

Before creating many effects in a new area:

1. Define input/output roles and alpha/color/state behavior.
2. Choose representative low-, medium-, and high-cost techniques.
3. Create representative test media and measurable scenarios.
4. Package one reference effect through the complete lifecycle.
5. Build its `.tox`, preview, baseline, benchmark sample, and gallery entry.
6. Validate composability in the browser and rack, including missing auxiliary inputs.
7. Document source, license, permissions, dependencies, limitations, reset, and fallback behavior.

Prefer improvements that make many effects more trustworthy: contract validation, reproducible builds, color/alpha correctness, state/reset behavior, target-hardware tests, presets/examples, and rollback. A near-duplicate look should usually be a preset or parameter mode rather than another package.
