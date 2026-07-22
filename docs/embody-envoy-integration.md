# Embody, Envoy, and TD knowledge integration

The ImageFX live-QA integration uses:

- Embody `6.0.131` for Envoy's live TouchDesigner tools;
- the local `td-ai-assistant` index for TouchDesigner, StreamDiffusionTD,
  Scope, and DotSimulate knowledge; and
- `td-knowledge-mcp` as one MCP server that exposes the knowledge tools, the
  checked ImageFX project context, and the connected Envoy tools.

The integration is intentionally separate from release generation. The
canonical builder only accepts a blank `/project1`, owns
`/project1/td_imagefx` and `/project1/imagefx_demo`, and writes
`TD_ImageFX_Library.toe` atomically. An Embody COMP in that project would break
the builder boundary and could leak development tooling into the released
project.

## Files

| Path | Purpose |
| --- | --- |
| `integrations/embody/project-context.json` | Public-safe network, output, workflow, safety, and validation contract |
| `integrations/embody/mcp-config.example.json` | Combined bridge example with local-path placeholders only |
| `.codex/config.toml.example` | Portable project-scoped Codex MCP configuration template |
| `integrations/embody/check_td_bridge.py` | Official-client smoke test for the contract, knowledge index, and optional Envoy session |
| `integrations/embody/envoy-validation-plan.json` | Ordered read-only live audit |
| `touchdesigner/scripts/install_dev_harness.py` | Non-saving compiled-core installer for a disposable project |
| `touchdesigner/scripts/validate_live_suite.py` | One-command Textport runner for all ten tracked live validators with a consolidated ignored report |
| `touchdesigner/scripts/validate_reference_video_modules.py` | State-restoring rendered-pixel sweep for the three independently adjustable reference-video recreations |
| `touchdesigner/scripts/validate_live_project.py` | Read-only health, error, and TOP structural report |
| `touchdesigner/scripts/validate_rack_selection.py` | State-restoring live regression test for all eight rack effect menus |
| `touchdesigner/scripts/validate_all_effect_parameters.py` | State-restoring rendered-pixel sweep for every numeric component, toggle, rack mix, time, and per-effect time scale in all 96 latest packages |
| `touchdesigner/scripts/validate_particle_module.py` | Pixel checks for all eight shapes, all eight motion modes, every numeric slider, time behavior, range metadata, bypass, and routing |
| `touchdesigner/scripts/validate_ink_flow_module.py` | Pixel checks for both ink styles, water particles, bypass, and deterministic motion |
| `touchdesigner/scripts/validate_glitch_fusion_module.py` | Pixel checks for 24 glitch styles, bypass, timing, seed, routing, and shader diagnostics |
| `touchdesigner/scripts/validate_color_adjustment_module.py` | Pixel checks for neutral grading, all 72 numeric slider components, sixteen overlay modes, alpha preservation, routing, range metadata, and shader diagnostics |
| `touchdesigner/scripts/validate_motion_studio_module.py` | Pixel checks for 40 motion styles, bypass, manual timing, easing, edges, bounded trails, routing, and shader diagnostics |
| `touchdesigner/scripts/validate_output_resolution.py` | Live checks for default HD, 4K UHD, custom dimensions, bounds, and output propagation |

Detailed setup and commands are in
[`integrations/embody/README.md`](../integrations/embody/README.md).

## Operating model

The combined bridge must be started with
`--project-context integrations/embody/project-context.json` and the
project-local `--envoy-config integrations/embody/local/.embody/envoy.json`.
Before live work, call `get_td_project_context`; it must return
`td-imagefx-library`. The bridge also verifies both managed root operators
before it exposes Envoy tools. Then query the knowledge library before writing
TouchDesigner Python or GLSL.

For an audit, follow `envoy-validation-plan.json`: confirm the TD instance,
record baseline performance, discover the network, run `HealthCheck`, check
recursive errors and warnings, capture the eleven approved TOPs, and compare
final performance. Envoy's `capture_top` quality verdict must pass, and the
images still require visual inspection. A clean operator graph does not prove
that a frame is visible or aesthetically correct.

`check_td_bridge.py` separates local MCP/knowledge health from live Envoy
health; add `--require-envoy` only after the harness is open and Embody's Envoy
switch is enabled. Its child-server output is quiet by default; add `--verbose`
for MCP diagnostics. If Embody advances from port 9870 during a rapid restart,
the bridge follows the active project-local registry entry automatically;
`--port` remains the fallback when that registry is unavailable.
`validate_rack_selection.py` is an explicit mutation test:
it snapshots the rack preset, exercises all eight menu callbacks, restores the
snapshot in a `finally` block, and never saves the project.
`validate_all_effect_parameters.py` is likewise a disposable-harness-only
mutation test. It restores the complete rack preset, demo routing, source time,
resolution, and timeline state in a `finally` block and never saves. Its report
records the context used for controls that only apply in a particular mode or
state.
`validate_live_suite.py` runs the structural audit and every state-restoring
regression in order. Its documented Textport invocation copies `globals()` so
TouchDesigner objects remain available inside each isolated validator scope;
the runner writes `build/envoy-validation/live-suite.json` and never saves.

The reusable browser includes an Execute DAT that defers `UpdateSelection()` by
one frame on project startup and component creation. This forces Movie File In
to reload the selected gallery PNG after deserialization; the live validator
checks that startup contract, while `capture_top` proves the preview is not
black or fully transparent.

Any mutation requires explicit authorization and belongs in the disposable
harness, preferably under `/project1/imagefx_sandbox`. Immutable package `.tox`
versions, the canonical `.toe`, native validation records, and approved visual
baselines remain protected.
