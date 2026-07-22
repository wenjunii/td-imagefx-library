# TD ImageFX Library

[![Verify repository](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml/badge.svg)](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml)

TD ImageFX Library is a versioned, extensible image-animation and video-effects system for TouchDesigner. Effects are immutable packages with stable interfaces, explicit processing contracts, compatibility metadata, and exact-version project locking. The aim is a library that can expand without silently changing finished shows.

The current source contains **96 current effect IDs across 18 categories**, backed by **124 immutable package versions**. Version 0.3.0 established the production-oriented transform, compositing, keying, matte, mask, color, blur, temporal, simulation, rack, browser, updater, release-tooling, and CI foundation; the unreleased source adds compatible Despill and Vignette slider fixes without replacing their retained predecessors.

Canonical repository: [github.com/wenjunii/td-imagefx-library](https://github.com/wenjunii/td-imagefx-library)

## Effect catalog

Package manifests under `packages/` are authoritative for versions, inputs, parameters, processing requirements, image behavior, provenance, assets, licenses, and compatibility. Discovery surfaces select the highest SemVer for each effect ID. Exact historical versions remain addressable for project locks and reproducible shows.

| Category | Count | Included techniques |
| --- | ---: | --- |
| Blur | 9 | Bilateral, bokeh, box, chromatic, depth-aware, directional, Gaussian, radial, tilt shift |
| Color | 13 | CDL, channel mixer, curves, duotone, exposure, gradient map, HSV, levels, lift/gamma/gain, 3D LUT, posterize, temperature/tint, tone map |
| Composite | 5 | Alpha composite, blend modes, channel shuffle, edge extend, matte composite |
| Distortion | 10 | Bulge/pinch, displacement and flow warps, kaleidoscope, lens, mirror, polar, ripple, twirl, wave |
| Glitch | 5 | Block and slice shifts, digital noise, RGB split, scan tear |
| Key | 4 | Chroma key, despill, difference key, luma key |
| Light | 3 | Bloom, edge glow, glow |
| Lighting | 1 | Normal lighting |
| Mask | 4 | Gradient, noise, radial, and shape masks |
| Matte | 4 | Alpha repair, dilate, erode, feather |
| Motion | 1 | Optical-flow warp |
| Sharpen | 2 | Sharpen, unsharp mask |
| Simulation | 4 | Cellular automata, fluid ink, particle advection, reaction diffusion |
| Spatial | 1 | Depth parallax |
| Stylize | 10 | Edge detect, emboss, frosted glass, halftone, ordered dither, pixelate, scanlines, sepia, VHS, vignette |
| Temporal | 10 | Echo, feedback variants, frame blend, motion smear, recursive zoom, stutter, temporal glitch, time displacement |
| Transform | 6 | 2D transform, corner pin, crop/feather, fit/fill, perspective warp, tile/repeat |
| Transition | 4 | Directional, luma, noise-dissolve, and radial wipes |

The latest-version processing view is:

| Model | Count | Meaning |
| --- | ---: | --- |
| `single_pass` | 68 | One shader stage with no retained history |
| `multi_pass` | 14 | Two or more ordered shader stages |
| `temporal` | 10 | Stateful frame processing with declared history |
| `simulation` | 4 | Stateful iterative processing with simulation history |
| `adapter` | 0 | Reserved for native, Python, network, or external-runtime adapters |

The 30 new v0.3 effects are:

- Transform: Transform 2D, Crop Feather, Corner Pin, Tile Repeat, Fit Fill, Perspective Warp.
- Composite: Blend Modes, Alpha Composite, Matte Composite, Channel Shuffle, Edge Extend.
- Key: Chroma Key, Luma Key, Difference Key, Despill.
- Matte: Dilate, Erode, Feather, Alpha Repair.
- Mask: Gradient Mask, Radial Mask, Shape Mask, Noise Mask.
- Color: Curves, Color Decision List, Tone Map, LUT 3D.
- Blur: Bilateral Blur, Bokeh Blur, Depth-Aware Blur.

These packages remain intentionally `experimental`: native compilation, preview, baseline, and benchmark coverage have passed, but representative media, edge cases, production resolutions, color pipelines, GPUs, and drivers still require project-specific qualification. A large catalog is not the same as a production guarantee.

## v0.3 production foundations

### Richer package contracts

Schema version 1 now supports additional, backward-compatible metadata:

- semantic input/output roles for source, second image, mask, depth, normal, flow, displacement, state, and data routing;
- explicit input/working/output color spaces, scene/display/data reference, alpha representation, pixel-format policy, and sampling behavior;
- deterministic, seeded, time-dependent, external, or nondeterministic execution declarations;
- temporal reset strategy, reset target, resolution/input-change behavior, and warmup frames;
- separate `state_pass` and `render_pass`, pass scale, iteration count, and optional quality tiers;
- provenance, source revision/attribution, declared examples and presets, and known limitations.

Older schema-v1 manifests remain loadable. If they omit a new field, the UI labels that part of the contract as legacy or unspecified instead of inventing a production guarantee.

### Correct stateful execution

All ten temporal and four simulation effects now have immutable `1.1.0` packages. They declare separate private state and public render passes, a working reset pulse, deterministic or fixed-step behavior where promised, and explicit reset/warmup metadata. The runtime uses retained history rather than exposing simulation state as the display result. Older `1.0.0` versions remain available for locked projects.

### Rack routing and control

The eight-slot rack has one primary image path plus six semantic auxiliary buses: second image, displacement, depth, normal, flow, and mask. Inputs route by manifest role/semantic; unsupported non-TOP or unknown auxiliary roles fail visibly. Stateful Reset targets every declared history node, including a compatibility fallback for legacy components. **Auto Time** can be disabled and replaced with an explicit **Manual Time**, and the default slot binding uses rack modulation correctly.

### Browser diagnostics

The browser source adds channel, processing-model, capability, input-readiness, available-input, and sorting controls to the existing search/category/tag/favorite filters. Selected-effect details expose descriptions, parameters, image contracts, compatibility confidence, required buses, quality metadata, and a preview path. The native build initializes and validates the first 512×288 preview, and later selections reload it automatically. Effect components are loaded lazily instead of keeping the entire catalog resident.

## Repository map

| Path | Purpose |
| --- | --- |
| `packages/` | Immutable packages at `packages/<package-id>/<version>/` |
| `schemas/` | Machine-readable package, feed, state, and lock contracts |
| `src/tdimagefx/` | Validation, registry, compatibility, updater, archive, state, lockfile, and CLI logic |
| `touchdesigner/` | TouchDesigner extensions, callbacks, native builder, and reusable core component sources |
| `integrations/embody/` | Project-scoped TD knowledge, Envoy live-QA contract, and safe harness setup |
| `tools/` | Effect scaffolding, release packaging, gallery/benchmark generation, and repository verification |
| `.github/workflows/` | Cross-platform verification, immutable-history checks, and prepare-only release automation |
| `tests/` | Unit and integration checks that do not require a live TouchDesigner process |
| `docs/` | Architecture, setup, authoring, security, gallery, benchmarks, coverage, and references |

## Install and build

Clone the complete repository; do not copy a `.toe` by itself:

```console
git clone https://github.com/wenjunii/td-imagefx-library.git
cd td-imagefx-library
```

The current source and generated artifacts are synchronized. The recorded Windows build used TouchDesigner `2025.32820` and validated all 96 current effects with 124 versioned effect `.tox` files, nine core `.tox` files, one library `.toe`, 96 previews, 96 visual baselines, and 96 benchmark samples. The build report contains zero shader, preview, or builder errors. A fresh repository run completed 172 tests successfully, with four expected Windows symlink-permission skips, and two independent 99-file release builds matched byte-for-byte. Read [TouchDesigner setup](docs/touchdesigner-setup.md) to reproduce the native build.

The generated project targets TouchDesigner 2025. Validate the exact TouchDesigner build, operating system, GPU, driver, resolution, pixel format, and color pipeline used by your production system. Python 3.11 or newer is required for repository tooling; it is not required merely to use already-built native components.

### Credential safety

Never commit API keys, access tokens, passwords, private keys, `.env` files,
machine-local MCP configuration, the Embody Envoy registry, or licensed/private
media. Those paths are ignored, and the repository verifier now performs a
redacted high-confidence scan of every tracked file. Suspected values are never
printed into local or GitHub Actions logs.

Before staging, scan the complete tracked tree:

```console
python tools/check_credentials.py
```

After staging, scan the exact files intended for the next commit:

```console
python tools/check_credentials.py --staged
```

This guard complements GitHub secret scanning; it does not replace careful
review. If a credential is ever committed, revoke it immediately before
removing it from Git history. See [the security policy](SECURITY.md).

Reusable core components use component-relative callback and feedback-state targets, so slot selection, Parameter Execute actions, and temporal history continue to work after a `.tox` is imported, moved, or renamed.

The effect browser now reloads its selected preview one frame after project
startup or component creation. This prevents a valid gallery file from
appearing black/transparent until the first manual selection change.

For knowledge-grounded live inspection, use the separate [Embody, Envoy, and TD knowledge integration](docs/embody-envoy-integration.md). It combines the local TouchDesigner knowledge index with Envoy's live tools and a checked ImageFX project profile. Embody runs in an ignored QA harness, never inside the canonical builder-owned `.toe`.

The integration includes `integrations/embody/check_td_bridge.py`, which starts
the project-scoped MCP server through the official client, confirms the
`td-imagefx-library` contract, waits for the 3,022-chunk knowledge index, and
optionally requires a clean live Envoy connection. This distinguishes an open
TouchDesigner window from an actually reachable Envoy endpoint.

The project-scoped MCP configuration follows the active instance in the
ImageFX harness's local `.embody/envoy.json` registry, including automatic port
changes after rapid TouchDesigner restarts. Before any Envoy tools are exposed,
the bridge verifies both `/project1/td_imagefx` and
`/project1/imagefx_demo`. A FlexGPU, FlexShow, or other open TouchDesigner
project is rejected, while the local knowledge and project-contract tools
remain available.

### Which TouchDesigner project should I open?

Open `TD_ImageFX_Library.toe` to use, demonstrate, or perform with the generated
library. Open the ignored
`integrations/embody/local/TD_ImageFX_DevHarness.toe` for effect development,
Embody/Envoy control, MCP-assisted inspection, and live regression testing.
Do not add Embody to the generated library project.

The harness does not synchronize directly into `TD_ImageFX_Library.toe`.
Synchronization is source-driven:

1. Finalize harness experiments in the tracked manifests, shaders, extensions,
   callbacks, or builder scripts.
2. Run repository and live validation.
3. Run `touchdesigner/scripts/build_project.py` from a separate blank,
   disposable TouchDesigner project to regenerate the canonical `.tox` and
   `.toe` artifacts.

`install_dev_harness.py` performs the other direction: tracked source and
compiled core components are loaded into the harness. It never saves either
project. Parameter or network edits that exist only in the harness remain
local.

The installer now requires the exact unnumbered harness identity. If
TouchDesigner opens `TD_ImageFX_DevHarness.toe` but its title shows
`TD_ImageFX_DevHarness.1.toe`, `.2.toe`, or another numbered name, use
**File > Save Project As**, select `TD_ImageFX_DevHarness.toe`, approve
replacement only for that ignored harness, close TouchDesigner, and reopen the
unnumbered file. Never approve replacement of `TD_ImageFX_Library.toe`.

## Use in TouchDesigner

### Output resolution

Select `/project1/imagefx_demo` and open its **Output** custom parameter page.
**Resolution Preset** provides:

- **HD 1920 x 1080**, the default;
- **4K UHD 3840 x 2160**; and
- **Custom**, using the adjustable **Custom Width** and **Custom Height**.

Custom dimensions accept 16 through 8192 pixels per axis. The generated demo
source and `out1_image` update immediately when the preset or custom values
change. A replacement Movie File In, Video Device In, or other source TOP keeps
its own processing resolution through the effect chain, while the final output
is resized to the selected delivery resolution.

4K and large custom sizes increase GPU memory and cook time substantially,
especially with eight rack slots, particles, ink, Glitch Fusion, Color
Adjustment, and Motion Studio trails enabled. On a laptop RTX 3080 Ti, start
Motion Studio at one trail sample and raise it only after checking frame time.
Qualify the chosen combination on the target machine before using it in a
performance.

### Ink-flow fusion

The reusable `InkFlowFusion.tox` module combines two adjustable image treatments with an independently adjustable water-current particle layer:

- **Minimal Ink Work** produces restrained monochrome line work, dry-brush texture, warm paper, and controlled tonal marks.
- **Minimal Ink Wash (Shui-mo)** produces softer diffused washes, layered pigment values, pooled edges, granulation, and paper fibers.

Select `/project1/imagefx_demo/ink_flow`. On **Ink Visuals**, use **Ink Visual Enabled** and **Ink Style**, then tune mix, pigment strength, edge detail, wash spread, granulation, and paper texture. On **Ink Palette**, set the paper and pigment colors. On **Water Particles**, use **Water Particles Enabled**, then tune columns, size, flow speed/direction/distance, cross-current turbulence, random wandering, stretch, shape, opacity, ink mix, and seed. **Auto Time**, **Time Scale**, and **Manual Time** support live or deterministic animation.

The water-current field defaults to a sparse 32-column composition and accepts 8 through 500 columns. Increase it for denser pigment fields only after checking the target resolution and frame-time budget.

The visual and particle switches are independent:

| Ink Visual | Water Particles | Module result |
| --- | --- | --- |
| Off | Off | Original input |
| On | Off | Selected ink treatment |
| Off | On | Original input plus water-current particles |
| On | On | Water-current particles composited with the selected ink treatment |

The demo-level **Ink Flow Module Enabled** switch bypasses the entire module. The separate **Random Particles Enabled** switch controls the existing `ParticleRandomMove.tox` stage after ink flow, **Glitch Module Enabled** controls `GlitchFusion.tox` after both particle stages, **Color Adjustment Enabled** controls the dedicated grading stage, **Motion Module Enabled** controls `MotionStudio.tox`, and **Apply Video Effects** controls the eight-slot rack after Motion Studio.

### Random-move particles

The reusable `ParticleRandomMove.tox` module turns any image TOP into a GPU
particle field. Every particle samples the source image and follows
deterministic seeded motion. Its controls now cover:

- density, size variation, aspect, rotation, spin, softness, and hollow amount;
- eight shapes: Circle, Square, Diamond, Triangle, Hexagon, Ring, Star, and Line;
- eight motion modes: Orbit, Wander, Wave, Swirl, Fountain, Rain, Explosion,
  and Flow;
- speed variation, move amount, jitter, two-axis drift, turbulence, scatter,
  pulse amount/rate, and seed;
- source blend, per-particle source-sample offset, opacity variation,
  background RGBA, and automatic or manual time; and
- particle tint RGBA, tint amount, hue/hue variation, saturation, and
  brightness.

With **Ink Flow Module Enabled**, **Glitch Module Enabled**, and **Color
Adjustment Enabled** off, the random-particle and rack switches produce:

| Random Particles Enabled | Apply Video Effects | Result |
| --- | --- | --- |
| Off | Off | Original image |
| Off | On | Original image through the eight-slot rack |
| On | Off | Random-moving particles only |
| On | On | Random-moving particles through the eight-slot rack |

Select `/project1/imagefx_demo/particle_random_move` to tune random-particle
controls. **Effective Time** is intentionally read-only because it reports the
resolved Auto/Manual time; animate with **Auto Time**, **Time Scale**, or
**Manual Time**. The default 96-column grid produces about 5,000 particles for
a 16:9 source. The shader uses a fixed 5x5 search neighborhood and bounded
displacement, so work remains bounded; reduce **Particle Columns** first when
qualifying 4K or multi-output shows.

**Particle Columns** ranges from 8 to 500. At 16:9, the 500-column
maximum represents about 140,000 particles; use it when the target resolution
and frame-time budget have been qualified.

### Glitch Fusion

The reusable `GlitchFusion.tox` module adds 24 bounded, single-pass GPU glitch
styles: RGB split, block shift, slice tear, digital noise, pixel sort,
datamosh, VHS tracking, scanline jitter, macroblock, signal dropout, frame
jitter, rolling sync, channel swap, color quantize, bit crush, mosaic
scramble, wave interference, static snow, CRT corruption, horizontal hold,
vertical hold, data bend, edge corruption, and a layered Glitch Fusion mode.

Use the demo-level **Glitch Module Enabled** toggle to bypass the complete
module. Select `/project1/imagefx_demo/glitch_fusion` to choose **Style** and
adjust **Effect Mix**, **Glitch Intensity**, **Glitch Speed**, block size, slice
density, displacement, jitter, smear, RGB split, digital noise, dropout,
scanlines, tracking, compression, color shift, color levels, edge corruption,
and seed. **Auto Time**, **Time Scale**, and **Manual Time** support live or
deterministic animation. The module preserves source alpha and returns the
original input when disabled or when Effect Mix is zero.

Glitch Fusion sits after Ink Flow and Random Particles, but before Color
Adjustment, Motion Studio, and the eight-slot rack. This lets it corrupt the
original image, either particle render, or their combined result; the color
module can grade that result and Motion Studio can animate it before **Apply
Video Effects** determines whether the rack also processes it.

### Color adjustment

The reusable `ColorAdjustment.tox` module provides one bounded GPU pass for
technical correction and creative color styling. Select
`/project1/imagefx_demo/color_adjustment`, then use:

- **Color Adjustment** for whole-module bypass, dry/wet mix, and RGB inversion;
- **Primary** for exposure, global offset, brightness, contrast, contrast
  pivot, saturation, vibrance, and hue;
- **White Balance** for temperature and green/magenta tint;
- **Tonal Range** for input black/white, gamma, per-channel RGB lift and gain,
  shadows, midtones, highlights, blacks, whites, shadow toe, and highlight
  shoulder;
- **Color Balance** for independent shadow, midtone, and highlight RGB balance
  with optional luminance preservation;
- **Detail** for clarity and dehaze;
- **Creative Color** for monochrome, sepia, posterization, fade, solarization,
  and soft thresholding;
- **Duotone** for independent shadow/highlight colors and blend amount; and
- **Color Overlay** for an RGBA overlay with Normal, Multiply, Screen, Overlay,
  Soft Light, Hard Light, Color, Difference, Darken, Lighten, Color Dodge,
  Color Burn, Linear Dodge, Linear Burn, Exclusion, and Luminosity blend modes;
  and
- **Film** for monochrome or colored grain plus adjustable vignette amount,
  midpoint, feather, and roundness.

All controls load neutral except the stored overlay color/amount, which are
inactive until **Color Overlay Enabled** is on. Source alpha is preserved. Use
the demo-level **Color Adjustment Enabled** toggle to bypass the whole module;
**Adjustment Mix** at zero is also an exact dry path. The duotone and overlay
color alpha sliders contribute to their respective blends instead of acting as
unused storage. The module remains active whether or not the separate
eight-slot rack is enabled.

### Motion Studio

The reusable `MotionStudio.tox` module supplies 40 bounded GPU motion styles:
pan, diagonal pan, drift, orbit, figure eight, bounce, pendulum, swing, shake,
handheld, jitter, float, breathe, zoom pulse, infinite zoom, dolly zoom,
rotate, spin pulse, spiral, vortex, twist, horizontal wave, vertical wave,
radial wave, ripple, liquid, wobble, slither, flow field, heat haze, parallax,
perspective sway, rolling shutter, whip pan, stop motion, step jump, conveyor,
tunnel, kaleidoscope motion, and elastic motion.

Use the demo-level **Motion Module Enabled** toggle for an exact whole-stage
bypass, then select `/project1/imagefx_demo/motion_studio`. Its **Motion** page
provides style, dry/wet mix, amount, speed, phase, direction, center, zoom,
rotation, frequency, warp, randomness, seed, kaleidoscope segments, and
stepped-motion controls. Choose Linear, Sine, Smooth, Smoother, Bounce, or
Elastic easing and Hold, Repeat, Mirror, or Transparent edge handling. **Auto
Time**, **Time Scale**, and **Manual Time** support live animation and
repeatable still-frame tuning.

Optional motion trails use a fixed maximum of five samples in the same GLSL
pass. Keep **Trail Amount** at zero or **Trail Samples** at one for the lowest
cost; increase them only when the target resolution, GPU, and frame-time budget
have been qualified. Disabled, zero mix, and zero amount return the upstream
RGBA image unchanged.

### Eight-slot rack

1. Open `/project1/imagefx_demo` after a successful native build.
2. Choose **HD 1920 x 1080**, **4K UHD 3840 x 2160**, or **Custom** on the **Output** page.
3. Drag a still or movie into the demo to create a **Movie File In TOP**. Disconnect the generated `source_image` from input 0 of `ink_flow`, then connect your Movie File In TOP there.
4. Keep your source connected to `fixture_image_b` if you want its derived clean/alternate image, or replace rack input 1 with a different TOP for transitions, composites, and Difference Key.
5. On `imagefx_demo`, choose whether **Ink Flow Module Enabled**, **Random Particles Enabled**, **Glitch Module Enabled**, **Color Adjustment Enabled**, **Motion Module Enabled**, and **Apply Video Effects** are on.
6. Select `ink_flow` to tune ink visuals and water particles, `particle_random_move` for the separate random-particle stage, `glitch_fusion` for its 24 glitch styles, `color_adjustment` for grading and overlays, `motion_studio` for its 40 motion styles, or `fx_rack` and open its **Rack** custom parameter page to choose up to eight effects.
7. Adjust slot enable, mix, order, bypass, reset, and modulation. Leave **Auto Time** enabled for timeline-driven, particle, and feedback motion.
8. View `out1_image`, then export/import validated JSON rack presets if needed.

The canonical demo supplies deterministic fixtures to all six auxiliary rack inputs so every package can be auditioned immediately. In a production network, replace those fixtures with the required media: a second image/clean plate, displacement, depth, normal, flow, or mask TOP. Color-correction and transform packages use neutral defaults by design; open the loaded `slot1` through `slot8` component and adjust its custom effect parameters to see and tune the operation.

Presets capture exact package versions, slot order, enable/mix state, modulation, manual time, and eligible effect parameters. They do not install packages, approve updates, or replace a production project lock.

For the exact selection-callback regression check, run
`touchdesigner/scripts/validate_rack_selection.py` in the development harness.
It snapshots the complete rack preset, changes every `Slot1effect` through
`Slot8effect` menu to a known alternative package, verifies that the loaded
component and stored package changed, restores each original selection, and
finally imports the snapshot again. The script reports to the ignored
`build/envoy-validation/rack-selection.json` file and never saves the project.
The read-only `validate_live_project.py` audit also checks that every current
menu selection matches its loaded slot package and that the relocated Parameter
Execute DAT targets its owning rack.

For the complete effect-control regression check, run
`touchdesigner/scripts/validate_all_effect_parameters.py` in a disposable
development harness. It loads every latest package into rack slot 1, sweeps
all 502 manifest numeric components, every toggle, rack mix, effective time,
and per-effect **Time Scale** against rendered pixels at 320 x 180, validates
range/clamp metadata and finite output, and writes the ignored
`build/envoy-validation/all-effect-parameters.json` report. It restores the
full rack preset, demo routing, resolution, source time, and timeline state in
a `finally` block and never saves the project.

Inside loaded `slot1` through `slot8` components, **Enable**, **Mix**,
**Effective Time**, and package-status fields are intentionally read-only
because the rack owns them. Adjust the corresponding slot controls on
`fx_rack`; per-effect **Time Scale** remains editable and multiplies the rack's
global time. This locking prevents rack-driven values from looking like
malfunctioning local sliders.

### Searchable browser

Open `/project1/td_imagefx/core/fx_browser`. Search is case-insensitive across catalog metadata. Filter by category, channel, model, capability, tags, favorites, or whether the required auxiliary inputs are currently available; then sort by name, category, or relative GPU cost. Review the selected effect's preview and diagnostics before creating it in an explicit target COMP.

### Individual components

Versioned effect components live under `packages/<package-id>/<version>/tox/`. Reusable core components, including `InkFlowFusion.tox`, `ParticleRandomMove.tox`, `GlitchFusion.tox`, `ColorAdjustment.tox`, and `MotionStudio.tox`, are generated under `touchdesigner/core/`. When importing one into another show, set **Library Root** to this checkout or a verified installed-package root.

## Author and validate effects

Create a non-overwriting package scaffold:

```console
python tools/new_effect.py chromatic-smear "Chromatic Smear" stylize --model single_pass --gpu-cost medium
python tools/new_effect.py echo-lite "Echo Lite" temporal --model temporal --capability history --history-frames 1
```

The scaffolder emits the richer v0.3 image, determinism, temporal, provenance, and processing fields where applicable. Edit the manifest and shader sources, run `touchdesigner/scripts/build_project.py` inside TouchDesigner, inspect `build/touchdesigner-build-report.json`, then regenerate derived documentation:

```console
python tools/record_native_validation.py
python tools/build_gallery.py
python tools/check_gallery.py --update
python tools/benchmark_report.py
python tools/verify_repository.py
```

Only use `check_gallery.py --update` after visually approving every changed preview. Benchmark values are hardware-specific measurements, not universal performance promises.

Stateful gallery images use deterministic state-shader iteration from controlled reset/prior-frame fixtures for reproducible review; shipped effects reset from black and use live Feedback TOP history, so validate timing-sensitive behavior in TouchDesigner as well as comparing PNGs.

## Release preparation

Stage a release candidate with deterministic package ZIPs, a validated feed, release provenance, and `SHA256SUMS`:

```console
python tools/package_release.py --release-tag v0.3.0
```

Release construction is transactional: it validates the complete immutable package set, stages only the latest 96 versions, pins manifest links to the exact release tag, rejects unsafe paths/symlinks and malformed identifiers, and exposes no partial output when a build fails. With `--verify-source-binding`, release-affecting package, legal, runtime, and packager inputs must also be clean, so uncommitted bytes cannot be attributed to a tag. The command does not publish, sign, install, or activate anything. The manual GitHub workflow binds the supplied tag to the selected source revision, checks immutable history against the previous reachable release tag, and prepares and attests artifacts without creating a public release.

The generated `tdimagefx.github.catalog` feed declares the broadest maturity channel present in the release so mixed stable/beta/experimental catalogs remain valid. Each package keeps its own channel, and clients still apply their configured channel when selecting update candidates.

## Automatic update checks

The Update Manager checks only explicitly configured local or HTTPS JSON feeds on a worker thread. It validates bounded JSON without duplicate keys; rejects credentials, queries, fragments, malformed ports, and origin-changing redirects; binds a feed to its exact configured source; enforces channel hierarchy; reconciles duplicate package candidates by project-lock source then configured trust; reports compatibility confidence; compares installed and project-locked versions; records feed digests; safely redacts malformed URLs; and prevents stale checks from overwriting newer status. Verified package staging checks every declared entrypoint, processing pass, changelog, example, and preset before immutable registration.

Checks remain **notification-only**: they never download, install, activate, or execute discovered code. The default first-party source is:

```text
https://raw.githubusercontent.com/wenjunii/td-imagefx-library/main/registry/update-feed.json
```

For an offline checkout, disable `tdimagefx.github.catalog` and enable `tdimagefx.local` in `config/update_sources.json`. The updater does not crawl GitHub, Derivative sites, forums, or the wider web for arbitrary effects, shaders, plugins, or techniques. See the [updater, security, and version-locking policy](docs/updater-security-version-locking.md).

## Verify a checkout

Run the dependency-free repository check with Python 3.11 or newer:

```console
python tools/verify_repository.py
```

The verifier expects exactly 96 current IDs and 124 immutable manifests. It compiles Python, runs tests, validates manifests and feeds, verifies the recorded hashes of the library `.toe`, all 124 effect `.tox` files, and nine core `.tox` files, compares generated gallery/baseline/benchmark coverage with the latest catalog, and prevents version drift. It also cross-checks this README's test and catalog claims, the ImageFX project context, and the live validator's package/build constants against checked source and native records. A failure caused by stale native or generated artifacts is intentional: rebuild and review them rather than weakening the invariant.

GitHub Actions runs verification on Windows, macOS, and Linux with Python 3.11 and 3.13, and separately rejects modifications to package versions already present in repository history.

## Production rules and limitations

- Never let an update replace a package version referenced by a show.
- Keep project locks with the project and updater cache/state outside the lock.
- Treat shaders, Python, `.tox` files, and compiled plugins as executable content with different risk levels.
- Test alpha, HDR/negative color, aspect ratio, dynamic resolution, reset, and auxiliary-input behavior on representative media.
- Record the TouchDesigner build, OS, GPU, driver, color space, resolution, frame rate, and quality tier used for validation.
- Relative GPU-cost labels and benchmark data are discovery hints only. The recorded driver exposed CPU submission timing and texture memory, but not per-operator GPU execution timing.
- The new v0.3 effects passed the recorded native compile, preview, baseline, and benchmark checks but remain experimental pending production-specific media, edge-case, resolution, color-pipeline, GPU, and driver qualification.
- The updater discovers metadata; it is not a general plugin marketplace or an automatic installer.

## Documentation

- [Architecture](docs/architecture.md)
- [TouchDesigner setup](docs/touchdesigner-setup.md)
- [Embody, Envoy, and TD knowledge integration](docs/embody-envoy-integration.md)
- [Effect authoring contract](docs/effect-authoring-contract.md)
- [Generated effect gallery](docs/gallery.md)
- [Runtime benchmark report](docs/benchmarks.md)
- [Updater, security, and version locking](docs/updater-security-version-locking.md)
- [Roadmap and category coverage](docs/roadmap-and-coverage.md)
- [Official references](docs/official-sources.md)
- [Changelog](CHANGELOG.md)
- [Issue tracker](https://github.com/wenjunii/td-imagefx-library/issues)

## Project status and license

The source tree is versioned as **v0.3.0**. Public contracts continue to use package manifest `schema_version: 1`, effect API `fx_api: "1.0"`, SemVer package versions, and the `stable`, `beta`, and `experimental` channels. The new schema-v1 fields are additive; breaking changes still require an explicit migration path and appropriate version change.

TD ImageFX Library and all 124 bundled package versions are released under the [MIT License](LICENSE). Required attribution for incorporated MIT-compatible code is preserved in [Third-Party Notices](THIRD_PARTY_NOTICES.md). Third-party packages added later retain their own license and attribution metadata; inclusion in this catalog does not relicense external work.

TouchDesigner is a trademark of Derivative Inc. This independent project is not affiliated with or endorsed by Derivative.
