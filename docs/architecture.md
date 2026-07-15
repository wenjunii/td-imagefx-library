# Architecture

TD ImageFX Library separates reusable visual content from discovery, installation state, and project decisions. That separation is the main safeguard against an update changing a finished TouchDesigner project.

## Design principles

1. **Packages are immutable.** A published `<package-id>/<version>` is never edited in place.
2. **Identity is stable.** IDs use `tdimagefx.<category>.<effect>` and versions use Semantic Versioning.
3. **Contracts are explicit.** Manifest schema version, effect API version, inputs, parameters, processing model, capabilities, assets, dependencies, and compatibility are machine-readable.
4. **Discovery is not execution.** A new feed entry can be displayed without downloading, installing, activating, or evaluating it.
5. **Projects decide.** The installed registry describes what is available; a project lock describes exactly what that project uses.
6. **TouchDesigner remains the renderer.** The library organizes effects and builds/integrates components; image cooking and shader compilation remain visible in TouchDesigner.
7. **Failure is reversible.** Staging, activation records, side-by-side versions, and rollback preserve the last known-good state.

## Layers

```mermaid
flowchart LR
    A["Curated feeds and local packages"] --> B["Manifest and schema validation"]
    B --> C["Compatibility and trust checks"]
    C --> D["Installed registry"]
    D --> E["Project lock resolver"]
    E --> F["TouchDesigner package/component adapter"]
    F --> G["FX instance"]
    F --> J["Searchable browser"]
    F --> K["Eight-slot rack"]
    K --> G
    H["Updater state"] --> C
    I["Project lockfile"] --> E
```

### Package layer

`packages/<package-id>/<version>/` holds one immutable package. `package.json` is its entry point. Assets may include GLSL, Python, component source, presets, previews, examples, license text, or platform-specific plugin payloads, but every shipped asset must be declared by the manifest and covered by the package digest policy.

The v0.2.0 namespace contains 66 GLSL effect IDs and 78 immutable version directories/manifests. The twelve original v0.1 effects remain at `1.0.0` beside upgraded `1.1.0` versions; the other current effects have one version each. Catalog, browser, rack, native-build, gallery, and benchmark views select the highest version for each ID, but an exact old version remains addressable by a version-aware lookup or project lock.

The current 66-version view contains forty single-pass, twelve multi-pass, ten temporal, and four simulation packages across 13 user-facing categories. Future adapter packages use the same lifecycle but may require stronger activation rules for Python, network access, native plugins, or external runtimes.

### Contract layer

`schemas/` defines the machine-readable boundaries for package manifests, feeds, installed state, and project locks. There are three independent compatibility axes:

- `schema_version` controls how metadata is parsed. The v0.2.0 value remains integer `1`.
- `fx_api` controls whether a TouchDesigner adapter can expose and drive the effect. The v0.2.0 value remains `1.0`.
- Package `version` controls changes to the package itself and follows SemVer.

A parser must reject unsupported schema versions. An adapter must refuse incompatible effect API versions. A resolver may retain several SemVer versions of one package simultaneously.

All 66 current v0.2 manifests declare a `processing` object. The twelve immutable `1.0.0` history manifests predate it. For schema-v1 backward compatibility with those and compatible external older packages, the loader treats an omitted object as `single_pass`, `low`, no capabilities, and zero history:

| Field | Meaning |
| --- | --- |
| `model` | `single_pass`, `multi_pass`, `temporal`, `simulation`, or future `adapter` execution |
| `gpu_cost` | Relative `low`, `medium`, `high`, or `extreme` authoring hint |
| `capabilities` | Routing/security facts such as history, second input, transition, displacement, depth, normal, flow, simulation, audio, native code, network, or Python |
| `passes` | Ordered package-relative shader paths; at least two for `multi_pass` |
| `history_frames` | Retained frame count; at least one for temporal/simulation processing |

Models describe graph structure; capabilities describe what the graph needs. Neither replaces runtime compatibility testing or measured performance data.

### Core Python layer

`src/tdimagefx/` owns data and lifecycle logic that can be tested independently of a `.toe` project:

| Module | Responsibility |
| --- | --- |
| `semver` | Parse and compare package versions and constraints |
| `manifest` | Load and validate package metadata |
| `registry` | Discover installed packages without conflating them with active project choices |
| `compatibility` | Evaluate TouchDesigner, OS, architecture, GPU/API, dependency, and effect API requirements |
| `lockfile` | Resolve and persist exact project versions and digests |
| `feed` | Read update indexes and select channel-appropriate candidates |
| `archive` | Verify and safely stage distributable archives |
| `state` | Persist installed, pending, active, and rollback state |
| `cli` | Expose the same core operations outside TouchDesigner |

Core modules must not import TouchDesigner's `td` module. This keeps schema, feed, archive, and lock behavior testable in ordinary Python and prevents updater logic from being coupled to a live show file.

### TouchDesigner adapter layer

`touchdesigner/` translates a validated package into TouchDesigner operators and parameters. Its responsibilities are deliberately narrow:

- create or load a Base COMP for an effect;
- connect image, mask, and auxiliary TOP inputs according to the manifest;
- construct declared single-pass/multi-pass shader chains and temporal/simulation feedback paths;
- create custom parameters from declared parameter metadata;
- bind parameters to GLSL uniforms or native nodes;
- expose one canonical TOP output;
- report shader compile errors and compatibility failures;
- attach package identity, version, digest, and lock status to the instance;
- preserve instance parameter values during a compatible, explicitly approved migration.

It does not decide that an update is trustworthy and does not rewrite a project lock on its own.

### Presentation layer

The shipped browser and eight-slot FX Rack consume the catalog without becoming package truth. The browser provides case-insensitive search, category/tag filters, JSON-backed favorites, compatibility/model/GPU-cost columns, and creation into an explicitly selected target COMP. The rack provides ordered slots, effect selection, enable/mix, shared time, reordering, per-slot and global bypass, reset/reload, validated presets, and sine/triangle/saw mix modulation.

Browser favorites and rack presets are project/UI state. Both interfaces default to the latest version of each of the 66 effect IDs. A preset records exact package versions and parameters for reconstruction, so a retained historical version can still be requested, but it does not install packages, approve an update, or rewrite the project lock. Both interfaces can be rebuilt from manifests, installed state, and a lock.

### Authoring and generated-artifact layer

The source-first toolchain keeps reviewable inputs separate from generated native and documentation artifacts:

1. `tools/new_effect.py` creates a non-overwriting manifest/shader scaffold for a declared processing model.
2. `touchdesigner/scripts/build_project.py` runs inside TouchDesigner, validates all 78 immutable manifests, selects and rebuilds only the latest version of each of 66 effect IDs, preserves historical `.tox` files, writes four core `.tox` files and `TD_ImageFX_Library.toe`, renders latest-version preview PNGs, and captures runtime benchmark data.
3. `tools/build_gallery.py`, `tools/check_gallery.py`, and `tools/benchmark_report.py` render/check derived documentation for the latest 66 versions.
4. `tools/verify_repository.py` checks all 78 manifests and native entrypoints, plus latest-version gallery baselines, benchmark coverage, and version consistency.
5. `tools/package_release.py` validates the stored version set, then stages only the latest 66 versions as deterministic ZIPs and release-feed metadata under `dist/`. Each ZIP includes `LICENSE`, `THIRD_PARTY_NOTICES.md`, the manifest, and declared package assets; feed manifest URLs are pinned to the supplied release tag. Publication and activation remain separate actions.

## State boundaries

| State | Meaning | Mutability |
| --- | --- | --- |
| Source package | Published content at an exact version | Immutable |
| Installed registry | Packages verified and present on this machine | Mutable machine state |
| Pending activation | Verified candidate awaiting approval or restart | Mutable machine state |
| Active selection | Package currently selected by the resolver | Mutable, auditable |
| Project lock | Exact package versions and digests required by one project | Changes only through explicit project migration |
| Instance state | Effect parameters, modulation links, presets, bypass/mix | Owned by the `.toe` project |

Do not store all six concepts in one JSON file. In particular, discovering or installing a newer package must not alter the project lock.

## Package resolution

Resolution follows this order:

1. Read the project lock if one exists.
2. Require the exact locked version and digest.
3. If it is installed and compatible, activate it.
4. If it is missing, report a reproducible missing-package error and offer to retrieve that exact artifact.
5. If no lock exists, resolve only from an explicitly selected channel and produce a lock before the project is treated as production-ready.

No “latest wins” fallback is allowed for a locked project.

## Error behavior

- Invalid manifests are excluded from the registry with actionable validation messages.
- Unsupported `schema_version` or `fx_api` values fail closed.
- Missing assets or digest mismatches quarantine the package.
- GLSL compile errors leave the original input available through bypass and surface the GLSL TOP/Info DAT error.
- A failed activation restores the previous active pointer; it never deletes the previous version.
- A missing locked dependency is reported rather than silently substituted.

## Extensibility

New content types should implement four interfaces: manifest validation, compatibility evaluation, staging verification, and a TouchDesigner adapter. A new effect category does not require a new package lifecycle. A compiled plugin, however, can add restart, platform, ABI, signing, and license requirements without weakening the rules for simpler GLSL packages.
