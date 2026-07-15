# Changelog

All notable changes to TD ImageFX Library are recorded here. Package versions follow Semantic Versioning; package manifest schema and effect API compatibility are versioned independently.

## [Unreleased]

No unreleased changes are recorded yet.

## [0.2.0] - 2026-07-15

### Added

- Fifty-four new effects for a 66-effect catalog spanning blur, color, distortion, glitch, light/lighting, motion, sharpen, simulation, spatial, stylize, temporal, and transition work.
- Immutable side-by-side history for the twelve v0.1 starter effects: their original `1.0.0` packages remain available while upgraded `1.1.0` versions become current, yielding 78 stored package versions across 66 effect IDs.
- Manifest processing metadata for `single_pass`, `multi_pass`, `temporal`, `simulation`, and future `adapter` packages, including GPU-cost hints, capabilities, ordered passes, and history requirements.
- Twelve multi-pass, ten temporal, and four simulation packages alongside forty single-pass packages.
- Searchable TouchDesigner browser with case-insensitive text/category/tag filters, JSON-persisted favorites, compatibility/model/GPU-cost columns, and selected-effect creation into a target COMP.
- Eight-slot FX Rack with slot reordering, per-slot/all-slot bypass, reset/reload actions, validated JSON/file presets, and sine/triangle/saw mix modulation.
- `tools/new_effect.py` scaffolding for all processing models and declared capabilities.
- `tools/package_release.py` for deterministic latest-version package ZIPs, SHA-256 metadata, release-tagged immutable manifest URLs, and release-feed staging. Each ZIP includes the repository license and third-party notices with the manifest and declared package assets.
- Generated 66-effect gallery, TouchDesigner-rendered preview baselines, and runtime benchmark reporting.
- Reusable `FxBrowser.tox` alongside the library, rack, and updater core components.
- Dependency-free `tools/verify_repository.py` checks for tests, Python compilation, all 78 immutable manifests, feeds, entrypoints, native artifacts, latest-66 gallery/baseline and benchmark consistency, and version consistency.
- GitHub Actions verification using the same local command.
- First-party public HTTPS update-feed configuration for notification-only discovery.

### Changed

- Rebuilt `TD_ImageFX_Library.toe`, the 66 current package `.tox` files, and four core `.tox` files with TouchDesigner 2025.32820 while retaining twelve exact historical `.tox` files.
- The native builder now validates all 78 stored manifests, selects and rebuilds only the latest version for each of 66 effect IDs, preserves historical versions, creates declared pass chains and feedback/history paths, renders current-version gallery previews, captures benchmark samples, and records processing diagnostics in its build report.
- Browser, rack, native project, gallery, and benchmark views now default to the latest 66 versions while exact historical package versions remain addressable by version-aware library calls and project locks.
- Native previews now use a colorful spatial test pattern, representative neutral-effect overrides, and a current-frame history seed, producing 64 distinct reference images for 66 effects while restoring package defaults afterward.
- Expanded the catalog DAT with descriptions, processing models, GPU-cost hints, capabilities, compatibility, previews, and component paths.
- Expanded user and author documentation for browser, rack, native build, gallery, benchmark, and release workflows.
- TouchDesigner build completion output includes the generated report path.

### Security

- Browser and rack file operations validate inputs and report errors without silently executing discovered content.
- Presets retain exact package versions and use bounded, validated JSON; they do not modify project locks.
- Release artifacts are deterministic and accompanied by SHA-256 digests, while publishing and activation remain separate explicit actions.
- The scaffolder rejects non-canonical versions and path escapes; the release packager validates manifests and packages only declared nonsymlink assets, excluding undeclared secrets.
- The TouchDesigner builder validates package identity, manifest contracts, file containment, and declared assets before reading shaders or writing components.
- Temporal Glitch and Fluid Ink use a project-original cell hash; incorporated third-party shader code remains explicitly attributed.
- Automatic update checks remain notification-only and do not download, install, activate, or execute discovered packages.

## [0.1.0] - 2026-07-15

### Added

- Foundation architecture for immutable, side-by-side effect packages.
- Package manifest schema version 1 and effect API `1.0` conventions.
- Registry, SemVer, compatibility, update-feed, archive, state, lockfile, and CLI foundations.
- Stable, beta, and experimental release channels.
- Project-level exact-version and digest locking model.
- Staged update flow with separate check, download, verification, activation, and rollback states.
- TouchDesigner integration foundation and documented GLSL effect contract.
- Twelve starter GLSL effects: Duotone, Posterize, HSV Shift, Wave Warp, Twirl, Kaleidoscope, RGB Split, Block Shift, Pixelate, Scanlines, Vignette, and Noise Dissolve.
- Security guidance for remote catalogs, archives, shaders, Python packages, `.tox` components, and compiled plugins.
- Initial category coverage roadmap and official TouchDesigner reference index.
- MIT license for the library, package core, native components, and twelve starter effects.

### Security

- Automatic update checks are designed to notify without implicitly executing or activating newly discovered code.
- Package digests and safe archive extraction are required before staged content is eligible for activation.
- Production projects retain their locked package versions until an explicit migration is accepted.
