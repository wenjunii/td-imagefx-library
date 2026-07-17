# TD ImageFX Library

[![Verify repository](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml/badge.svg)](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml)

TD ImageFX Library is a versioned, extensible image-animation and video-effects system for TouchDesigner. Effects are immutable packages with stable interfaces, explicit processing contracts, compatibility metadata, and exact-version project locking. The aim is a library that can expand without silently changing finished shows.

Version **0.3.0** contains **96 current effect IDs across 18 categories**, backed by **122 immutable package versions**. This release adds 30 production-oriented transform, compositing, keying, matte, mask, color, and blur effects; upgrades all 14 temporal and simulation effects to state/render-separated `1.1.0` packages; and strengthens the rack, browser, updater, release tooling, manifest contract, and CI foundation.

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

The v0.3 source and generated artifacts are synchronized. The recorded Windows build used TouchDesigner `2025.32820` and validated all 96 current effects with 122 versioned effect `.tox` files, four core `.tox` files, one library `.toe`, 96 previews, 96 visual baselines, and 96 benchmark samples. The build report contains zero shader, preview, or builder errors. A fresh repository run completed 153 tests successfully, with four expected Windows symlink-permission skips, and two independent 99-file release builds matched byte-for-byte. Read [TouchDesigner setup](docs/touchdesigner-setup.md) to reproduce the native build.

The generated project targets TouchDesigner 2025. Validate the exact TouchDesigner build, operating system, GPU, driver, resolution, pixel format, and color pipeline used by your production system. Python 3.11 or newer is required for repository tooling; it is not required merely to use already-built native components.

For knowledge-grounded live inspection, use the separate [Embody, Envoy, and TD knowledge integration](docs/embody-envoy-integration.md). It combines the local TouchDesigner knowledge index with Envoy's live tools and a checked ImageFX project profile. Embody runs in an ignored QA harness, never inside the canonical builder-owned `.toe`.

## Use in TouchDesigner

### Eight-slot rack

1. Open `/project1/imagefx_demo` after a successful native build.
2. Connect the primary image and any required second-image, displacement, depth, normal, flow, or mask TOPs.
3. Select `fx_rack` and open its **Rack** custom parameter page.
4. Choose up to eight effects and adjust slot enable, mix, order, bypass, reset, and modulation.
5. Leave **Auto Time** enabled for timeline-driven work, or disable it and set **Manual Time** for deterministic inspection.
6. Export/import validated JSON presets or save/load preset files inside the configured preset root.

Presets capture exact package versions, slot order, enable/mix state, modulation, manual time, and eligible effect parameters. They do not install packages, approve updates, or replace a production project lock.

### Searchable browser

Open `/project1/td_imagefx/core/fx_browser`. Search is case-insensitive across catalog metadata. Filter by category, channel, model, capability, tags, favorites, or whether the required auxiliary inputs are currently available; then sort by name, category, or relative GPU cost. Review the selected effect's preview and diagnostics before creating it in an explicit target COMP.

### Individual components

Versioned effect components live under `packages/<package-id>/<version>/tox/`. Reusable core components are generated under `touchdesigner/core/`. When importing one into another show, set **Library Root** to this checkout or a verified installed-package root.

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

The verifier expects exactly 96 current IDs and 122 immutable manifests. It compiles Python, runs tests, validates manifests and feeds, verifies the recorded hashes of the library `.toe`, all 122 effect `.tox` files, and four core `.tox` files, compares generated gallery/baseline/benchmark coverage with the latest catalog, and prevents version drift. A failure caused by stale native or generated artifacts is intentional: rebuild and review them rather than weakening the invariant.

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

TD ImageFX Library and all 122 bundled package versions are released under the [MIT License](LICENSE). Required attribution for incorporated MIT-compatible code is preserved in [Third-Party Notices](THIRD_PARTY_NOTICES.md). Third-party packages added later retain their own license and attribution metadata; inclusion in this catalog does not relicense external work.

TouchDesigner is a trademark of Derivative Inc. This independent project is not affiliated with or endorsed by Derivative.
