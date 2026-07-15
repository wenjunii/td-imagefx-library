# TD ImageFX Library

[![Verify repository](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml/badge.svg)](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml)

TD ImageFX Library is a versioned, extensible image-animation and video-effects system for TouchDesigner. Each effect is an immutable package with a stable interface, processing metadata, compatibility requirements, and an exact-version project-lock model. The goal is a library that can grow without silently changing finished shows.

Version **0.2.0** expands the foundation to **66 current effect IDs backed by 78 immutable package versions**, adds multi-pass, temporal, and simulation processing, and ships a searchable browser plus an eight-slot rack with presets, reordering, bypass, and modulation. The twelve original v0.1 effects remain available at `1.0.0` beside their upgraded `1.1.0` versions. The package, registry, compatibility, update-feed, archive, state, and lockfile layers remain independently testable outside TouchDesigner.

Canonical repository: [github.com/wenjunii/td-imagefx-library](https://github.com/wenjunii/td-imagefx-library)

## Effect catalog

The current catalog contains 66 effects across 13 categories. Package manifests under `packages/` are authoritative for versions, parameters, inputs, licenses, processing requirements, assets, and compatibility. There are 78 version directories and manifests: browser, rack, gallery, native-build, and benchmark views select the latest version of each effect ID, while exact historical versions remain addressable for locked projects.

| Category | Count | Included techniques |
| --- | ---: | --- |
| Blur | 6 | Box, chromatic, directional, Gaussian, radial, tilt shift |
| Color | 9 | Channel mixer, duotone, exposure, gradient map, HSV, levels, lift/gamma/gain, posterize, temperature/tint |
| Distortion | 10 | Bulge/pinch, displacement and flow warps, lens, mirror, polar, ripple, twirl, kaleidoscope, wave |
| Glitch | 5 | Block and slice shifts, digital noise, RGB split, scan tear |
| Light | 3 | Bloom, edge glow, glow |
| Lighting | 1 | Normal lighting |
| Motion | 1 | Optical-flow warp |
| Sharpen | 2 | Sharpen, unsharp mask |
| Simulation | 4 | Cellular automata, fluid ink, particle advection, reaction-diffusion |
| Spatial | 1 | Depth parallax |
| Stylize | 10 | Edge detect, emboss, frosted glass, halftone, ordered dither, pixelate, scanlines, sepia, VHS, vignette |
| Temporal | 10 | Echo, feedback variants, frame blend, motion smear, recursive zoom, stutter, temporal glitch, time displacement |
| Transition | 4 | Directional, luma, noise-dissolve, and radial wipes |

The processing contract makes execution shape visible before an effect is loaded. All 66 current manifests declare it explicitly. The twelve retained `1.0.0` manifests predate the object, so the schema-v1 loader applies its conservative single-pass defaults to them, as it does for compatible external older manifests. Counts below describe the current 66-version view:

| Model | Count | Meaning |
| --- | ---: | --- |
| `single_pass` | 40 | One shader pass with no retained frame history |
| `multi_pass` | 12 | Two or more declared shader passes executed in order |
| `temporal` | 10 | Stateful processing with declared history frames |
| `simulation` | 4 | Stateful iterative processing with simulation history |
| `adapter` | 0 | Reserved for native, Python, network, or external-runtime adapters |

Processing metadata can declare relative GPU-cost hints (`low`, `medium`, `high`, or `extreme`) and capabilities such as `multi_pass`, `history`, `second_input`, `transition`, `displacement`, `depth`, `normal`, `flow`, and `simulation`. These are routing and discovery metadata, not performance guarantees; measure on the target GPU.

## Why the library is package-based

- Effects can coexist at multiple versions instead of being overwritten in place.
- A project can lock the exact package version and digest used in production.
- Update discovery is separate from download, activation, and execution.
- GLSL, native networks, Python tools, plugins, presets, and learning techniques can share one catalog without sharing one trust level.
- Stable, beta, and experimental channels allow exploration without destabilizing production work.

## Repository map

| Path | Purpose |
| --- | --- |
| `packages/` | Immutable packages at `packages/<package-id>/<version>/` |
| `schemas/` | Machine-readable package, feed, state, and lock contracts |
| `src/tdimagefx/` | Versioning, validation, registry, compatibility, updater, archive, state, lockfile, and CLI logic |
| `touchdesigner/` | TouchDesigner extensions, callbacks, native builder, and reusable core `.tox` files |
| `tools/` | Effect scaffolding, release packaging, gallery/benchmark generation, and repository verification |
| `.github/workflows/` | Automated verification for pushes and pull requests |
| `tests/` | Unit and integration checks that do not require editing a production `.toe` |
| `docs/` | Architecture, setup, authoring, security, generated gallery, benchmarks, coverage, and source references |

## Install and open

Clone the complete repository; do not copy the `.toe` by itself:

```console
git clone https://github.com/wenjunii/td-imagefx-library.git
cd td-imagefx-library
```

Open `TD_ImageFX_Library.toe` in TouchDesigner 2025. The checked-in project, four reusable core `.tox` files, and 78 versioned effect `.tox` files are ready to use. The project presents the latest 66 effects by default; the twelve retained `1.0.0` components remain beside their `1.1.0` successors for exact-version loads. Keep the checkout together because blank **Library Root** parameters resolve from `project.folder`.

The native assets, preview images, and benchmark inputs were generated on Windows with TouchDesigner 2025.32820. Validate other TouchDesigner builds, operating systems, drivers, and GPUs before production use. Python is optional for using the prebuilt `.toe` and `.tox` files.

## Use in TouchDesigner

### Eight-slot rack

1. Open `/project1/imagefx_demo`.
2. Replace or reconnect `source_image` with any image TOP.
3. Select `fx_rack` and open its **Rack** custom parameter page.
4. Choose up to eight effects and adjust each slot's **Enable** and **Mix**.
5. Use each slot's **Up**, **Down**, **Reset**, and **Bypass** actions to manage the chain.
6. Select `sine`, `triangle`, or `saw` modulation and set per-slot depth/rate when desired.
7. Use **Export/Import Preset** for JSON in the project or **Save/Load Preset** for validated preset files.

The default chain is Wave Warp -> Exposure -> Gaussian Blur -> RGB Split -> Feedback Trails -> Halftone -> Bloom -> Scanlines. **Auto Time** and **Time Scale** drive effects that declare time controls. Presets capture exact package versions, slot order, enable/mix state, modulation, and eligible effect parameters; they do not replace a production project lock.

### Searchable browser

Open `/project1/td_imagefx/core/fx_browser`. Search is case-insensitive across catalog metadata; **Category**, comma-separated **Tags**, and **Favorites Only** narrow the result DAT. Favorites persist as JSON in the browser COMP. Select an effect, set **Creation Target** to a COMP, and pulse **Create Selected**. The result table exposes compatibility, processing model, GPU-cost hint, and component path for every match.

### Individual and reusable components

Effect components live under `packages/<package-id>/<version>/tox/`. The browser and rack use the highest installed SemVer for each of the 66 effect IDs, while version-aware library calls and project locks can still request any retained exact version. The reusable core files are `TDImageFXLibrary.tox`, `FxRack.tox`, `FxBrowser.tox`, and `FxUpdater.tox` under `touchdesigner/core/`. When importing one into another show, set **Library Root** to this checkout or a verified installed-package root.

Read [TouchDesigner setup](docs/touchdesigner-setup.md) for native rebuild instructions, production checks, and effect testing. Read the [effect authoring contract](docs/effect-authoring-contract.md) before creating or converting an effect.

## Author, document, and benchmark effects

Create a package scaffold without overwriting existing work:

```console
python tools/new_effect.py chromatic-smear "Chromatic Smear" stylize --model single_pass --gpu-cost medium
python tools/new_effect.py echo-lite "Echo Lite" temporal --model temporal --capability history --history-frames 1
```

Edit the generated manifest and shaders, then run the native builder described in [TouchDesigner setup](docs/touchdesigner-setup.md). It validates all 78 immutable manifests and package-relative paths before file access, then rebuilds only the latest version for each of the 66 effect IDs. Historical `.tox` files are preserved. It also creates the library/rack/browser/updater `.tox` files, `TD_ImageFX_Library.toe`, current-version preview PNGs, runtime benchmark samples, and `build/touchdesigner-build-report.json`.

After reviewing the native output, regenerate and verify the derived documentation:

```console
python tools/build_gallery.py
python tools/check_gallery.py --update
python tools/benchmark_report.py
python tools/verify_repository.py
```

Only use `check_gallery.py --update` after intentionally approving the newly rendered previews; normal verification uses `python tools/check_gallery.py` and detects changed, missing, or added images. Browse the [generated effect gallery](docs/gallery.md) and [hardware-specific benchmark report](docs/benchmarks.md).

For a release candidate, create deterministic package ZIPs, SHA-256 metadata, and a feed staging file:

```console
python tools/package_release.py --release-tag v0.2.0
```

This writes to `dist/` by default and stages only the latest version of each of the 66 effect IDs. Every ZIP contains `LICENSE`, `THIRD_PARTY_NOTICES.md`, the validated package manifest, and its declared entrypoints and shader passes; undeclared files and symbolic links are excluded. Feed entries use immutable, release-tagged manifest URLs rather than a mutable branch URL. The command does not publish, sign, install, or activate anything; review the artifacts and feed before attaching them to the matching GitHub Release tag.

## Automatic update checks in v0.2.0

The Update Manager at `/project1/td_imagefx/update_manager` checks explicitly configured local or HTTPS JSON feeds on a worker thread. **Auto Check** defaults to on, the `stable` channel, a 24-hour interval, and a 10-second timeout. Results appear in `update_results` and `.imagefx/update-status.json`.

The default first-party source is:

```text
https://raw.githubusercontent.com/wenjunii/td-imagefx-library/main/registry/update-feed.json
```

Checks are notification-only: they never download, install, activate, or execute discovered code. The checked-in public feed remains empty until curated release artifacts are published. For an offline checkout, disable `tdimagefx.github.stable` and enable `tdimagefx.local` in `config/update_sources.json`.

The updater does not crawl GitHub, Derivative sites, forums, or the wider web for arbitrary effects, shaders, plugins, or techniques. Updating this checkout with `git pull` is a separate, reviewable operation outside the in-project feed checker. See the [updater, security, and version-locking policy](docs/updater-security-version-locking.md).

## Verify a checkout

Python 3.11 or newer can run the complete dependency-free repository check:

```console
python tools/verify_repository.py
```

The verifier compiles Python, runs the unit suite, validates feeds and all 78 immutable manifests, checks declared entrypoints and native assets, verifies that gallery and benchmark artifacts cover the latest 66 versions, and prevents library-version drift. GitHub Actions runs the same command for pushes and pull requests.

For CLI exploration, an editable install is optional:

```console
python -m pip install -e .
tdimagefx --help
```

Inside TouchDesigner's Textport, `op('/project1/td_imagefx').HealthCheck()` should report `ok=True`, `package_count=66`, `package_version_count=78`, and no missing entrypoints. Shader compilation is checked by the native builder and recorded in its build report rather than by `HealthCheck()`.

## Production rules

- Never let an update replace a package version referenced by a show.
- Keep project locks with the project and updater cache/state outside the project lock.
- Treat shaders, Python, `.tox` files, and compiled plugins as executable content with different risk levels.
- Preview and test updates on representative media and target hardware before activation.
- Record the TouchDesigner build, OS, GPU, driver, color space, resolution, and frame rate used for validation.
- Preserve alpha unless an effect explicitly documents another alpha policy.

## Documentation

- [Architecture](docs/architecture.md)
- [TouchDesigner setup](docs/touchdesigner-setup.md)
- [Effect authoring contract](docs/effect-authoring-contract.md)
- [Generated effect gallery](docs/gallery.md)
- [Runtime benchmark report](docs/benchmarks.md)
- [Updater, security, and version locking](docs/updater-security-version-locking.md)
- [Roadmap and category coverage](docs/roadmap-and-coverage.md)
- [Official references](docs/official-sources.md)
- [Changelog](CHANGELOG.md)
- [Issue tracker](https://github.com/wenjunii/td-imagefx-library/issues)

## Project status

This repository is at **v0.2.0**. Public contracts use package manifest `schema_version: 1`, effect API `fx_api: "1.0"`, SemVer package versions, and the `stable`, `beta`, and `experimental` channels. Breaking changes require an explicit migration path and an appropriate version change.

TD ImageFX Library and all 78 bundled effect versions are released under the [MIT License](LICENSE). Required attribution for incorporated MIT-compatible code is preserved in [Third-Party Notices](THIRD_PARTY_NOTICES.md). Third-party packages added later must retain their own license and attribution metadata; inclusion in this catalog does not relicense external work.

TouchDesigner is a trademark of Derivative Inc. This independent project is not affiliated with or endorsed by Derivative.
