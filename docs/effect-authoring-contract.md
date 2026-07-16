# Effect authoring contract

Every TD ImageFX effect must be predictable from the outside even when its internal technique is different. This contract applies to GLSL, native TOP networks, feedback systems, Python/Script TOP tools, and future plugin adapters. Type-specific rules may add requirements but may not weaken the common interface.

The JSON schema in `schemas/package-manifest.schema.json` is authoritative for exact field names, types, and conditions. This document explains authoring intent.

## 1. Identity and immutability

- Package IDs use lowercase dot-separated names: `tdimagefx.<category>.<effect>`.
- Use ASCII letters, digits, and hyphens inside a segment; do not encode the version in the ID.
- Package versions use canonical Semantic Versioning, for example `1.2.0`.
- Each version lives at `packages/<package-id>/<version>/package.json`.
- A published version directory is immutable. Any content or metadata correction creates a new version.
- v0.3 continues to use integer `schema_version: 1` and effect API `fx_api: "1.0"`.
- `channel` is `stable`, `beta`, or `experimental`; a channel describes maturity, not compatibility.

Choose the category by the primary user-facing result, not by implementation. A perspective operation belongs in transform even if it is a single GLSL pass.

## 2. Manifest meaning

Every effect declares enough information to answer these questions without opening a binary `.tox`:

- What package/version is this, who produced it, and under what license?
- What assets execute and where did the technique/code originate?
- Which TOP or data inputs and outputs exist, in what order, and with what roles?
- Which parameters are stable for presets, automation, and modulation?
- How are color, alpha, pixel format, sampling, resolution, time, and randomness handled?
- How many passes/history frames/iterations are required, and which capabilities are needed?
- How is temporal state reset and warmed up?
- Which TouchDesigner builds, operating systems, architectures, APIs, dependencies, or permissions are required?
- What is known to be unsupported, untested, expensive, or visually approximate?

Do not hide adapter-critical behavior only in a tutorial. If code needs information to build, route, reproduce, or safely evaluate an effect, it belongs in the manifest.

The richer `image_contract`, `determinism`, `temporal`, `provenance`, roles, and advanced processing fields are additive within schema version 1. Legacy schema-v1 packages can omit them; new packages should declare every applicable field. Absence must be displayed as legacy/unasserted behavior, not interpreted as a guarantee.

## 3. Processing models and capabilities

Every new package declares `processing`:

| Model | Required behavior |
| --- | --- |
| `single_pass` | One shader stage and no retained history |
| `multi_pass` | At least two ordered paths in `passes`; the first matches `entrypoints.shader` |
| `temporal` | `stateful: true`, `history_frames >= 1`, and the `history` capability |
| `simulation` | Temporal requirements plus the `simulation` capability |
| `adapter` | External implementation with explicit Python/network/native capabilities, permissions, and compatibility |

`gpu_cost` is a relative `low`, `medium`, `high`, or `extreme` discovery hint. It is not an FPS promise. Capabilities are drawn from `multi_pass`, `history`, `second_input`, `transition`, `displacement`, `depth`, `normal`, `flow`, `simulation`, `audio`, `native_plugin`, `network`, and `python`.

Declare only what the implementation needs. Cross-field rules include:

- two or more declared passes require the `multi_pass` capability for a `multi_pass` model;
- temporal/simulation processing requires `history` and at least one history frame;
- simulation additionally requires `simulation`;
- second/auxiliary images require `second_input` except a transition image, which requires `transition`;
- depth, normal, flow, displacement, and audio roles require their matching capability;
- `native_plugin`, `network`, and `python` capabilities must agree with package permissions.

### Stateful pass separation

New temporal/simulation packages should declare both `state_pass` and `render_pass`. If either is present, both and `passes` are required, the model must be temporal or simulation, and the package must declare `history`.

- `state_pass` writes only private retained state.
- `render_pass` converts current source plus private state into the canonical public image.
- `entrypoints.shader`, `state_pass`, `render_pass`, and every ordered pass must be package-relative declared assets.
- Dry/wet composition and primary-source alpha preservation belong in the render stage unless the effect contract says otherwise.

Do not expose raw simulation state as the final image merely because it is convenient to wire. Do not sample uninitialized history.

### Scale, iterations, and quality tiers

`pass_scale` ranges from `0.0625` to `4.0`; `iterations` ranges from 1 to 1024. Optional `quality_tiers` contain stable IDs, labels, a pass scale, an iteration count, and exactly one `default: true` tier. A tier is a repeatable configuration, not a performance claim. Changing a tier's meaning can break presets even if its ID is unchanged.

No bundled v0.3 effect currently publishes quality tiers. Authors must implement and measure them before exposing the metadata.

## 4. Ports and semantic routing

Input 0 is the primary 2D image TOP for image effects. New manifests should use `role: "source_image"`. Additional connectors must be ordered, labeled, and assigned one of the supported roles:

| Input role | Meaning and capability |
| --- | --- |
| `source_image` | Primary RGBA image |
| `second_image` | Second source/layer; requires `second_input` |
| `auxiliary_image` | Generic auxiliary image; requires `second_input` |
| `transition_image` | Transition destination/source B; requires `transition` |
| `mask` | Scalar or RGBA influence/matte |
| `depth` | Depth texture with documented encoding; requires `depth` |
| `normal` | Normal texture with documented space; requires `normal` |
| `flow` | Motion/optical-flow vectors with documented encoding; requires `flow` |
| `displacement` | Displacement/control texture; requires `displacement` |
| `audio` | Audio/control input; requires `audio` |
| `control` | Non-image control stream |
| `data` | Generic declared data input |

Output roles are `image`, `mask`, `state`, or `data`. Output 0 for an image effect is the canonical public `image` TOP. Private feedback state is not a substitute for that output.

The rack supports source image plus second image, displacement, depth, normal, flow, and mask buses. A package using audio/control/data needs an adapter designed for that family; the image rack must fail visibly rather than misroute it.

Do not reorder connectors in a patch release. Adding an optional trailing connector may be minor if old networks remain identical. Removing, reordering, or changing connector meaning is breaking.

## 5. Image contract

New image effects should declare all four `image_contract` sections.

### Color

Declare `input_space`, `working_space`, `output_space`, and `reference`. Supported spaces are `source`, `project`, `linear-srgb`, `srgb`, `rec709`, `rec2020`, `display-p3`, `acescg`, and `raw`; reference is `scene_referred`, `display_referred`, or `data`.

- Do not silently apply gamma conversions.
- Use project/color-parameter facilities where TouchDesigner color management matters.
- Preserve HDR and negative values unless the technique and format explicitly require clipping.
- A tone-mapping operation should distinguish scene-referred input from display-referred output rather than relying on its category name.

### Alpha

Declare input, working, and output representation as `straight`, `premultiplied`, `opaque`, `none`, or `any`. This must agree with top-level `alpha_policy`:

- `premultiply` requires `output: "premultiplied"`;
- `unpremultiply` requires `output: "straight"`;
- `force_opaque` requires `output: "opaque"`;
- a non-`any` preserved input must not silently change representation.

The default authoring expectation is to preserve primary-source alpha. Key, matte, morphology, and compositing effects must document intentional changes. Test transparent pixels with nonzero hidden RGB.

### Pixel format and sampling

Pixel policy is `inherit`, `minimum`, `preferred`, or `fixed`. Non-inherit policies name a format from the schema. Sampling declares filter, edge mode, mipmap use, and a border color only when edge mode is `border`. Mipmap/anisotropic filtering requires `mipmaps: true`.

Resolution and coordinates still follow the top-level contract:

- inherit primary input resolution unless `resolution_policy` explicitly says otherwise;
- derive resolution and texel size from TouchDesigner texture info;
- account for aspect ratio when an operation is intended to be isotropic;
- test portrait, landscape, square, odd dimensions, and live resolution changes.

## 6. Time, determinism, and reset

`determinism.mode` is one of:

| Mode | Contract |
| --- | --- |
| `deterministic` | Fixed inputs, parameters, time, and state sequence produce the same result |
| `seeded` | Reproducibility uses exactly one declared seed parameter or fixed seed |
| `time_dependent` | Result depends on explicit time progression |
| `external` | Result depends on declared external input/state |
| `non_deterministic` | Reproducibility is not promised and the limitation is documented |

Use `fixed_timestep` when simulation/state advancement is defined per step. Time-driven shaders receive explicit adapter time instead of reading an undocumented machine clock. `Speed = 0` should freeze motion where Speed exists. Presets should capture manual time/seed, not a machine's absolute clock.

Stateful packages declare `temporal.reset`:

- strategy: `pulse_parameter`, `toggle_parameter`, `automatic`, or `unsupported`;
- the referenced manifest parameter ID for pulse/toggle strategies;
- what is cleared: `history`, `simulation_state`, or `all`;
- whether resolution or input changes trigger reset;
- optional `warmup_frames`.

A supported Reset must actually clear every retained state target and reseed to a documented condition. If reset is unsupported, explain why in `known_limitations` and do not display a fake working pulse.

## 7. Parameters and component interface

Manifest parameter `id` is a stable lowercase identifier; `name` is the stable TouchDesigner parameter name. Labels/help text may be more human-friendly. Image effects include `Enable` and normalized `Mix`; adapters may add bypass outside the package.

| TouchDesigner name | Meaning |
| --- | --- |
| `Enable` | Turn processing on/off without destroying state |
| `Mix` | Dry/wet blend from primary input to effect result |
| `Time` | Explicit time value |
| `Speed` | Time multiplier |
| `Phase` | Cyclic offset |
| `Seed` | Reproducible procedural seed |
| `Reset` | Stateful reset pulse when supported |
| `Quality` | A small, implemented set of declared quality tiers |

Parameter compatibility rules:

- label/help-only corrections are patch-level;
- a backward-compatible optional parameter can be minor;
- renaming/removing/changing type or materially changing value mapping is major unless a migration alias fully preserves behavior;
- changing a default look is normally major;
- changing the meaning of a preset-visible enum/menu entry can be breaking.

## 8. Provenance, files, and assets

Every referenced asset path is package-relative, uses forward slashes, stays inside the version directory after canonical resolution, and is declared. Do not load hidden shader includes, Python modules, LUTs, textures, models, or binaries.

`provenance.origin` is `original`, `adapted`, `ported`, `generated`, or `third_party`. `source.type` records original/repository/publication/website/generated origin. Adapted, ported, and third-party content requires a source URL; record revision, author, and license where known. Declare package-contained changelogs, examples, and presets so release packaging includes them. List material limitations rather than relying on issue history.

Include all required license and attribution text. Do not commit secrets, credentials, personal paths, private hostnames, or machine tokens. Preview media must be replaceable and must not be required for the effect to cook.

A source checkout may declare a generated `touchdesigner_component` that does not exist until the native builder runs. Authored shaders and every declared processing/provenance asset must already exist. A distributable package must contain every entrypoint, and the native build report must record the generated `.tox`.

## 9. GLSL TOP rules

Normal 2D pixel shaders follow TouchDesigner's GLSL TOP conventions:

```glsl
layout(location = 0) out vec4 fragColor;

uniform float uMix;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effected = source; // effect logic
    fragColor = TDOutputSwizzle(mix(source, effected, clamp(uMix, 0.0, 1.0)));
}
```

Requirements:

- use `sTD2DInputs` and `vUV` for normal image sampling;
- use TouchDesigner texture/output info for resolution;
- pass output through `TDOutputSwizzle()`;
- do not add a shader `#version` when TouchDesigner owns version selection;
- map uniforms unambiguously to manifest parameters;
- guard divisions, logarithms, normalization, and powers against NaN/Inf;
- avoid data-dependent unbounded loops and document expensive fixed loops;
- preserve alpha according to the image contract;
- keep state writes, public render, and dry/wet responsibilities explicit;
- surface warnings/compile errors through adapter diagnostics.

## 10. Performance and testing

Every stable package needs a reproducible measurement note, not a universal FPS promise. Record TouchDesigner build, OS, GPU/driver, resolution, pixel format, frame rate, pass/sample/iteration counts, quality tier, representative parameters, cook/GPU time, and memory behavior where available.

An effect is not stable until applicable checks pass:

- schema, cross-field, path, identity, and immutable-history validation;
- declared asset, digest, archive, license, and attribution review;
- shader compilation on at least one declared TouchDesigner build;
- parameter/uniform completeness and boundary handling;
- bypass and dry/wet identity;
- alpha, color, HDR/negative, format, aspect, and dynamic-resolution cases;
- auxiliary-input absent/present/wrong-role behavior;
- deterministic seed/time behavior or documented nondeterminism;
- reset, resolution-change reset, warmup, and long-history behavior for stateful packages;
- approved visual preview/baseline update;
- runtime benchmark sample on named hardware;
- target-environment smoke/soak testing proportional to risk.

The reviewer must understand what executes, which files it accesses, and what changed between versions without treating the binary `.tox` as the only source.

## 11. Source-first workflow

```console
python tools/new_effect.py chromatic-smear "Chromatic Smear" stylize --model single_pass --gpu-cost medium
```

Edit and review the scaffold, then run the native builder inside TouchDesigner. Inspect `build/touchdesigner-build-report.json` before regenerating derived artifacts:

```console
python tools/build_gallery.py
python tools/check_gallery.py --update
python tools/benchmark_report.py
python tools/verify_repository.py
```

Only update gallery baselines after visual approval. Release staging uses:

```console
python tools/package_release.py --release-tag v0.3.0
```

It creates a transactional, deterministic release candidate with feed metadata, provenance, and checksums. It does not publish or activate packages.

## 12. Versioning examples

- Fix a shader branch that produced NaN at `Radius = 0`: patch.
- Add an optional Edge Softness whose default preserves the old look: minor.
- Add a second optional output with adapter support: usually minor.
- Add an explicit image contract that exactly documents unchanged behavior: patch; changing behavior to match it may not be.
- Split internal state/render passes without changing public output/reset behavior: implementation-dependent patch or minor, with visual migration evidence.
- Rename `Amount` to `Strength` or change its range mapping: major unless an alias preserves automation.
- Change a mask from connector 1 to connector 2: major.
- Change package bytes or digest without changing the version: forbidden.
