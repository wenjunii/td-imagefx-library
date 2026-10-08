# Control validation

## Clean release and Show Control review/export — 2026-10-07

The main `TD_ImageFX_Library.toe` was rebuilt from the current sources in
TouchDesigner 2025.32820 on the RTX 3080 Ti Laptop GPU. It contains the default
test-pattern cue, no personal show/media, and the updated Color Switch,
Two-Image Composition, Source Media, synchronized module switches, Look Editor
shortcuts, Projector Review and silent Export Video controls. The previous
personal TOE was backed up locally before replacement.

| Coverage | Result |
| --- | --- |
| Blocking native suite | All 22 validators passed |
| Packaged effects | 96 effects; 511 numeric controls, 116 toggles and 14 reset pulses passed |
| Synchronized switches | 878 two-way binding checks passed across designer, cue and composition workflows, rack master and slots |
| Real-frame suite | All 9 groups / 139 checks passed, including Source Media and composition playback |
| Show Control | 21 cue fields, 63 mapping values, 28 pulse routes and 14 panel-button dispatches covered |
| Look Editor navigation | 64 checks passed, including off-air targets and state preservation |
| Projector Review / Export | 14 checks passed; feed ordering/blackout, cue/draft/video-source exports, cancellation and original-state preservation |
| Export decoding | Five clips decoded without errors: 1920x1080 and 3840x2160 H.264, plus 640x360 H.264/Motion JPEG; expected 30 FPS, duration and frame count; no audio streams |
| Clean saved-file startup | 45 checks passed after reopening: default test cue/no media, no QA/draft/export nodes, no native errors, 1080p source, exact UHD wall, disabled rack/Ink Flow, blackout on, audio off and output windows closed |
| Portable release suite | 353 tests passed, with 4 expected Windows symlink-permission skips |

The audit now isolates bound-module fixtures from their original workflow, and
explicitly cooks ordered stateless GLSL passes before taking same-frame pixel
samples. These corrections prevent copied enable bindings and stale multi-pass
buffers from producing false failures. Installed two-way bindings are tested
separately. Review/export testing now uses a disposable Show Control copy, and
asserts that the original cue document, selection, unsaved editor fields and
main look remain unchanged. Native provenance includes both new show helpers.

Portable verification is performed on the exact publishable Git index snapshot.
The rejected dance auditions and their 17 local-only tests are preserved locally
but excluded from the release, which explains the lower portable count than a
full working-folder discovery. Test clips, native QA reports, backups and private
show files remain Git-ignored. Historical results below describe their own
earlier builds and are not claims about the current release.

The computer-use inspection checks the native Show Control panel, including the
right-hand inspector at normal text size. Parameter sweeps test ranges, values,
callbacks and rendered response; they do not manually drag every GUI slider or
test every combination. No audience output was opened and no audible sound was
played. Three-projector/processor mapping, stereo listening, codecs for actual
show media and sustained full-show performance still require hardware rehearsal.

## Source Media in the main project — 2026-10-07

The canonical main TOE now includes a **Source Media** page on `imagefx_demo`.
The existing `source_image` remains the stable workflow entry. File selection,
aspect fitting/cropping/stretching, anchor coordinates, letterbox RGBA and video
transport are available without replacing or reconnecting TOPs. Show cue media
and timing remain separate; see [Source Media](source-media.md).

The rebuilt project passed **21 live validators**, **9 real-frame groups
(139 checks)** and full repository verification with **320 local tests** (four
expected Windows symlink-permission skips). Source Media adds 26 native checks
and 17 real-frame checks, including alpha, anchor endpoints, HD/4K/custom output,
decoded PNG/MP4, play/pause, seek/restart/reload, reverse, loop/end hold,
missing-file status and cue isolation. The initial pixel test fixture was fixed
to keep its TOP connections within the copied designer COMP; the corrected
checks pass without relaxing their pixel assertions.

The saved canonical TOE was reopened successfully, its Source Media page was
inspected, and the visible **Preview Source** pulse opened the expected 1920 x
1080 source viewer. A credential scan of all 708 tracked/untracked publishable
files found no high-confidence credential matches.

All 704 pre-existing publishable files were snapshotted to the ignored
`build/backups/source-media-20261007-132457/` directory before edits. Unrelated
audition/prototype files remain unchanged and are not included in the native
workflow. Native artifact/source hashes were refreshed. No GitHub push, audience
output or audible audio test was performed; codec compatibility and sustained
multi-projector show performance still require rehearsal with actual media.

## Main-checkout integration — 2026-10-07

Color Switch and Two-Image Composition have also been merged into the original
main project folder and rebuilt as its canonical `TD_ImageFX_Library.toe`.
That build passed **20 live validators**, **8 real-frame groups (122 checks)**,
and repository verification with **306 local tests** (four expected Windows
symlink-permission skips). The count includes the 17 pre-existing local audition
tests, without adding the rejected audition to the native workflow.

The original TOE matched its previous native-validation record. It and all
affected existing files were backed up under the ignored
`build/backups/color-composition-integration-20261007-125549/` directory. All 26
pre-existing untracked files remained byte-identical; the existing README audition
notes were retained. The two new stages and their branch effects start disabled.
No commit or GitHub push was made, and no audience or audible outputs were tested.

## Color Switch and Two-Image Composition — 2026-10-07

The updated native build passed **20 live validators** and **8 real-frame
groups (122 checks)** in TouchDesigner 2025.32820. The new modules account for
284 native checks and 31 real-frame checks: RGB/hue replacement, pure-black
replacement, alpha, numeric endpoints, menus/toggles, layout/crop/fit pixels,
HD/4K canvas dimensions, independent A/B effects and rack selection, image/video
decoding, independent playback, pause, seek, reverse, loop, restart, and cue
capture/restore/legacy reset. Branch clock values are excluded from saved looks.

The portable verifier passed **289 tests**, with four expected Windows
symlink-permission skips. It verified 96 current effects, 124 immutable package
versions, 144 native artifacts, gallery baselines, benchmarks and source hashes.
A credential scan included all 678 tracked and untracked publishable files and
found no high-confidence credential matches. Nothing was pushed in this update.

Both new stages and all branch FX start disabled. The original checkout and its
uncommitted audition work were preserved in place; these changes are isolated
on `codex/color-switch-composition`. The rejected mocap prototypes are not part
of the build. No audience outputs or audible audio were enabled. Actual show
media, three-output rendering cost and projector hardware still need rehearsal.

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

The focused `validate_module_bindings.py` regression first audits the installed
two-way links without repairing them, then uses disposable cue copies to check
every module and rack slot in both directions. It covers independent states,
capture/recall, A/B branches, reorder, preset/slot reload, and the rack master
bypass's rendered pixels. The October 7, 2026 in-place main-TOE upgrade passed
830 focused checks and preserved the current cue document and designer look.
This focused result is not a new complete native-build certification.

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
