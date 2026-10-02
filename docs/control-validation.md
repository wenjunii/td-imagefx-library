# Control validation — 2026-10-02

The saved canonical `TD_ImageFX_Library.toe` was reopened in TouchDesigner
2025.32820 on Windows (embedded Python 3.11.10). All 16 live validators passed.
The checks exercised native parameter values, ranges, expressions, callbacks,
rendered pixels, cue behavior and real media frames. They did not manually drag
every GUI slider or qualify every possible combination of values.

| Area | Result |
| --- | --- |
| Full live suite | 16 validators passed; no failed checks |
| Rack, library, browser and updater | 45 pulse handlers and 42 rack value controls passed |
| Actual deferred rack events | 39 checks passed across all eight effect menus, both tested mix values, per-slot bypass, global bypass/enable and preset export |
| Effect packages | All 96 current effects; 511 numeric controls, 116 toggles and 14 reset pulses passed |
| Ink Dream Flow | 110 writable values; 583 checks passed |
| Ink Brush Flow | 120 writable values; 631 checks passed |
| Ink Radial Flow | 130 writable values; 684 checks passed |
| Layer Composite | 38 writable values, 5 pulse dispatches and 173 checks passed |
| Show Control | 38 checks passed, including 21 cue-editor values and dispatch wiring for 19 cue/transport/output buttons |
| Decoded layer images | 4 checks passed for PNG color/alpha, compositing and zero opacity |
| Layer video playback | 18 checks passed for independent transports, seeking, speed/reverse, pause, loop/end holding, restart/reload, mixed media and missing-file status |
| Show media playback | 9 checks passed for image/video readiness, advancing frames, pause/resume, embedded stereo audio decoding and layer parameter cues |
| Portable repository check | 221 tests completed successfully, with 4 expected Windows symlink-permission skips |
| Native artifacts | Hashes verified for the canonical TOE, 16 core TOXs and 124 immutable package TOXs |

## Verification improvements

`validate_control_surface.py` now checks that Parameter Execute DATs are active.
Browser Create must successfully create a component with an output in a temporary
target, as well as reject a missing target. The browser target's value, expression
and parameter mode are restored after testing.

Its separate `validate_deferred()` function changes parameters and invokes native
`pulse()` events, yielding to TouchDesigner's event loop between checks. It never
calls the callback handlers directly. The original rack preset and UI values are
restored before its report is written. Run it separately after the blocking
suite; see the README's complete live validation instructions.

Ink Radial Flow retains all Ink Brush Flow controls and adds ten radial controls.
Its checks include outward/inward direction, exact zero/off fallback, deterministic
seeking, stationary glitter/shimmer, alpha behavior and 1920×1080/3840×2160 output.
Show cues capture and animate its eligible parameters, including radial speed and
glitter, and pause/resume its clock. Earlier native render comparisons confirmed
the existing Dream and Brush outputs were unchanged by adding the radial module.

## Scope and reports

Detailed reports are generated locally in the ignored `build/envoy-validation/`
folder: `live-suite.json`, `control-surface.json`, `control-events.json`, the
individual module reports, `layer-composite-files.json`,
`layer-composite-videos.json`, and `show-media.json`. The live-suite report records
the source hash of each validator. Native artifact hashes are public in
[`native-validation.json`](native-validation.json).

Audience windows and audible output stayed disarmed. Output-window and audio-device
controls were checked for wiring only; actual projectors, monitor placement, audio
listening tests and sustained multi-output performance still require rehearsal on
the show hardware. The validators use temporary components and restore state;
they never save their test state into the canonical TOE.
