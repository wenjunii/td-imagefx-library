# Control validation

## Full controls + GitHub sync audit — 2026-10-05

A fresh load of the canonical TOE in TouchDesigner 2025.32820 passed all
**19 native validators**, followed by all **7 real-frame validation groups**
(**91 checks**). The portable verifier completed **263 tests**, with four
expected Windows symlink-permission skips. No effect-control failure was found
in this run; this does not mean every possible parameter combination is tested.

| Coverage | Result |
| --- | --- |
| Effect packages | 96 effects; 511 numeric controls, 116 toggles and 14 reset pulses passed |
| Rack/library/browser/updater | 45 pulse handlers, 42 rack values, plus 39 actual event-loop checks passed |
| Separate effect modules | All native module/range/pixel validators passed, including glitter/shimmer, particles, color, motion, layers, crop and workflow |
| Show Control | 45 checks; 21 cue fields, 63 mapping values, 23 pulse routes and 12 panel buttons covered |
| 4K wall output | 51 native checks and 4 real-frame button checks passed; exact UHD quadrant pixels and panoramic slices verified |
| Look Editor | Full-value recall/update/cancel/copy tests plus 11 decoded-media/pulse checks passed |
| Media and workflow events | 6 workflow/crop, 4 layer-image, 18 layer-video and 9 show-playback checks passed |
| Saved-file startup | 29 startup checks passed, including blackouts, disarmed audio, disabled rack defaults and no retained draft/QA nodes |

`validate_deferred_controls.py` now runs the seven asynchronous checks in order
after the blocking live suite. It refuses active shows/drafts or armed output,
checks fixture availability before starting, rejects unchanged stale reports,
records source hashes, and fails on any false check or restoration error. Show
playback is tested in a private disposable copy, not the operator's cue list.
Six portable regression tests protect the audit's inventory and result handling.
Reproduction commands, including the generated AV fixture, are in the README.

The canonical TOE and core TOX hashes still match the native build record.
The rejected dance-puppet prototype and local media remain outside this sync.
No audience window was opened and no sound was auditioned. Physical processor
output order, projection alignment, stereo listening and sustained show load
still require rehearsal with the actual connected hardware.

## Captured-look editing — 2026-10-05

The off-air Look Editor adds Recall Look, Update Cue, Save as New Cue and Cancel
Changes. All **19 native validators passed**, including **45 Show Control
checks**, 23 pulse dispatch routes and 12 panel-button callbacks. The tests cover
full captured-value recall, preview pixel response, isolation from the main
workflow/audience tracks, original-cue preservation, failed recall, cancellation,
cue-ID targeting, Save/Load Show persistence and playback/edit guards.

The separate real-frame look-media test passed **11 checks**: PNG/MP4 decoding,
advancing video, speed/loop/in point, all four actual parameter pulse events,
silent preview, safe restart, missing-media rejection and unchanged main design.
The existing asynchronous show-media test also passed **9 checks**, including
pause/resume and embedded stereo decoding, with physical audio disabled.
The computer-use inspection exercised visible Recall/Cancel buttons and caught
a clipped help label, which was shortened in the final panel layout.
After reopening the final canonical TOE, all 19 validators passed again;
11 look-editor and 18 wall-output startup checks also passed. The saved artifact
contains no active draft or temporary QA nodes. Blackouts remain on and audio off.

The portable suite completed **257 tests**, with four expected Windows symlink
permission skips. New transaction tests do not require TouchDesigner. Native
validation still does not certify show hardware or sustained performance.

## 4K wall output — 2026-10-05

The rebuilt TOE was reopened beside the library packages in TouchDesigner
2025.32820 on the RTX 3080 Ti Laptop GPU. All **19 live validators passed**.
The new wall validator passed **51 checks**, including exact UHD quadrant pixels
and seams, 5760x1080 panoramic slices, identical/independent/show routing,
fit/fill/stretch, confidence isolation, blackout, calibration and fail-closed
display selection. A separate real-frame event test passed **4 checks** for
Check Display, blocked Open Wall, Close Wall and display-policy changes.
The portable repository verifier also passed: **245 tests**, with four expected
Windows symlink-permission skips; native hashes, gallery and benchmarks agree.
A fresh canonical reopen passed **18 startup checks**: UHD output, blackout,
confidence text, unassigned/protected display, audio disarmed, and the existing
Ink Flow / video-FX / eight-slot disabled defaults.
The final UI inspection caught and corrected a relative-path expression in the
Source Validation text field. Native validation now evaluates that field and
checks diagnostics across the entire wall component, not just the output TOP.

The tested build replaces the canonical TOE; an ignored local backup preserves
the previous file. Audience output was never opened and no audio was auditioned.
Only the laptop display was connected: physical processor output order, HDMI
bandwidth, refresh stability and projector synchronization are **not verified**.
The numbered pattern is provided for that rehearsal. See [wall output](wall-output.md).

This rerun includes the existing module and cue validators but does not repeat
every separately deferred media/playback test from the earlier session below.
No validation test saves its temporary state into the canonical TOE.

## Full control audit — 2026-10-04

The saved canonical `TD_ImageFX_Library.toe` was reopened in TouchDesigner
2025.32820 on Windows (embedded Python 3.11.10). All 18 live validators passed.
The checks exercised native parameter values, ranges, expressions, callbacks,
rendered pixels, cue behavior and real media frames. They did not manually drag
every GUI slider or qualify every possible combination of values.

| Area | Result |
| --- | --- |
| Full live suite | 18 validators passed after reopening the saved TOE; no failed checks |
| Rack, library, browser and updater | 45 pulse handlers and 42 rack value controls passed |
| Actual deferred rack events | 39 checks passed across all eight effect menus, both tested mix values, per-slot bypass, global bypass/enable and preset export |
| Effect packages | All 96 current effects; 511 numeric controls, 116 toggles and 14 reset pulses passed |
| Ink Dream Flow | 110 writable values; 583 checks passed |
| Ink Brush Flow | 120 writable values; 631 checks passed |
| Ink Radial Flow | 130 writable values; 684 checks passed |
| Layer Composite | 40 writable values, 5 pulse dispatches and 179 checks passed, including source selection and unused-file unloading |
| Final Crop | 11 writable values and 46 checks passed: preset/manual crop pixels, range extremes, bypass, fixed-canvas modes and 1080p/4K sizes |
| Workflow | 78 checks passed across all 14 stages: moves, wiring, retained rack settings, invalid-order rejection and order-dependent pixels |
| Actual workflow/crop events | 6 checks passed for all 5 order buttons and Reset Crop on real TD frames |
| Show Control | 40 checks passed, including cue capture/restoration of workflow order and crop, 21 cue-editor values and dispatch wiring for 19 cue/transport/output buttons |
| Decoded layer images | 4 checks passed for PNG color/alpha, compositing and zero opacity |
| Layer video playback | 18 checks passed for independent transports, seeking, speed/reverse, pause, loop/end holding, restart/reload, mixed media and missing-file status |
| Show media playback | 9 checks passed for image/video readiness, advancing frames, pause/resume, embedded stereo audio decoding and layer parameter cues |
| Portable repository check | 237 tests completed successfully, with 4 expected Windows symlink-permission skips |
| Native artifacts | Hashes verified for the canonical TOE, 17 core TOXs and 124 immutable package TOXs |

The startup-default recheck also passed 45 checks after reopening the saved TOE:
Ink Flow, Apply Video Effects, and all eight rack slots were off; their parameter
defaults and exported preset state agreed; standalone Ink Flow/FX Rack TOXs also
loaded disabled. Both the default output and the bypassed rack preserved the
input pixels. Explicitly loading a cue or preset can still enable its saved effects.
The particle, glitch, color and motion routing validators now explicitly enable
rack slots during their effect-comparison checks and restore each slot's value,
expression and mode afterward; they no longer assume an enabled startup rack.

## Verification improvements

The full-control follow-up fixes a diagnostic false failure at extreme crop
values: a valid one-pixel-wide or one-pixel-high TOP is now accepted, while
zero-sized output still fails. A portable regression covers both cases.

The Workflow/Crop recheck includes portable geometry and ordering tests and two
native validators.
The full suite temporarily selects the default module order and bypasses crop
for legacy neighbor/resolution tests, then restores the user's order and crop
enable state. Its dedicated workflow validator tests other orders in a copy.
No test saves the live project, opens an audience output, or auditions audio.
See [workflow and crop](workflow-and-crop.md) for older-cue migration and the
difference between crop-sized and fixed-canvas output.

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
`layer-composite-videos.json`, `show-media.json`, `look-editor-media.json`, and
the consolidated `deferred-controls.json`. Both suite summaries record
the source hash of each dispatched validator. Native artifact hashes are public in
[`native-validation.json`](native-validation.json).

Audience windows and audible output stayed disarmed. Output-window and audio-device
controls were checked for wiring only; actual projectors, monitor placement, audio
listening tests and sustained multi-output performance still require rehearsal on
the show hardware. The validators use temporary components and restore state;
they never save their test state into the canonical TOE.
