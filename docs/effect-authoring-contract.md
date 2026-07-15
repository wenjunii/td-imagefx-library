# Effect authoring contract

Every TD ImageFX effect must look predictable from the outside even when its internal technique is completely different. This contract applies to GLSL, native TOP networks, Python/Script TOP tools, feedback systems, and future plugin adapters; type-specific rules may add requirements but may not weaken the common interface.

## 1. Package identity

- Package IDs use lowercase dot-separated names: `tdimagefx.<category>.<effect>`.
- Use ASCII letters, digits, and hyphens inside a segment; do not encode a version in the ID.
- Package versions use Semantic Versioning, for example `1.2.0`.
- Each package lives at `packages/<package-id>/<version>/` and has a `package.json` entry point.
- Published version directories are immutable. A correction creates a new version.
- The manifest uses integer `schema_version: 1` and effect contract `fx_api: "1.0"` for this foundation release.
- The release channel is one of `stable`, `beta`, or `experimental`.

Choose the category by the primary user-facing result, not the implementation method. `tdimagefx.distort.twirl` remains in distortion whether it is implemented with GLSL or a native network.

## 2. Required manifest meaning

The JSON schema in `schemas/` is authoritative for exact field names, types, and conditional requirements. Semantically, every effect package must declare:

- identity: package ID, display name, package version, schema version, and effect API;
- description, category, tags, author/source attribution, license, and homepage/source links where applicable;
- release channel and publication/changelog information;
- content/implementation type and declared asset paths;
- input and output connector contracts;
- parameters with stable machine names, labels, types, defaults, ranges/options, units, and modulation suitability;
- TouchDesigner build range and relevant OS, architecture, GPU/API, or dependency constraints;
- alpha, color-space, resolution, time, and determinism behavior;
- package archive/digest information when distributed remotely;
- processing model, relative GPU-cost hint, capabilities, ordered passes, and history requirements;
- optional preview, example, preset, and known-limit metadata.

Unknown required behavior must not be hidden in a tutorial. If an adapter needs the information to build or safely run an effect, it belongs in the manifest/schema.

## 3. Processing models and capabilities

Every new v0.2 effect declares a root `processing` object. Its fields describe how the adapter must construct the graph and what resources or inputs it needs:

| Model | Contract |
| --- | --- |
| `single_pass` | One shader pass, no retained history |
| `multi_pass` | Two or more shader paths in ordered `passes`; `passes[0]` matches `entrypoints.shader` |
| `temporal` | Stateful frame processing with `history_frames >= 1` and the `history` capability |
| `simulation` | Stateful iterative processing with `history_frames >= 1`, plus `history` and `simulation` capabilities |
| `adapter` | Reserved for an external implementation whose Python/network/native permissions and compatibility are declared explicitly |

`gpu_cost` is one of `low`, `medium`, `high`, or `extreme`. It is a relative discovery hint, not an FPS promise. `capabilities` is a unique list drawn from `multi_pass`, `history`, `second_input`, `transition`, `displacement`, `depth`, `normal`, `flow`, `simulation`, `audio`, `native_plugin`, `network`, and `python`.

Declare what the implementation actually needs. A second image or control texture requires `second_input`; multi-pass packages require `multi_pass`; feedback requires `history`. A permission-bearing capability must agree with the package permission block. Pass paths follow the same containment rules as every other package asset, and changing pass order or history semantics can be a breaking behavior change.

## 4. File and asset rules

- Every referenced asset path is relative to the package version directory.
- Paths must use forward slashes in JSON, must not be absolute, and must not contain `..` traversal.
- Assets must remain inside their package after canonical path resolution.
- Do not load shader includes, Python modules, textures, LUTs, models, or binaries that are not declared.
- Include the package's license and all required third-party notices.
- Do not commit secrets, API keys, personal paths, hostnames, or machine-specific tokens.
- Preview media must be replaceable and must not be required for the effect to cook.

A source checkout may declare a generated `touchdesigner_component` entrypoint that does not exist until `touchdesigner/scripts/build_project.py` runs. That is the only v0.2.0 build-time exception: authored shaders and every declared pass must already exist, the build report must record the generated `.tox`, and a distributable/installed package must contain every declared entrypoint. A package may embed assets into a `.tox` for portability, but the source package remains the reviewable record and the embedded asset list must match it.

## 5. Operator interface

### Inputs

Input 0 is always the primary 2D image TOP for image effects. Additional connectors must be declared and labeled. Recommended roles are:

| Role | Meaning |
| --- | --- |
| `image` | Primary RGBA image; required at input 0 |
| `mask` | Optional scalar or RGBA mask controlling effect application |
| `image_b` | Second image for a transition or two-source composite |
| `displacement` | Optional displacement/flow/control texture |
| `depth` | Optional depth texture with documented range and units |
| `motion` | Optional motion vectors with documented encoding |

Do not change connector order in a patch release. Adding an optional trailing connector may be minor if old networks behave identically. Reordering, removing, or changing connector meaning is breaking.

### Output

- Output 0 is the final RGBA image TOP.
- The output is reachable through a stable top-level component connector; users must not depend on internal operator names.
- A diagnostic or analysis output requires a declared additional connector and a minor version at minimum.
- When an effect cannot run, it should fail visibly in diagnostics while keeping a bypassed primary image available whenever safe.

## 6. Common parameters

The adapter presents common controls consistently. TouchDesigner parameter machine names should be stable across all effects, while labels may be human-friendly. In effect API 1.0, authored image-effect manifests include `Enable` and `Mix`; the adapter/rack may add a separate bypass control around the package. The remaining controls are declared only when applicable.

| Machine name | Label | Contract |
| --- | --- | --- |
| `Enable` | Enable | Required for image effects; turns effect processing on/off without destroying state |
| `Mix` | Mix | Required for image effects; normalized dry/wet blend where 0 is input and 1 is full effect |
| `Bypass` | Bypass | Optional adapter/rack wrapper that returns the primary input without cooking the effect when feasible |
| `Time` | Time | Explicit time value used when the package is time-driven |
| `Speed` | Speed | Multiplier applied to time-driven behavior |
| `Phase` | Phase | Offset for cyclic/time behavior, when applicable |
| `Seed` | Seed | Deterministic seed for random/noise behavior |
| `Reset` | Reset | Pulse that clears temporal state, when applicable |
| `Maskenable` | Mask Enable | Enables a declared mask input |
| `Maskinvert` | Mask Invert | Inverts declared mask influence |
| `Quality` | Quality | Small documented set of performance/quality modes |

Except for `Enable` and `Mix`, only expose common parameters that have meaning, and do not rename them. Effect-specific parameter names must remain stable for automation and presets. Parameter changes follow these compatibility rules:

- changing a label or help text without changing behavior is patch-level;
- adding an optional parameter with backward-compatible default is minor-level;
- removing/renaming a parameter, changing its type, or materially changing its value mapping is major-level;
- widening a safe numeric range can be minor; changing the default look requires careful migration and is normally major.

## 7. Image behavior

### Resolution and coordinates

- Inherit the primary input resolution and pixel format unless the manifest explicitly says otherwise.
- Use normalized UV coordinates and correct spatial calculations for aspect ratio when the visual operation is intended to be isotropic.
- Derive texel size/resolution from TouchDesigner texture info, not hard-coded constants.
- Define behavior outside the `[0, 1]` UV range: clamp, repeat, mirror, border color, or transparent.
- Test portrait, landscape, square, odd pixel dimensions, and dynamic resolution changes.

### Color

- State the expected color context: project working space, scene-linear, or display-referred.
- Avoid silently applying gamma conversions.
- Color parameters must use TouchDesigner's color parameter facilities when working-space conversion matters.
- Clamp only when the effect requires it. Preserve HDR/negative values when the declared format and technique allow them.

### Alpha

The default policy is **preserve the primary input alpha**. An effect that creates, erodes, composites, or otherwise changes alpha must declare that policy. Wet/dry mixing must not accidentally make transparent pixels opaque. Test transparent images with nonzero hidden RGB.

## 8. Time and determinism

- Time-driven shaders receive time through the common adapter rather than reading an undocumented global clock.
- At fixed inputs, parameters, time, and seed, the result should be deterministic unless nondeterminism is explicitly declared.
- `Speed = 0` freezes time-driven motion.
- `Reset` clears feedback/history to a documented starting state.
- Temporal effects declare whether they are frame-based or seconds-based and how dropped frames affect them.
- Presets must not capture a machine's absolute clock unless that is the explicit technique.

## 9. GLSL TOP rules

The starter packages use TouchDesigner's GLSL TOP conventions:

```glsl
layout(location = 0) out vec4 fragColor;

uniform float uMix;

void main()
{
    vec2 uv = vUV.st;
    vec4 source = texture(sTD2DInputs[0], uv);
    vec4 effected = source; // replace with effect logic
    vec4 result = mix(source, effected, clamp(uMix, 0.0, 1.0));
    fragColor = TDOutputSwizzle(result);
}
```

Requirements:

- Use `sTD2DInputs` and `vUV` for normal 2D pixel-shader input sampling.
- Use `uTD2DInfos`/`uTDOutputInfo` for texture and output resolution.
- Pass pixel-shader output through `TDOutputSwizzle()`.
- Do not add a `#version` line when TouchDesigner owns shader version selection.
- Declare custom uniforms with names that map unambiguously to manifest parameters.
- Guard divisions, logarithms, normalization, and power operations against NaN/Inf edge cases.
- Avoid data-dependent unbounded loops and document expensive sample counts.
- Preserve source alpha unless the manifest declares otherwise.
- Use a fixed seed path for procedural noise when reproducibility is promised.
- Shader warnings and compile errors must be visible through an Info DAT or the adapter's diagnostics.
- For multi-pass effects, make the handoff between passes explicit and keep dry/wet composition at the declared final stage.
- For temporal/simulation effects, define reset/initialization behavior and never sample uninitialized history.

## 10. Performance contract

Every stable package needs a reproducible performance note, not a universal FPS promise. Record:

- TouchDesigner build, OS, GPU, and driver;
- input/output resolution and pixel format;
- target frame rate;
- number of passes and samples;
- measured effect cook/GPU time where available;
- GPU memory behavior;
- quality mode and representative parameter values.

Avoid unnecessary TOP downloads to CPU, uncontrolled feedback buffers, per-frame Python loops over pixels, and operators that cook while bypassed. Performance tiers are comparative hints, not compatibility guarantees. The native builder records TouchDesigner timing and memory samples in `docs/benchmark-data.json`; `python tools/benchmark_report.py` renders the hardware-specific report.

## 11. Testing and review

An effect is not stable until all applicable checks pass:

- package schema and path validation;
- digest/archive tests for distributed packages;
- shader/source lint or compile validation available to the project;
- manifest parameter-to-uniform completeness;
- deterministic default image or documented visual snapshot comparison;
- bypass and dry/wet identity checks;
- alpha, color, format, aspect, and dynamic-resolution cases;
- parameter boundaries and invalid-value behavior;
- compatibility accept/reject cases;
- license and attribution review;
- manual TouchDesigner smoke test on at least one declared supported build.
- generated preview review followed by an intentional gallery-baseline update;
- benchmark sample coverage for every catalog package.

The reviewer should be able to understand what executes, what files it accesses, and what changes between versions without opening a binary `.tox` as the only source.

The supported source-first workflow is:

```console
python tools/new_effect.py chromatic-smear "Chromatic Smear" stylize --model single_pass --gpu-cost medium
```

Edit the scaffold, run `touchdesigner/scripts/build_project.py` inside TouchDesigner, inspect `build/touchdesigner-build-report.json`, then regenerate/check derived artifacts:

```console
python tools/build_gallery.py
python tools/check_gallery.py --update
python tools/benchmark_report.py
python tools/verify_repository.py
```

Only update gallery baselines after visual approval. For release staging, `python tools/package_release.py --release-tag v0.2.0` creates deterministic ZIPs and feed metadata under `dist/`; it does not publish or activate them.

## 12. Versioning examples

- Fix a shader branch that produced NaN at `Radius = 0`: patch.
- Add an optional `Edge Softness` parameter whose default preserves the old look: minor.
- Add a second optional output for a matte: usually minor, with adapter support.
- Rename `Amount` to `Strength` or change its range mapping: major unless a migration alias preserves automation.
- Change mask input from connector 1 to connector 2: major.
- Improve documentation or preview media only: patch.
- Change the package digest without changing the version: forbidden.
