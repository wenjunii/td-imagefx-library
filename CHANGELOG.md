# Changelog

All notable changes to TD ImageFX Library are recorded here. Package versions follow Semantic Versioning; package manifest schema and effect API compatibility are versioned independently.

## [Unreleased]

### Added

- Project-scoped integration for Embody `6.0.131`, Envoy, the local
  TouchDesigner knowledge library, and `td-knowledge-mcp`.
- A public-safe `get_td_project_context` profile, placeholder-only combined MCP
  configuration, and ordered read-only live validation plan.
- A disposable QA harness installer that refuses the canonical library project,
  never saves automatically, loads the compiled ImageFX core, synchronizes the
  tracked extensions, and repairs legacy package-local shader references.
- A live structural validator covering library health, recursive operator
  errors, warnings, script errors, and approved TOP existence/resolution before
  Envoy performs pixel-quality capture.
- `InkFlowFusion.tox`, a reusable GPU module with independently switchable
  minimal Chinese ink work, minimal ink wash (Shui-mo), and seeded
  water-current particles, plus adjustable paper, pigment, flow, randomness,
  density, shape, palette, bypass, and deterministic-time controls.
- A dedicated live ink-flow validator covering both visual styles, whole-module
  and feature-level bypass, water-particle motion, seed variation, combined
  rendering, maximum density, and GLSL diagnostics.
- `GlitchFusion.tox`, a reusable single-pass GPU module with 24 selectable
  glitch styles, master and mix bypass, deterministic/manual timing, seed, and
  adjustable geometry, signal, compression, color, and corruption controls.
- A dedicated live Glitch Fusion validator covering the exact style menu,
  every style's visible and distinct output, bypass fidelity, time and seed
  variation, rack routing, resolution, and GLSL diagnostics.
- `ColorAdjustment.tox`, a reusable neutral-by-default single-pass GPU module
  for inversion, primary grading, white balance, levels, tonal shaping,
  three-way RGB balance, clarity/dehaze, creative treatments, duotone,
  sixteen adjustable color-overlay blend modes, grain, and vignette.
- A dedicated live Color Adjustment validator covering master and zero-mix
  bypass, neutral fidelity, every numeric slider and overlay mode, endpoint
  metadata, visual distinction, source-alpha preservation, rack routing, and
  GLSL diagnostics.
- `MotionStudio.tox`, a reusable single-pass GPU motion module with 40
  selectable animation styles, master and mix bypass, deterministic/manual
  timing, six easing modes, four edge modes, adjustable transform/warp/random
  controls, and bounded one-through-five-sample motion trails.
- A dedicated live Motion Studio validator covering the exact style, easing,
  and edge menus; bypass fidelity; every style's visible and distinct output;
  manual time; bounded trail sampling; routing; resolution; and GLSL
  diagnostics.
- Demo output-resolution controls with a default 1920 x 1080 preset, a 4K UHD
  3840 x 2160 preset, and adjustable 16-through-8192 custom width and height.
- A dedicated live output-resolution validator covering default values, the
  exact preset menu, HD, 4K UHD, nonstandard custom dimensions, source/output
  propagation, bounds, and operator diagnostics.
- Expanded Color Adjustment controls for global offset and contrast pivot,
  extended tonal shaping, three-way color balance, clarity/dehaze, fade,
  solarize, threshold, sixteen overlay blend modes, film grain, and vignette.
- Expanded Random Particles controls with eight shapes, eight motion modes,
  size/aspect/rotation/spin/softness/hollow variation, richer motion and source
  sampling, opacity variation, tint/HSV grading, and an explicit read-only
  Effective Time display.
- Exhaustive native slider validation for all 72 Color Adjustment numeric
  components and all 39 Random Particles numeric components, including visible
  output response, finite pixels, endpoint evaluation, range/clamp metadata,
  menu distinction, alpha preservation, and resolved-time behavior.
- A state-restoring all-effect validator that loads all 96 latest packages and
  checks every manifest numeric component, toggle, rack mix, effective time,
  per-effect time scale, range/clamp contract, finite output, diagnostics, and
  320 x 180 cook resolution without saving the project.
- Compatible `tdimagefx.key.despill@1.1.0` and
  `tdimagefx.stylize.vignette@1.2.0` packages whose color-alpha sliders now
  scale suppression and vignette strength; prior immutable versions remain
  available for exact project locks.

### Changed

- The development harness installer now requires the exact unnumbered
  `TD_ImageFX_DevHarness.toe` identity and rejects `.1`, `.2`, and other
  numbered recovery identities before modifying the live network.
- Setup documentation now distinguishes the generated runtime `.toe` from the
  ignored development harness and documents the source-first rebuild path;
  harness-only edits never silently synchronize into the release artifact.
- The project-scoped TD knowledge bridge now follows the active Envoy instance
  in the ImageFX Embody registry and fails closed unless both ImageFX managed
  roots are present, preventing another open TouchDesigner project from being
  mistaken for the QA harness.
- The standalone bridge checker now rejects missing-root and malformed Envoy
  error reports instead of treating absent health flags as a clean project.
- Repository verification now protects the live-QA integration identity,
  catalog counts, managed paths, required audit tools, and no-save harness
  boundary.
- Repository verification now also rejects drift between public README claims,
  the checked source test count, the live validator's catalog constants, and
  the native TouchDesigner build recorded in the ImageFX project context.
- The native builder and runtime loaders now keep GLSL Pixel Shader DAT
  references package-relative when effects move into a rack or user network.
- The browser now reloads and cooks its selected preview after a catalog
  selection changes; the native builder also initializes and validates the
  first 512x288 preview before exporting the component.
- The canonical demo now routes source through ink flow, optional random
  particles, optional Glitch Fusion, optional Color Adjustment, optional
  Motion Studio, and the eight-slot rack with explicit stage-level bypass
  controls.
- The generated demo source and final Out TOP now follow the selected delivery
  resolution automatically.
- The native `.toe`, nine core `.tox` components, benchmark report, and
  SHA-256-bound native validation record were rebuilt with TouchDesigner
  `2025.32820`.
- The offline suite now contains 172 tests, including contracts for every
  latest manifest uniform being both declared and referenced, bounded
  ink-flow particles, two distinct visual styles, all 24 Glitch Fusion styles,
  neutral color adjustment, sixteen overlay modes, all 40 Motion Studio styles,
  HD/4K/custom output resolution, native artifact inventory, and the
  eight-output Embody audit.
- Repository verification now scans tracked files for high-confidence
  credential formats and forbidden secret-bearing filenames without printing
  suspected values; a staged-only mode supports pre-commit review.

### Fixed

- Rack-loaded effects now multiply global rack time by their editable local
  **Time Scale**; effective time, enable/mix, and package metadata are locked
  read-only when the rack owns them, so internal controls no longer appear
  editable while being overridden.
- Ink and paper palette alpha now participate in pigment, paper, and
  water-particle blending instead of behaving like inactive sliders.

- Replaced ambiguous SemVer regular expressions in the Python package and
  TouchDesigner updater with bounded deterministic parsers, preventing
  attacker-controlled version text from causing exponential backtracking.

## [0.3.0] - 2026-07-16

### Added

- Thirty production-oriented GLSL effects, expanding the latest catalog to 96 effect IDs across 18 categories: six transform/framing tools; five compositing tools; four keying/despill tools; four matte tools; four mask generators; four color-management/grading tools; and three advanced blur/focus tools.
- Transform 2D, Crop Feather, Corner Pin, Tile Repeat, Fit Fill, Perspective Warp, Blend Modes, Alpha Composite, Matte Composite, Channel Shuffle, Edge Extend, Chroma Key, Luma Key, Difference Key, Despill, Dilate, Erode, Feather, Alpha Repair, Gradient Mask, Radial Mask, Shape Mask, Noise Mask, Curves, Color Decision List, Tone Map, LUT 3D, Bilateral Blur, Bokeh Blur, and Depth-Aware Blur packages.
- Immutable `1.1.0` upgrades for all ten temporal and four simulation effects, bringing the stored package history to 122 versions while retaining their `1.0.0` predecessors.
- Additive schema-v1 contracts for semantic input/output roles; color, alpha, pixel format, and sampling behavior; determinism; temporal reset/warmup; provenance; state/render pass separation; pass scale; iterations; and quality tiers.
- Six semantic rack auxiliary buses for second image, displacement, depth, normal, flow, and mask, plus explicit manual-time control.
- Browser filters for channel, processing model, capability, and input readiness; available-input diagnostics; sorting; selected-effect preview/details; parameter and image-contract summaries; and lazy effect instantiation.
- `SECURITY.md`, `CONTRIBUTING.md`, CODEOWNERS, immutable-history checking, and a manual prepare-only release workflow.
- A tracked native-validation record that binds the successful TouchDesigner environment and zero-error result to SHA-256 hashes for the library `.toe`, every versioned effect `.tox`, and all four core `.tox` files.

### Changed

- The latest processing-model split is now 68 single-pass, 14 multi-pass, 10 temporal, and 4 simulation packages.
- Stateful graph generation now keeps private simulation/history state separate from the public render output, supports retained histories longer than one frame, and routes Reset to every declared history node with a legacy fallback.
- Stateful gallery captures now use controlled reset/prior-frame fixtures and deterministically unroll each declared state shader for its preview iteration count; shipped components continue to reset from black and use live Feedback TOP history.
- Rack input connections resolve declared roles and semantic aliases instead of treating every secondary TOP as the same source.
- Disabling rack Auto Time now uses the explicit Manual Time value, and slot mix bindings preserve rack modulation.
- The manifest loader, validator, and scaffolder understand the richer v0.3 contracts while preserving older schema-v1 manifests as legacy/unasserted metadata.
- The notification-only updater now rejects duplicate JSON keys, bounds feed data, rejects credential/query/fragment/malformed-port URL data and origin-changing redirects, binds configured sources to feed IDs and optional digests, applies channel hierarchy and runtime compatibility checks, reconciles duplicate candidates by exact project-lock source and feed trust, reports project-lock context, safely redacts malformed URLs, and prevents stale checks from replacing newer results.
- Verified staging now requires every manifest-declared entrypoint, processing pass, changelog, example, and preset to exist before immutable package registration.
- Release packaging is transactional and deterministic, emits the mixed-maturity `tdimagefx.github.catalog` feed, validates its generated feed, confines all output paths, rejects unsafe symlinks and identifiers, can bind a clean release-input tree and release tag to the source revision, writes release provenance and `SHA256SUMS`, and leaves no partial destination on failure.
- GitHub verification now spans Windows, macOS, and Linux with Python 3.11 and 3.13, with a separate check protecting previously published package-version directories.

### Security

- Update discovery remains notification-only; no new code is downloaded, installed, activated, or executed by an automatic check.
- Feed/source identity and trust reconciliation, source digest, archive containment, immutable-history, release tag/revision binding, release provenance, and transactional-output checks reduce substitution and partial-release risks.
- Unknown runtime compatibility is reported as unverified rather than silently promoted to a verified match.

### Verification status

- The Python manifest and runtime contracts include dedicated tests for the new package metadata, stateful upgrades, rack routing/reset/time behavior, browser diagnostics, updater validation, release hardening, and immutable history.
- The synchronized native build used TouchDesigner `2025.32820` on Windows and produced 122 versioned effect `.tox` files, four core `.tox` files, one library `.toe`, 96 previews, 96 visual baselines, and 96 benchmark samples. Its report records zero shader, preview, or builder errors.
- The final repository verifier completed 146 tests successfully; four Windows-only symbolic-link cases were skipped because the local account lacked link-creation privilege. Two independently staged 99-file release candidates were byte-identical.

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
