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
`ParticleRandomMove.tox`, `GlitchFusion.tox`, and `FxRack.tox`,
synchronizes their extension DATs from `touchdesigner/extensions/`, repairs
legacy absolute Pixel Shader DAT paths inside loaded effects, points every
library root at the checkout, creates the same managed paths used by the
canonical project, and exposes HD, 4K UHD, and custom output-resolution
controls. It refuses to run in `TD_ImageFX_Library.toe`, refuses to
replace existing managed roots, and never saves a project. Run it through Envoy
for a single undoable operation, or use a fresh local harness when you need a
clean reset.

Do not run `touchdesigner/scripts/build_project.py` in this harness. Native
rebuilds require a separate blank TouchDesigner project.

## Connect the combined MCP bridge

Copy `mcp-config.example.json` to the MCP configuration used by your client and
replace every `C:\ABSOLUTE\PATH\TO\...` placeholder with an absolute local path.
Do not commit the resulting local configuration. The bridge connects to Envoy
on port 9870, queries the assistant's FAISS index, and serves this repository's
`project-context.json`.

After reconnecting, call `get_td_project_context`. It must return
`project_id: td-imagefx-library`; a different project ID means the client is
still using another bridge configuration.

## Validate a live project

`envoy-validation-plan.json` is the ordered, read-only audit contract. It:

1. loads the ImageFX context and relevant TD documentation;
2. confirms the selected TD/Envoy instance and records baseline performance;
3. checks the managed network and calls `HealthCheck`;
4. checks recursive operator errors and warnings;
5. captures the demo, ink-flow, random-particle, Glitch Fusion, rack, and
   browser preview TOPs with Envoy's pixel-quality verdict; and
6. compares final performance before running the offline repository verifier.

For a local JSON diagnostic from TouchDesigner, run:

```python
script = r"C:/absolute/path/to/td-imagefx-library/touchdesigner/scripts/validate_live_project.py"
namespace = {"__file__": script, "__name__": "td_imagefx_live_validation"}
exec(compile(open(script, encoding="utf-8").read(), script, "exec"), namespace)
result = namespace["validate"]()
print(result)
```

The report is written to the ignored
`build/envoy-validation/live-project.json`. It checks structure, health,
recursive `errors`, `warnings`, and `scriptErrors`, output family and
resolution. Envoy's `capture_top` remains the required pixel-level check:
structural success alone cannot prove that an image is visible or correct.

## Safety boundary

- Treat live access as read-only unless a specific edit is requested.
- Keep experiments under `/project1/imagefx_sandbox` or in a disposable copy.
- Never externalize immutable package `.tox` files.
- Never save the harness over `TD_ImageFX_Library.toe`.
- Never approve gallery baseline changes without human visual review.
- Keep update discovery notification-only; installation and activation remain
  separate, explicit actions.
