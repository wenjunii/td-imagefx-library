# Changelog

All notable changes to TD ImageFX Library are recorded here. Package versions follow Semantic Versioning; package manifest schema and effect API compatibility are versioned independently.

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
