# Embody, Envoy, and TD knowledge integration

This integration combines three local tools without changing the ImageFX release
boundary:

- Embody `6.0.131` supplies Envoy's live TouchDesigner inspection and control.
- `td-ai-assistant` supplies the indexed TouchDesigner knowledge library.
- `td-knowledge-mcp` exposes both through one MCP server and adds the checked
  ImageFX project profile in `project-context.json`.

The canonical `TD_ImageFX_Library.toe` remains a generated release artifact.
Embody belongs in a separate, ignored QA project because the native builder owns
exactly `/project1/td_imagefx` and `/project1/imagefx_demo` and rejects unrelated
top-level operators.

## Create the local QA harness

1. Create `integrations/embody/local/` and save a blank TouchDesigner project as
   `TD_ImageFX_DevHarness.toe` in that folder.
2. Drag `Embody-v6.0.131.tox` into the harness. Complete its setup wizard, enable
   Envoy, and keep it bound to `127.0.0.1`. Port `9870` is the default.
3. Set Embody's AI project root to `integrations/embody/local/` so generated
   assistant files remain local and ignored.
4. Run this in the TouchDesigner Textport, replacing the checkout path:

   ```python
   script = r"C:/absolute/path/to/td-imagefx-library/touchdesigner/scripts/install_dev_harness.py"
   exec(
       compile(open(script, encoding="utf-8").read(), script, "exec"),
       {"__file__": script, "__name__": "__main__"},
   )
   ```

The installer loads the tracked `TDImageFXLibrary.tox`, `InkFlowFusion.tox`,
`ParticleRandomMove.tox`, `GlitchFusion.tox`, `ColorAdjustment.tox`, and
`MotionStudio.tox`, and `FxRack.tox`,
synchronizes their extension DATs from `touchdesigner/extensions/`, repairs
legacy absolute Pixel Shader DAT paths inside loaded effects, points every
library root at the checkout, creates the same managed paths used by the
canonical project, and exposes HD, 4K UHD, and custom output-resolution
controls. It refuses to run in `TD_ImageFX_Library.toe`, refuses to
replace existing managed roots, requires the exact unnumbered
`TD_ImageFX_DevHarness.toe` identity, and never saves a project. Run it through
Envoy for a single undoable operation, or use a fresh local harness when you
need a clean reset.

The direction of synchronization is tracked source into the harness, not the
harness into the canonical `.toe`. After an experiment is approved, encode it
in the tracked manifests, shaders, extensions, callbacks, or builder scripts;
validate it; then run `build_project.py` from a separate blank project to
regenerate `TD_ImageFX_Library.toe`. Changes made only in the ignored harness
remain local.

Do not run `touchdesigner/scripts/build_project.py` in this harness. Native
rebuilds require a separate blank TouchDesigner project.

## Run the complete live suite

After installing the harness, run all nine tracked live validators with one
Textport command:

```python
script = r"C:/absolute/path/to/td-imagefx-library/touchdesigner/scripts/validate_live_suite.py"
scope = dict(globals())
scope.update({"__file__": script, "__name__": "__main__"})
exec(compile(open(script, encoding="utf-8").read(), script, "exec"), scope)
```

The copied Textport globals are required by rendered-pixel checks that create
temporary TouchDesigner operators. The suite writes the ignored
`build/envoy-validation/live-suite.json` summary and all individual reports,
restores each validator's temporary state, and never saves the harness. A full
run can take several minutes.

Opening the harness does not by itself prove that Envoy is online. Confirm
Embody's Envoy switch is enabled after every launch and that the active
instance in `integrations/embody/local/.embody/envoy.json` is listening before
starting a live audit.

## Connect the combined MCP bridge

Copy `mcp-config.example.json` to the MCP configuration used by your client and
replace every `C:\ABSOLUTE\PATH\TO\...` placeholder with an absolute local path.
Do not commit the resulting local configuration. The bridge follows this
project's active Embody registry entry (with port 9870 only as a fallback),
queries the assistant's FAISS index, and serves this repository's
`project-context.json`. Before it exposes live tools, it verifies both
`/project1/td_imagefx` and `/project1/imagefx_demo`; a FlexGPU or other TOE on
the selected port is rejected.

After reconnecting, call `get_td_project_context`. It must return
`project_id: td-imagefx-library`; a different project ID means the client is
still using another bridge configuration.

### Codex project-scoped configuration

Codex can keep a different `td-knowledge` project contract in each trusted
repository. Copy `.codex/config.toml.example` to `.codex/config.toml`, replace
the placeholders with absolute local paths, and restart Codex or start a new
task from this repository. The local file is ignored because its paths are
machine-specific.

The project-scoped entry deliberately uses the same `td-knowledge` server name
as the user-level entry. Inside this repository, Codex loads the closer
`.codex/config.toml` and supplies `integrations/embody/project-context.json`;
outside it, the user's existing server configuration remains active. Confirm
the active contract before live work:

```text
get_td_project_context -> project_id: td-imagefx-library
```

### Check the complete bridge

Run the standalone checker with the Python interpreter from the
`td-ai-assistant` virtual environment. With the three repositories next to one
another in the same workspace, its default paths are sufficient:

```powershell
..\td-ai-assistant\venv\Scripts\python.exe integrations\embody\check_td_bridge.py
```

This checks the MCP subprocess, the ImageFX project contract, and knowledge
retrieval even when TouchDesigner is closed. Require the live Envoy connection,
managed-root diagnostics, and project performance as well with:

```powershell
..\td-ai-assistant\venv\Scripts\python.exe integrations\embody\check_td_bridge.py --require-envoy
```

Child-server diagnostics are quiet by default so a normal successful shutdown
does not print transport cleanup noise. Add `--verbose` when diagnosing MCP
startup or shutdown.

If the result says Envoy is offline or Codex reports `Transport closed`, first
confirm that TouchDesigner is still running and Embody's Envoy switch is on.
Then confirm that the project-local `.embody/envoy.json` selects the intended
ImageFX harness. During a rapid restart, Embody may select the next free port
while Windows releases the previous socket; the bridge now follows that active
registry entry automatically. Use `--port` only as a fallback when the registry
is unavailable.
Clients that honor MCP `tools/list_changed` notifications refresh the live
catalog automatically. If Codex still shows only the five local tools after
Envoy is listening, restart the Codex task once to reconnect the
project-scoped MCP process.

## Validate a live project

`envoy-validation-plan.json` is the ordered, read-only audit contract. It:

1. loads the ImageFX context and relevant TD documentation;
2. confirms the selected TD/Envoy instance and records baseline performance;
3. checks the managed network and calls `HealthCheck`;
4. checks recursive operator errors and warnings;
5. captures the demo, ink-flow, random-particle, Glitch Fusion, Color
   Adjustment, Motion Studio, rack, and browser preview TOPs with Envoy's pixel-quality
   verdict; and
6. compares final performance before running the offline repository verifier.

For a local JSON diagnostic from TouchDesigner, run:

```python
script = r"C:/absolute/path/to/td-imagefx-library/touchdesigner/scripts/validate_live_project.py"
namespace = dict(globals())
namespace.update({"__file__": script, "__name__": "td_imagefx_live_validation"})
exec(compile(open(script, encoding="utf-8").read(), script, "exec"), namespace)
result = namespace["validate"]()
print(result)
```

The report is written to the ignored
`build/envoy-validation/live-project.json`. It checks structure, health,
recursive `errors`, `warnings`, and `scriptErrors`, output family and
resolution, all eight rack selections, and the browser's deferred preview
startup callback. Envoy's `capture_top` remains the required pixel-level check:
structural success alone cannot prove that an image is visible or correct.

For the reported rack-menu regression, run the state-restoring validator:

```python
script = r"C:/absolute/path/to/td-imagefx-library/touchdesigner/scripts/validate_rack_selection.py"
namespace = dict(globals())
namespace.update({"__file__": script, "__name__": "td_imagefx_rack_validation"})
exec(compile(open(script, encoding="utf-8").read(), script, "exec"), namespace)
result = namespace["validate"]()
print(result)
```

It exercises the effect-selection callback in all eight slots, verifies the
newly loaded package, and restores the exact preset snapshot in a `finally`
block. It changes live rack state temporarily, so run it only in the ignored
development harness. It never saves the project.

For a state-restoring rendered-pixel regression across the complete package
catalog, run `touchdesigner/scripts/validate_all_effect_parameters.py` with the
same Textport pattern. It loads all 96 latest effects through slot 1, checks
every numeric component and toggle plus rack mix, effective time, and local
time scale, validates range/clamp metadata, finite pixels, diagnostics, and QA
resolution, then restores rack, demo, source-time, resolution, and timeline
state. Run it only in the ignored development harness; it never saves.

For a state-restoring pixel regression of the separate Random Particles stage,
run `touchdesigner/scripts/validate_particle_module.py`. It verifies all eight
shapes and eight motion modes, every numeric slider component, the 500-column
maximum, range/clamp metadata, automatic/manual resolved time, bypass, seed,
rack routing, and shader diagnostics, then restores every artist-facing value.

For a state-restoring pixel regression of the dedicated grading stage, run
`touchdesigner/scripts/validate_color_adjustment_module.py` with the same
Textport pattern. It verifies neutral output, independent module/mix bypass,
the adjustment families, every numeric slider component, all sixteen overlay
blend modes, alpha preservation, rack routing, and shader diagnostics, then
restores every artist-facing value.

For a state-restoring pixel regression of Motion Studio, run
`touchdesigner/scripts/validate_motion_studio_module.py` with the same Textport
pattern. It verifies all 40 styles, master/mix/amount bypass, manual timing,
the exact easing and edge menus, bounded trail sampling, rack routing, output
resolution, and shader diagnostics, then restores every artist-facing value.

If opening `TD_ImageFX_DevHarness.toe` leaves a numbered project name such as
`TD_ImageFX_DevHarness.1.toe` or `.2.toe` in TouchDesigner's title, the file was
copied from a numbered recovery project and retained that embedded identity.
Use **File > Save Project As**, select the unnumbered
`TD_ImageFX_DevHarness.toe`, and approve replacement only when the dialog names
that ignored harness. Close TouchDesigner and reopen the unnumbered file before
running the installer. The installer rejects numbered identities so they
cannot silently become the active QA project. Never approve a replacement
dialog for `TD_ImageFX_Library.toe`.

## Safety boundary

- Treat live access as read-only unless a specific edit is requested.
- Keep experiments under `/project1/imagefx_sandbox` or in a disposable copy.
- Never externalize immutable package `.tox` files.
- Never save the harness over `TD_ImageFX_Library.toe`.
- Never approve gallery baseline changes without human visual review.
- Keep update discovery notification-only; installation and activation remain
  separate, explicit actions.
