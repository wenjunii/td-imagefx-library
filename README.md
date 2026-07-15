# TD ImageFX Library

TD ImageFX Library is a versioned, extensible image-animation and video-effects system for TouchDesigner. It treats each effect as a package with a stable interface, compatibility metadata, an immutable version, and a project lock entry. The goal is a library that can grow for years without silently changing finished shows.

Version **0.1.0** is the foundation release. It establishes the package, registry, compatibility, update-feed, archive, state, and lockfile layers and ships twelve starter GLSL image effects. It is a starting catalog, not a claim that every visual technique has already been implemented.

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
| `tests/` | Unit and integration checks that do not require editing a production `.toe` |
| `docs/` | Architecture, setup, authoring, security, versioning, coverage, and source references |

## Start here

1. Open `TD_ImageFX_Library.toe` in TouchDesigner 2025. The checked-in project, core `.tox` files, and all twelve effect `.tox` files are already generated and ready to use.
2. Read [TouchDesigner setup](docs/touchdesigner-setup.md) for the rack workflow, individual component loading, and the optional rebuild procedure.
3. Read the [effect authoring contract](docs/effect-authoring-contract.md) before creating or converting an effect.
4. Configure update behavior using the [updater, security, and version-locking policy](docs/updater-security-version-locking.md). The recommended default is automatic checks with notification-only activation.
5. Use the [architecture](docs/architecture.md) to understand which layer owns catalog data, runtime state, and project locks, and track planned categories in the [coverage roadmap](docs/roadmap-and-coverage.md).

The standalone core requires Python 3.11 or newer and has no runtime dependencies. Install the checkout with `python -m pip install -e .`, then run `tdimagefx --help`; command help is the executable source of truth for this foundation release.

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

## Project status

This repository is at **v0.1.0**. The public contracts use package manifest `schema_version: 1`, effect API `fx_api: "1.0"`, SemVer package versions, and the `stable`, `beta`, and `experimental` channels. Breaking changes to those contracts require an explicit migration path and an appropriate version change.

TD ImageFX Library and its twelve starter effects are released under the [MIT License](LICENSE). Required attribution for MIT-compatible code incorporated into the starter shaders is preserved in [Third-Party Notices](THIRD_PARTY_NOTICES.md). Third-party packages added later must retain their own license and attribution metadata; inclusion in this catalog does not relicense external work.

TouchDesigner is a trademark of Derivative Inc. This independent project is not affiliated with or endorsed by Derivative.
