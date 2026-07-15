# TD ImageFX Library

[![Verify repository](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml/badge.svg)](https://github.com/wenjunii/td-imagefx-library/actions/workflows/verify.yml)

TD ImageFX Library is a versioned, extensible image-animation and video-effects system for TouchDesigner. It treats each effect as a package with a stable interface, compatibility metadata, an immutable version, and a project lock entry. The goal is a library that can grow for years without silently changing finished shows.

Version **0.1.0** is the foundation release. It establishes the package, registry, compatibility, update-feed, archive, state, and lockfile layers and ships twelve starter GLSL image effects. It is a starting catalog, not a claim that every visual technique has already been implemented.

Canonical repository: [github.com/wenjunii/td-imagefx-library](https://github.com/wenjunii/td-imagefx-library)

## Starter effects

| Package ID | Name | Category |
| --- | --- | --- |
| `tdimagefx.color.duotone` | Duotone | Color |
| `tdimagefx.color.posterize` | Posterize | Color |
| `tdimagefx.color.hsv-shift` | HSV Shift | Color |
| `tdimagefx.distort.wave-warp` | Wave Warp | Distortion |
| `tdimagefx.distort.twirl` | Twirl | Distortion |
| `tdimagefx.distort.kaleidoscope` | Kaleidoscope | Distortion |
| `tdimagefx.glitch.rgb-split` | RGB Split | Glitch |
| `tdimagefx.glitch.block-shift` | Block Shift | Glitch |
| `tdimagefx.stylize.pixelate` | Pixelate | Stylize |
| `tdimagefx.stylize.scanlines` | Scanlines | Stylize |
| `tdimagefx.stylize.vignette` | Vignette | Stylize |
| `tdimagefx.transition.noise-dissolve` | Noise Dissolve | Transition |

All twelve are GPU image effects intended for a GLSL TOP workflow. Their package manifests under `packages/` are the authoritative source for versions, parameters, inputs, licenses, assets, and compatibility.

The TouchDesigner builder turns those sources into a reusable library COMP, individual effect `.tox` files, a four-slot animated FX Rack, a starter demo network, and a notify-only Update Manager. The standalone Python core validates and resolves package metadata, compatibility, feeds, archives, installed state, and exact project locks without requiring TouchDesigner to be running.

## Why the library is package-based

- Effects can coexist at multiple versions instead of being overwritten in place.
- A project can lock the exact package version and digest used in production.
- Update discovery is separate from download, activation, and execution.
- Native networks, GLSL, Python tools, compiled plugins, presets, and learning techniques can share one catalog without sharing one trust level.
- Stable, beta, and experimental channels allow exploration without destabilizing production work.

## Repository map

| Path | Purpose |
| --- | --- |
| `packages/` | Immutable effect packages at `packages/<package-id>/<version>/` |
| `schemas/` | Machine-readable package, feed, state, and lock contracts |
| `src/tdimagefx/` | Versioning, validation, registry, compatibility, updater, archive, state, lockfile, and CLI logic |
| `touchdesigner/` | TouchDesigner bootstrap, component-building, and runtime integration |
| `tools/` | Dependency-free repository verification used locally and in CI |
| `.github/workflows/` | Automated verification for pushes and pull requests |
| `tests/` | Unit and integration checks that do not require editing a production `.toe` |
| `docs/` | Architecture, setup, authoring, security, versioning, coverage, and source references |

## Install and open

Clone the complete repository; do not copy the `.toe` by itself:

```console
git clone https://github.com/wenjunii/td-imagefx-library.git
cd td-imagefx-library
```

Open `TD_ImageFX_Library.toe` in TouchDesigner 2025. The checked-in project, three core `.tox` files, and twelve effect `.tox` files are ready to use. Keep the checkout together because blank **Library Root** parameters resolve from `project.folder`.

The native files were generated and checked on Windows with TouchDesigner 2025.32820. Validate other TouchDesigner builds, operating systems, and GPUs locally before production use. Python is optional and is not required to use the prebuilt `.toe` or `.tox` files.

## Use in TouchDesigner

1. Open `/project1/imagefx_demo`.
2. Replace or reconnect `source_image` with any image TOP.
3. Select `fx_rack` and open its **Rack** custom parameter page.
4. Choose an effect for each of the four slots, then adjust each slot's **Enable** and **Mix** controls.
5. Use **Auto Time** and **Time Scale** to drive animated effects.

The default rack is **Wave Warp → RGB Split → Scanlines → Vignette**. Individual components live under `packages/<package-id>/<version>/tox/`. When importing `FxRack.tox`, `FxUpdater.tox`, or `TDImageFXLibrary.tox` into another show, set its **Library Root** to this checkout or to an installed package root.

Read [TouchDesigner setup](docs/touchdesigner-setup.md) for rebuild instructions, individual component loading, production checks, and effect testing. Read the [effect authoring contract](docs/effect-authoring-contract.md) before creating or converting an effect.

## Automatic update checks in v0.1.0

The Update Manager at `/project1/td_imagefx/update_manager` checks explicitly configured local or HTTPS JSON feeds on a worker thread. **Auto Check** defaults to on, the `stable` channel, a 24-hour interval, and a 10-second timeout. It performs its first check shortly after startup. Results appear in the manager's `update_results` table and in `.imagefx/update-status.json`.

The default source is the first-party public feed at:

```text
https://raw.githubusercontent.com/wenjunii/td-imagefx-library/main/registry/update-feed.json
```

Checks are notification-only: they never download, install, activate, or execute discovered code. The public feed is deliberately empty for the bundled v0.1.0 catalog; future entries must be curated and versioned before clients can discover them. For an offline checkout, disable `tdimagefx.github.stable` and enable `tdimagefx.local` in `config/update_sources.json`.

This release does not crawl GitHub, Derivative sites, forums, or the wider web for arbitrary effects, shaders, plugins, or techniques. Curated source monitors remain roadmap work. Updating the repository itself with `git pull` is separate from the in-project feed checker and should be reviewed outside production shows.

See the [updater, security, and version-locking policy](docs/updater-security-version-locking.md) before adding sources or enabling later lifecycle stages.

## Verify a checkout

Python 3.11 or newer can run every repository check without installing dependencies:

```console
python tools/verify_repository.py
```

The verifier compiles Python sources, runs the unit suite, validates both update feeds and all package manifests, checks every declared entrypoint, confirms required native assets exist, and prevents library-version drift. GitHub Actions runs the same command for pushes and pull requests.

For CLI exploration, an editable install is optional:

```console
python -m pip install -e .
tdimagefx --help
```

Inside TouchDesigner's Textport, `op('/project1/td_imagefx').HealthCheck()` should report `ok=True`, twelve packages, and no missing entrypoints. That health check does not compile shaders; shader compilation must be checked in TouchDesigner or through a native rebuild report.

## Learn and extend

Use the [architecture](docs/architecture.md) to understand which layer owns catalog data, runtime state, and project locks, and track planned categories in the [coverage roadmap](docs/roadmap-and-coverage.md). The standalone core has no runtime dependencies; command help and tests remain the executable source of truth while the foundation API settles.

## Production rules

- Never let an update replace a package version referenced by a show.
- Keep project locks with the project, and keep updater cache/state outside the project lock.
- Treat shaders, Python, `.tox` files, and compiled plugins as executable content with different risk levels.
- Preview and test updates on representative media and hardware before activation.
- Record the TouchDesigner build, operating system, GPU, driver, color space, resolution, and frame rate used for validation.
- Preserve alpha unless an effect explicitly documents another alpha policy.

## Documentation

- [Architecture](docs/architecture.md)
- [TouchDesigner setup](docs/touchdesigner-setup.md)
- [Effect authoring contract](docs/effect-authoring-contract.md)
- [Updater, security, and version locking](docs/updater-security-version-locking.md)
- [Roadmap and category coverage](docs/roadmap-and-coverage.md)
- [Official references](docs/official-sources.md)
- [Changelog](CHANGELOG.md)
- [Issue tracker](https://github.com/wenjunii/td-imagefx-library/issues)

## Project status

This repository is at **v0.1.0**. The public contracts use package manifest `schema_version: 1`, effect API `fx_api: "1.0"`, SemVer package versions, and the `stable`, `beta`, and `experimental` channels. Breaking changes to those contracts require an explicit migration path and an appropriate version change.

TD ImageFX Library and its twelve starter effects are released under the [MIT License](LICENSE). Required attribution for MIT-compatible code incorporated into the starter shaders is preserved in [Third-Party Notices](THIRD_PARTY_NOTICES.md). Third-party packages added later must retain their own license and attribution metadata; inclusion in this catalog does not relicense external work.

TouchDesigner is a trademark of Derivative Inc. This independent project is not affiliated with or endorsed by Derivative.
