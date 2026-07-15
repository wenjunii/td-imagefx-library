# TouchDesigner setup

This guide covers the safe integration model for TD ImageFX Library. The exact validated TouchDesigner build belongs in each release record and project lock; do not assume that every Official or Experimental build is interchangeable.

## Baseline

- Use a current **TouchDesigner 2025 Official** build for the v0.1.0 foundation.
- Use the GLSL version selected by the package manifest and adapter. Current TouchDesigner documentation identifies GLSL 4.60 as the main supported version.
- Keep a copy of a production `.toe` before changing its TouchDesigner build, GPU driver, working color space, or locked packages.
- Test on the operating system and GPU that will run the show. A shader compiling on one machine is not sufficient production validation.

See [official sources](official-sources.md) for the current download, release-note, GLSL TOP, and component documentation rather than relying on a version number copied into this file.

## Repository checkout versus installed content

The repository contains authored package sources and the integration layer. Runtime downloads and updater state should be stored outside source-controlled project content. A typical division is:

```text
repository/
  packages/                 authored, reviewable packages
  schemas/                  public contracts
  src/tdimagefx/            package/update core
  touchdesigner/            TD bootstrap and adapters

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

The repository includes a prebuilt `TD_ImageFX_Library.toe`, three reusable core `.tox` files, and twelve effect `.tox` files generated and validated with TouchDesigner 2025.32820. Open the `.toe` directly for the fastest start.

Keep the `.toe` in the repository root when using the default configuration. The Library Root fields are intentionally blank and resolve to `project.folder`, so the complete folder can be moved without preserving the original build-machine path. If you import `FxRack.tox`, `FxUpdater.tox`, or `TDImageFXLibrary.tox` into a different show folder, set that component's Library Root to the TD ImageFX repository or installed-package root.

The project remains source-first: its builder runs inside TouchDesigner and recreates the native assets from the manifests and shaders. Use the following procedure when you change package sources or intentionally rebuild the library:

1. Save the `.toe` into its own project folder.
2. Record the TouchDesigner build and GPU/driver details.
3. Copy or clone this repository to a stable path with no cloud-sync rewrite in progress.
4. Run `python tools/verify_repository.py` to validate tests, manifests, feeds, entrypoints, native assets, and version metadata before importing content.
5. Start a blank TouchDesigner project. The builder refuses to overwrite existing `/project1/td_imagefx` or `/project1/imagefx_demo` nodes.
6. Open TouchDesigner's Textport, replace the example path below with the absolute path to this checkout, and execute it:

   ```python
   script = r"C:/path/to/video-effects/touchdesigner/scripts/build_project.py"
   exec(
       compile(open(script, encoding="utf-8").read(), script, "exec"),
       {"__file__": script, "__name__": "__main__"},
   )
   ```

7. Confirm the build completes and inspect `build/touchdesigner-build-report.json` for shader or build errors.
8. Confirm the generated library catalog contains all twelve v0.1.0 packages.
9. Create a project lock before treating the project as production-ready.

The builder creates:

- `TD_ImageFX_Library.toe`, containing `/project1/td_imagefx` and the `/project1/imagefx_demo` starter network;
- one package `.tox` under `packages/<package-id>/<version>/tox/` for each starter effect;
- `touchdesigner/core/TDImageFXLibrary.tox`, `FxRack.tox`, and `FxUpdater.tox`;
- `build/touchdesigner-build-report.json` with the TouchDesigner environment, generated assets, and shader errors.

Generated nodes are intentionally owned under two paths only. Re-run the builder in a fresh blank project or remove/rename a previous generated tree deliberately; it fails instead of overwriting those nodes.

The dependency-free verifier requires Python 3.11 or newer and runs directly with `python tools/verify_repository.py`. An editable CLI install is optional: run `python -m pip install -e .`, then `tdimagefx --help`. Do not copy undocumented commands into show automation—CLI help and tests are authoritative while the foundation API settles.

## Minimal image chain

For a single effect, keep the TouchDesigner network legible:

```text
Movie File In TOP (or any image TOP)
    -> TD ImageFX effect COMP
    -> Null TOP
    -> downstream composite/output
```

The effect COMP takes the primary RGBA image at input 0. An effect declaring a mask takes it at input 1. Transition effects may declare a second image input; follow the manifest rather than assuming that every extra connector is a mask.

During authoring, the internal core generally follows:

```text
in TOP -> GLSL TOP -> common mix/alpha/bypass stage -> out Null TOP
```

Use the component output, not an internal GLSL TOP path. Internals may change within a compatible package patch; the top-level contract must remain stable.

## Loading a packaged component

TouchDesigner can save and reuse a COMP as a `.tox`. When a release provides a `.tox`:

1. Drag it into the target network or use the documented component-loading workflow.
2. Prefer paths relative to the project or the external `.tox`, and decide that behavior explicitly.
3. Enable a backup of an external `.tox` in the `.toe` when portability is more important than always loading from disk.
4. Keep the package ID, version, and digest visible on the component's Info page.
5. Do not replace an external `.tox` file in place while a locked project points to it. Install the new version beside it and migrate the instance.

## Testing the twelve starter effects

Use a small verification matrix before building a rack:

| Input | What it reveals |
| --- | --- |
| Color bars and grayscale ramp | Clipping, channel order, color transforms, posterization |
| Checkerboard with transparent edges | UV behavior, filtering, alpha preservation |
| Portrait or textured still | Perceptual quality and parameter usefulness |
| Fully transparent RGBA image with nonzero RGB | Premultiplication and alpha mistakes |
| Odd aspect ratios such as portrait and ultrawide | Aspect correction and coordinate assumptions |
| 8-bit and 16/32-bit float TOPs | Pixel-format assumptions and banding |

For each effect:

1. Confirm `Bypass` is visually identical to the input.
2. Confirm `Mix = 0` is input and `Mix = 1` is the full effect.
3. Exercise parameter minimum, default, and maximum values.
4. Scrub or restart time and verify deterministic behavior for the same seed.
5. Resize the input while cooking and check for errors or stale resolution values.
6. Inspect GLSL compile messages through the GLSL TOP and an Info DAT.
7. Monitor frame time, dropped frames, GPU memory, and cook behavior at the target resolution and frame rate.

## Animation and modulation

The library's common parameters can be driven through normal TouchDesigner mechanisms:

- CHOP exports for LFO, audio analysis, envelopes, MIDI, OSC, sensors, and control surfaces;
- parameter expressions for deterministic relationships;
- Bind mode for two-way or structured parameter relationships where appropriate;
- Animation COMP/keyframes for timeline work;
- Python for event-driven changes and preset management.

Modulation belongs to the effect instance or rack, not the immutable package. A package supplies ranges, units, defaults, and optional modulation hints; it must not assume a specific controller.

## Color, alpha, and resolution

- Keep the project's working color space explicit. Color effects must state whether they expect working-space, scene-linear, or display-referred data.
- Treat straight versus premultiplied alpha deliberately. The default contract is to preserve input alpha and avoid modifying hidden RGB unless the effect documents why.
- Inherit input resolution unless the manifest declares a generator or fixed-resolution process.
- Use TouchDesigner's built-in texture information such as `uTD2DInfos` and `uTDOutputInfo`; avoid hard-coded resolutions.
- Apply `TDOutputSwizzle()` to pixel-shader color output as documented by Derivative.

## Production checklist

- Project lock exists and matches every active package.
- No effect is resolving from `latest`, a mutable branch, or a staging directory.
- Required package versions are archived for offline recovery.
- Update checks are notification-only during rehearsals and performances.
- Network access can fail without blocking image output.
- The previous package set and `.toe` are available for rollback.
- Target media, resolution, frame rate, color space, GPU, and outputs have been soak-tested.
- External plugins and Python packages have separately approved licenses and trust records.
