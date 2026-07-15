# TouchDesigner setup

This guide covers the v0.2.0 native project, reusable components, and source-first build workflow. Record the exact TouchDesigner build in each release and project lock; do not assume that every Official or Experimental build is interchangeable.

## Baseline

- Use a current **TouchDesigner 2025 Official** build for the v0.2.0 native assets.
- Current TouchDesigner documentation identifies GLSL 4.60 as the main supported GLSL version.
- Keep a copy of a production `.toe` before changing its TouchDesigner build, GPU driver, working color space, or locked packages.
- Test on the OS and GPU that will run the show. A shader compiling on one machine is not sufficient production validation.

The checked-in native files, gallery previews, and benchmark data were generated with TouchDesigner **2025.32820** on Windows. See [official sources](official-sources.md) for current download, release-note, GLSL TOP, and component documentation.

## Repository checkout versus installed content

The repository contains authored package sources and the integration layer. Runtime downloads and updater state remain separate from source-controlled project content:

```text
repository/
  packages/                 authored, reviewable packages and generated package .tox files
  schemas/                  public contracts
  src/tdimagefx/            package/update core
  touchdesigner/            extensions, callbacks, builder, and reusable core .tox files
  docs/gallery/             TouchDesigner-rendered preview images

user data or release cache/
  installed/                verified side-by-side package versions
  staging/                  unactivated downloads
  quarantine/               rejected artifacts
  state/                    updater and activation records

show project/
  show.toe
  tdimagefx.lock.json        exact versions and digests for this show
```

Do not point a production component at a mutable download or staging path.

## First integration

The repository includes:

- `TD_ImageFX_Library.toe` with `/project1/td_imagefx` and `/project1/imagefx_demo`;
- 78 versioned effect `.tox` files under `packages/<package-id>/<version>/tox/`: one current version for each of 66 effect IDs plus twelve retained `1.0.0` components beside their upgraded `1.1.0` versions;
- `touchdesigner/core/TDImageFXLibrary.tox`;
- `touchdesigner/core/FxRack.tox`;
- `touchdesigner/core/FxBrowser.tox`;
- `touchdesigner/core/FxUpdater.tox`.

Open the `.toe` directly for the fastest start. Its browser, rack, demo, gallery, and benchmark data use the latest 66 versions. Exact retained versions remain available through version-aware library calls and project locks. Keep the project in the repository root when using the default configuration: blank **Library Root** fields resolve to `project.folder`. When importing a core `.tox` into a show elsewhere, set its **Library Root** to this checkout or a verified installed-package root.

For a quick inventory check in the Textport, `op('/project1/td_imagefx').HealthCheck()` should return `ok=True`, `package_count=66`, and `package_version_count=78`, with an empty `missing_entrypoints` list.

Python is not required to use the prebuilt native files. Python 3.11 or newer is required for repository tools and the standalone package CLI.

## Native rebuild

The project remains source-first. `touchdesigner/scripts/build_project.py` runs inside TouchDesigner and recreates the native assets from manifests and shaders. It owns and replaces `/project1/td_imagefx` and `/project1/imagefx_demo`; use a disposable build project or save any work before running it.

1. Copy or clone the repository to a stable local path.
2. Record the TouchDesigner build and GPU/driver details.
3. Validate a new manifest with an editable CLI install if needed:

   ```console
   python -m pip install -e .
   tdimagefx validate packages/tdimagefx.category.effect/1.0.0/package.json --type package
   ```

4. Start a blank TouchDesigner project and open the Textport.
5. Replace the example path with the absolute path to this checkout and execute:

   ```python
   script = r"C:/path/to/td-imagefx-library/touchdesigner/scripts/build_project.py"
   exec(
       compile(open(script, encoding="utf-8").read(), script, "exec"),
       {"__file__": script, "__name__": "__main__"},
   )
   ```

6. Confirm the Textport reports 66 current effects selected from 78 validated package versions and the path to `build/touchdesigner-build-report.json`.
7. Inspect that report for `errors`, `shader_errors`, and `preview_errors` before accepting the native output.
8. Run the generated-document and repository checks described below.
9. Create or update an exact project lock before treating a show as production-ready.

The builder creates or updates:

- `TD_ImageFX_Library.toe`;
- one rebuilt `.tox` for the latest version of each of 66 effect IDs, while leaving the twelve historical `1.0.0` `.tox` files untouched;
- four reusable core `.tox` files for the library, rack, browser, and updater;
- declared single-pass and multi-pass GLSL graphs plus temporal/simulation feedback graphs;
- 66 preview PNGs under `docs/gallery/`;
- `docs/benchmark-data.json` with per-effect runtime samples;
- `build/touchdesigner-build-report.json` with environment, graph, asset, timing, and shader diagnostics.

The build validates package identity, manifest contracts, declared paths, containment, and required assets across all 78 immutable versions before constructing networks. It then selects only the latest version of each of the 66 effect IDs for rebuilding, previews, the native catalog, and benchmarks. Historical version directories and `.tox` files are preserved. The build also fails if a current shader does not compile or a preview cannot be saved. The report is still written with runtime failure details.

## Generated gallery and benchmark reports

After a successful native build, regenerate the manifest-derived gallery index and hardware-specific benchmark report:

```console
python tools/build_gallery.py
python tools/benchmark_report.py
```

Compare every changed preview on representative media. Only after intentional visual approval should you replace the SHA-256 baselines:

```console
python tools/check_gallery.py --update
```

Normal verification must use `python tools/check_gallery.py` without `--update`; it reports missing, added, or changed preview files. Finish with:

```console
python tools/verify_repository.py
```

The generated [effect gallery](gallery.md) is searchable programmatically through `gallery.json`. The [benchmark report](benchmarks.md) records its TouchDesigner build, GPU, resolution, sample count, method, GPU timing availability, CPU submission time, and texture memory. Results are not transferable FPS promises.

## Searchable browser

The browser is `/project1/td_imagefx/core/fx_browser` in the checked-in `.toe` and is also available as `FxBrowser.tox`.

1. Enter case-insensitive text in **Search**.
2. Choose a **Category** or enter comma-separated **Tags**; requested tags are ANDed.
3. Use **Toggle Favorite** and **Favorites Only** to maintain a project-local JSON favorite list.
4. Inspect the `results` DAT for package ID, version, category, tags, compatibility, processing model, GPU-cost hint, and component path.
5. Set **Creation Target** to the destination COMP, select an effect, and pulse **Create Selected**.

Creation delegates to the parent library extension and loads the exact package `.tox` recorded in the current catalog. The browser defaults to the latest version per effect ID; a locked show can still request a retained historical version through the version-aware library API. Missing targets, catalog data, or component entrypoints are reported through browser status instead of being silently ignored.

## Eight-slot rack

The rack accepts a primary image at input 0 and produces one canonical image output. Its default chain is:

```text
Wave Warp -> Exposure -> Gaussian Blur -> RGB Split
    -> Feedback Trails -> Halftone -> Bloom -> Scanlines
```

Each of eight slots provides effect selection, enable, dry/wet mix, modulation depth/rate/state, Up, Down, Reset, and Bypass. Global controls reload/reset the rack and bypass or enable every slot. **Auto Time** and **Time Scale** drive time-aware package parameters.

Modulation currently applies `off`, `sine`, `triangle`, or `saw` waveforms to slot mix. It is bounded and does not edit immutable package defaults.

Rack presets use schema-versioned JSON and capture exact package IDs/versions, order, enable/mix state, eligible effect parameters, rack time settings, and modulation. Export/import operates on the **Preset JSON** parameter; save/load accepts `.json` paths confined to the library `presets/` folder and rejects files larger than 256 KiB. Preset application validates first and attempts to restore the previous slot state if a load fails. Presets do not install packages or rewrite a project lock.

## Minimal image chain

For a single effect, keep the TouchDesigner network legible:

```text
Movie File In TOP (or any image TOP)
    -> TD ImageFX effect COMP
    -> Null TOP
    -> downstream composite/output
```

Input 0 is the primary RGBA image. Additional image, displacement, depth, flow, or control TOPs are declared by the manifest. Use the component output, not an internal GLSL TOP path; package internals may change within a compatible patch while the top-level contract remains stable.

## Loading a packaged component

When a release provides a `.tox`:

1. Drag it into the target network or load it through the browser/library API.
2. Prefer project-relative or package-relative paths and decide external `.tox` behavior explicitly.
3. Enable a backup in the `.toe` when portability is more important than always loading from disk.
4. Keep package ID, version, and effect API visible on the component's Package page.
5. Never replace a `.tox` in place while a locked project points to it; install the new version beside it and migrate explicitly.

## Testing all 66 current effects

Use a small verification matrix before approving a package or rack:

| Input | What it reveals |
| --- | --- |
| Color bars and grayscale ramp | Clipping, channel order, color transforms, posterization |
| Checkerboard with transparent edges | UV behavior, filtering, alpha preservation |
| Portrait or textured still | Perceptual quality and parameter usefulness |
| Fully transparent RGBA with nonzero RGB | Premultiplication and hidden-RGB mistakes |
| Portrait, square, and ultrawide images | Aspect correction and coordinate assumptions |
| 8-bit and 16/32-bit float TOPs | Pixel-format assumptions and banding |
| Moving imagery and scene cuts | Temporal reset, history, echo, and simulation behavior |
| Auxiliary gradients/noise/depth/flow | Second-input semantics and displacement bounds |

For each effect:

1. Confirm `Enable = Off` is visually identical to input.
2. Confirm `Mix = 0` is input and `Mix = 1` is the full effect.
3. Exercise parameter minimum, default, and maximum values.
4. Scrub/restart time and verify deterministic behavior for the same seed and history state.
5. Reset temporal/simulation effects and check the documented initial state.
6. Resize the input while cooking and check for errors or stale resolution values.
7. Inspect every declared GLSL pass for compile messages.
8. Monitor frame time, GPU memory, and cook behavior at the target resolution/frame rate.

## Color, alpha, and resolution

- Keep the project working color space explicit; effects must state whether they expect working-space, scene-linear, or display-referred data.
- Treat straight versus premultiplied alpha deliberately. The default contract preserves primary-input alpha.
- Inherit input resolution unless the manifest declares another policy.
- Use `uTD2DInfos` and `uTDOutputInfo`; avoid hard-coded resolutions.
- Apply `TDOutputSwizzle()` to pixel-shader output.

## Update Manager

`/project1/td_imagefx/update_manager` and `FxUpdater.tox` provide notification-only update checks. The manager reads explicitly configured local or HTTPS feeds on a worker thread, defaults to stable-channel checks every 24 hours, and writes results to `update_results` plus `.imagefx/update-status.json`.

Discovery never downloads, installs, activates, or executes a package. Keep network access optional during rehearsals and performances, and review [updater, security, and version locking](updater-security-version-locking.md) before changing sources or lifecycle policy.

## Production checklist

- Project lock exists and matches every active package.
- No effect resolves from `latest`, a mutable branch, or a staging directory.
- Required versions, `.tox` files, and the `.toe` are archived for offline recovery.
- Update checks are notification-only during rehearsals and performances.
- Network failure cannot block image output.
- The previous package set and `.toe` are available for rollback.
- Target media, resolution, frame rate, color space, GPU, and outputs have been soak-tested.
- External plugins and Python packages have separately approved licenses and trust records.
