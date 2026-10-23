# Control validation

## Live-look and playback release audit — 2026-10-23

Rebuilt the canonical TOE and all nineteen core TOXs with TouchDesigner
2025.32820. The build has zero builder, shader or preview errors; all 96 gallery
baselines still match. The 124 published package versions were preserved.

- **28 blocking groups / 5,412 checks passed**, including 1,268 two-way module
  bindings. The 96-package sweep covers 511 numeric controls, 116 toggles and
  14 package reset pulses. Ink Dream / Brush / Radial Flow passed 843 / 891 /
  944 checks respectively, including Animation Speed and glitter/pattern controls.
- **14 real-frame groups / 341 checks passed**. New cases compare custom ink
  Recall/GO output at 1920×1080 against independent renders, verify standby
  preparation does not replace the on-air image, and test crossfade frames.
  The animation audit passed 87 checks; live-draft output, cue notes and GO/Go
  Back across blackouts passed 43. Navigation also passed 25 blocking checks.
- Show Control covers **22 cue editor fields, 54 pulse dispatch routes and 19
  panel buttons**. Output hardware actions are intercepted; tests do not open
  audience windows or play audible sound. The UI and stored values are tested
  together with rendered pixels, not treated as equivalent evidence.
- Cue/draft export passed 14 checks. Five H.264/MJPEG files were independently
  decoded at 1080p, UHD and custom sizes. All had the expected frame count and
  non-black video, with no audio stream.
- The UHD wall recorder passed seven functional checks, including early Stop
  & Save and Cancel. Three completed files decoded with correct P1/P2/P3
  quadrants, confidence previews and diagnostics, and animated content.
- A final explicit File > Open of `TD_ImageFX_Library.toe` passed **19 startup
  checks**: stopped transport, blackouts on, audio/windows/live audition off,
  clean cue, intact bindings/clocks, no native errors and unchanged personal
  show. All **4,055 embedded text DATs** passed the credential scan. The Show
  Control panel was visually inspected after reopening. TouchDesigner retains
  the internal display name `TD_ImageFX_Library.1.toe`; no numbered TOE exists
  on disk, and the canonical artifact hash remained unchanged.
- **520 portable publication tests passed**, with four expected Windows
  symlink-permission skips. The staged publication snapshot excludes the local,
  rejected dance prototypes. Repository, credential, immutable-package,
  native-artifact provenance, gallery and benchmark checks passed.

Performance is not certified by these functional passes. GO/preload dispatch
took 0.036–0.090 ms in the generated 1080p fixture, but the longest indivisible
preparation step took **65.4 ms**. The 30-fps H.264 UHD wall fixture reported
**10 dropped frames**; the 25-fps MJPEG and early-stop fixtures reported zero.
Warnings are retained. Preload ahead of an entrance, let startup finish, and
rehearse sustained output/recording with the actual show media and hardware.

The computer-use skill was used for the native build and TouchDesigner checks.
Personal show JSON was preserved byte-for-byte; backups remain local under
`build/backups/pre-release-validation-20261023/`. The publication TOE contains
only the clean test-pattern cue. Physical projectors, processor, HDMI delivery
and speaker output were not tested. No credentials or personal media are in
the publication set. The local reports are `live-suite.json`,
`deferred-controls.json`, `cue-playback.json`, `look-animation.json`,
`show-live-look.json`, `show-navigation.json`, `show-review-export.json`,
`cue-export-media.json`, `wall-export.json`, `wall-export-media.json` and
`release-reopen.json` under
`build/envoy-validation/`.

## Clean-release control audit — 2026-10-20

Rebuilt the canonical TOE with TouchDesigner 2025.32820 and clean defaults.
The one-command blocking suite now includes Output Mode, Projector Review,
Projection Mapping, mapping resets/persistence and polygon masking; the
real-frame suite now includes output-mode and mapping button events. Native
reports record the validator entry point, source hash and check count.

- All **27 blocking groups** passed, covering all 96 effect packages, 511 numeric
  controls, 116 toggles and 14 package reset pulses; 830 two-way module/rack
  binding checks also passed. The three ink-flow modules include dot-pattern,
  animated/static glitter and shimmer coverage.
- All **11 real-frame groups / 196 checks** passed. Mapping events exercise all
  13 mapping pulses and all eight resets on each of the three dedicated projector
  panels, and verify the saved test show. Show Control's 48 pulse dispatch routes
  and fourteen panel buttons are covered; hardware-opening actions are safely
  intercepted, not sent to audience displays.
- Look Editor navigation passed **64 checks**. Cue/draft/media exports passed
  **14 checks** and independent decoding of all five H.264/MJPEG clips at 1080p,
  UHD and custom sizes, including exact frame counts and no audio track.
- UHD wall recording passed all **7 checks** for completion, early Stop & Save,
  cancellation, cleanup and preserved show state. Three finished recordings
  independently decoded at 3840×2160 with the correct P1/P2/P3 quadrants,
  three-up confidence preview, diagnostics and changing animation. The 30 FPS
  H.264 case reported five startup drops; 25 FPS MJPEG and the early-stop case
  reported zero. These short fixtures do not certify sustained show playback.
- Fixed a regression where reinstalling review/export controls removed
  **Projection Mapping** from the inspector's visible pages. A native regression
  check failed before the fix and passed in the rebuilt TOE.
- Portable suite: **462 tests, four expected Windows symlink-permission skips**.
  Repository/provenance verification covers 96 current IDs, 124 immutable
  versions and 144 native artifacts. The publication set excludes personal
  media, credentials and rejected dance experiments.

The computer-use skill was used for live TouchDesigner testing. Output windows
stayed closed and audio stayed disarmed; physical projectors, the wall processor
and speaker output are not certified by these checks. The existing 55-cue show
JSON remains byte-for-byte unchanged. Pre-audit TOE/show backups are local under
`build/backups/pre-control-release-20261020/`. The release TOE has only the clean
test-pattern cue and no personal media.

Fresh detailed reports remain local under `build/envoy-validation/`:
`live-suite.json`, `deferred-controls.json`, `look-editor-controls.json`,
`show-review-export.json`, `cue-export-media.json`, `wall-export.json` and
`wall-export-media.json`. Generated QA movies remain in `build/export-tests/`.

## UHD wall video export — 2026-10-20

Show Control's **Export Video** page now has **2x2 Wall + Confidence / Real-Time**.
It records the final 3840×2160 wall TOP without altering cues, mapping, transport,
blackout or the global clock. Physical output windows must remain closed.
The existing offline saved-cue/draft renderer is unchanged in purpose.

- 459 portable tests passed (four expected Windows symlink-permission skips),
  repository verification passed, and all 22 blocking native validator groups passed.
- The new native recorder audit passed fixed-resolution UI validation, missing
  confidence rejection, 30 FPS H.264 and 25 FPS MJPEG completion, early Stop & Save,
  cancellation, cleanup, and unchanged original show data/parameters.
- Decoded files were verified as 3840×2160, silent, with correct FPS, exact
  automatic-stop frame counts, all three projector quadrants, confidence previews
  and diagnostic text. Animated test content changed between the first/last frame.
- The original five cue/draft/media export cases and cancel regression passed.
  A local Select TOP bridges component boundaries; duration uses seconds because
  TD's frame units use project FPS rather than the selected Movie FPS.
- Real-time frame drops are reported, not hidden: the initial 30 FPS test reported
  five startup dropped frames. This is not a guarantee of sustained show performance.

The computer-use skill was used for the native build and visible Show Control
inspection. No audience windows were opened or audio auditioned. Personal show
JSON remains unchanged; the previous TOE and saved show are backed up under
`build/backups/pre-wall-export-20261020-212150/`. Test movies and reports stay in
ignored `build/export-tests/` and `build/envoy-validation/` (`wall-export.json`,
`wall-export-media.json`, `show-review-export.json`, `live-suite.json`).
See [wall recording](show-control.md#record-the-complete-2x2-wall-including-confidence-monitor).

## Mapping resets and show-file persistence — 2026-10-20

Projection Mapping now has seven section resets, a full selected-projector
reset, a full three-projector reset and **Save Mapping + Cues to Show File**.
The individual projector panels expose the same section resets. Full reset
includes brightness/gamma and 1080p resolution, but never cue data, track
selection, routing, output mode, display assignment, audio or blackout.
Resetting a mask also clears that projector's open polygon draft. Reset changes
are live but not auto-saved. Save uses the existing JSON/validated-backup path;
Load Show restores all calibration and defaults missing legacy fields before
validation, with blackout on/audio off. No new cue format is introduced.

- All 69 focused native reset/persistence checks passed, including every section
  on every projector from both control surfaces, exact full-mapping round trips,
  unapplied-draft exclusion, safe legacy defaults, invalid-load atomicity and
  unchanged operator cues/values.
- 249 mapping checks, 49 polygon checks, 11 deferred native-event checks and all
  22 blocking native validator groups passed. All 47 Show Control pulse routes
  were covered. The portable suite passed 444 tests (four expected Windows
  symlink-permission skips).
- The computer-use skill was used to inspect the visible mapping page and click
  soft-edge reset, mask reset and Save Mapping in a disposable off-air copy.
  The saved test JSON confirmed mask reset while the non-default brightness
  remained unchanged. No audience display was opened and audio stayed disabled.

The canonical TOE was rebuilt clean. Personal show JSON was not overwritten;
the preceding TOE/show are backed up under
`build/backups/pre-mapping-resets-20261020-194704/`.
Reports: `build/envoy-validation/projection-resets.json`,
`projection-mapping.json`, `projection-polygon.json`,
`projection-mapping-events.json`, and `live-suite.json`.
See [reset and save instructions](projection-mapping.md#reset-mapping).

## Cursor-drawn custom projection masks — 2026-10-20

**Projection Mapping → Draw Custom Mask (Mouse)** adds a separate per-projector
polygon editor. Click to place 3–32 points, drag handles, close the contour,
insert on an edge, delete a selected point and undo. Concave outlines are
supported; crossed, touching, duplicate and zero-area outlines are rejected.
Draft feather, inversion and level are staged until Apply Mask. Cancel / Reload
does not modify the live calibration or reopen/reposition the window.

- 49 focused native checks passed: GPU/CPU concave-fill agreement, all three
  projectors, exact bypass, inversion/feather/level, invalid-apply retention,
  empty-polygon fail-closed behavior, direct/wall equivalence, show round trips,
  older-show defaults and all six toolbar callbacks.
- 249 mapping regression checks passed, including idempotent installation and
  no duplicate polygon-editor widgets. All 22 blocking native validator groups
  passed. The 431-test portable suite passed with four expected Windows symlink
  permission skips; repository verification scans 701 files for credentials.
- The computer-use skill was used to inspect the editor and actually click,
  drag, insert, delete, undo, close, feather, apply and reload a test outline.
  No physical projector window was opened and audio remained disabled.

The canonical TOE was rebuilt with clean defaults. The operator's show JSON is
unchanged; the preceding TOE and show are backed up in
`build/backups/pre-polygon-mask-20261020/`. Custom points are show calibration,
not cue look data. A polygon lives in the projector frame after corner pinning;
Apply resets only its mask transform to neutral. This is one polygon per output,
not a multi-region/freeform mesh editor. Hardware alignment still needs rehearsal.

Reports: `build/envoy-validation/projection-polygon.json`,
`projection-mapping.json`, and `live-suite.json`.
Usage: [Draw a custom mask](projection-mapping.md#draw-a-custom-mask-with-the-cursor).

## Per-projector mapping, masks and soft edges — 2026-10-20

Added **Show Control → Projection Mapping**, with separate two-way Shape,
Mask, Edges and Output control panels for all three projectors. Four-corner
geometry and source crop are joined by rectangle/ellipse/image masks,
position/size/rotation, inversion, mask level/feather, all-edge softness and
blend falloff. Masks default off; missing enabled image masks fail closed,
including when inverted. Show-level calibration is saved separately from cue
looks. Older shows load with neutral defaults for the new controls.

- 245 focused native checks passed, including pixel response, numeric bounds,
  mask files/channels, all three projector bindings, safe reinstallation,
  invalid-geometry retention and show-file round trips.
- 10 deferred native event checks passed: exact-once button dispatch, selected
  reset, unaffected projector/output settings, bindings and safety state.
- All 22 existing blocking native validation groups passed. Portable repository
  verification passed 407 tests with four expected Windows symlink-permission
  skips; the credential scan checked 698 files and verified 144 native artifacts.
- Direct feeds and every wall source mode use the calibration. Already mapped
  Show Control feeds are not mapped twice. The confidence quadrant remains
  unmasked, and its preview feeds include the calibration.

The computer-use skill was used to rebuild and test in TouchDesigner and inspect
the actual mapping controls. No audience window was opened or audio auditioned.
The canonical TOE is a clean build; the saved 54-cue show was restored into the
live session without modifying its JSON file. Previous TOE/show backups are in
`build/backups/pre-projection-mapping-20261020/`. No GitHub sync was performed.
Hardware alignment, blending and sustained venue playback still need rehearsal.

Reports: `build/envoy-validation/projection-mapping.json`,
`projection-mapping-events.json`, and `live-suite.json`.
Usage: [Projection mapping](projection-mapping.md).

## Full 2x2 wall canvas in Projector Review — 2026-10-20

**Projector Review → Review View** now offers Auto, Three Projectors,
2x2 Video Wall, each individual projector, and Confidence Monitor. Auto follows
Output Mode: a full packed 4K canvas for wall delivery, or three side-by-side
feeds for direct displays. The wall preview reads the actual `out1_wall_4k`
output; it is not a separate reconstruction. Its inline thumbnail preserves
aspect ratio, and Enlarge Review opens the selected full-resolution TOP viewer.

All 33 focused native checks passed: actual quadrant pixels, confidence
visibility/toggle, projector blackout with confidence retained, all seven menu
choices, panel dimensions, automatic mode following, cue-preserving
reinstallation, and no output windows opened. Report:
`build/envoy-validation/projector-review.json`.

All 22 existing blocking native validator groups also passed. Portable
verification passed 393 tests with four expected Windows symlink-permission
skips, checked 694 files for credentials, and verified 144 native artifacts.
The computer-use skill was used to build and inspect the new review in
TouchDesigner; no physical projector window was opened.

The previous main TOE and saved show JSON are backed up under
`build/backups/pre-wall-review-20261020/`. The saved show JSON remains
byte-for-byte unchanged. This operator preview does not change cue destinations,
physical Output Mode, or safety blackouts. Hardware output was not tested.

## Clear physical Output Mode — 2026-10-20

Added **Output Mode** as the second Show Control tab: Direct Displays or
4K Wall Processor, with Check/Open/Close All, display selection, blackout links
and live status. Direct output uses three separate display windows. The existing
cue tracks, content routing and saved looks are unchanged; Projector Review
follows the selected delivery mode automatically.

- 51 focused native checks passed for mode switching, visible controls,
  bindings, all three feed/window connections, 1080p/4K/720p dimensions,
  unassigned-display rejection and cue-preserving reinstallation.
- 12 deferred native event checks passed for exact-once Check/Open/Close
  dispatch, closing on mode/display edits, preview updates and safe blackouts.
- All 22 existing blocking native validation groups passed, including all
  34 Show Control pulse endpoints. All 383 portable tests passed (four expected
  Windows symlink-permission skips); the credential scan checked 693 files.
- Clean canonical TOE and core artifacts rebuilt; 144 native artifacts verified.
  Personal show JSON remains byte-for-byte unchanged. Previous TOE and JSON are
  backed up under `build/backups/pre-output-mode-20261020/`.

The computer-use skill was used to build/test in TouchDesigner and inspect the
new tab. No physical projector window was opened and no audio was auditioned.
Tests cover software routing and safety; hardware/EDID placement and sustained
multi-output playback still need venue rehearsal. Nothing was pushed to GitHub.
Reports: `build/envoy-validation/output-mode.json` and `output-mode-events.json`.

## Wall Output inside Show Control — 2026-10-20

Added a **Wall Output** tab with fourteen two-way parameter links, three display
buttons, and read-only diagnostics. Both safety blackouts are accessible here;
the original wall module remains the authority. Linked defaults, menus and
numeric limits match the originals. Check/Open/Close reuse the existing safe
display controller and never release blackout. Look Editor and review/export
callback guards remain independent.

- 151 native wall checks passed, including every linked value in both directions,
  all source/fit menu choices, toggle states, display-index range/defaults,
  idempotent installation, pixel mapping and UHD output.
- 12 deferred native event checks passed, including exact-once dispatch of all
  three added buttons, fail-closed opening and linked display-policy changes.
- All 22 blocking native validator groups passed; Show Control now audits all
  31 pulse endpoints. All 362 portable tests passed (four expected Windows
  symlink-permission skips), along with credentials/artifacts/gallery checks.
- Rebuilt the clean canonical TOE; saved show JSON is byte-for-byte unchanged.
  A local backup is under `build/backups/pre-show-wall-tab-20261020/`.

The computer-use skill was used for native building and inspection of the new
tab. No physical output was opened, no audio auditioned, and no GitHub sync was
performed. Hardware projector/processor testing still requires the real setup.

## Transparent Calligraphic Shadow — 2026-10-20

Added a default-off **Subject → Transparent Background** toggle. It removes
the paper fill, excludes hidden transparent pixels from subject masking,
clips out-of-frame samples, and composites the input, shadow, particles, and
glitter with alpha-aware mixing. Output is straight RGBA for Layer Composite.
The main TOE and core components were rebuilt without personal media/cues;
the prior TOE and shadow component are backed up locally under
`build/backups/pre-shadow-alpha-20261020/`.

- All 22 blocking native validators passed in TouchDesigner 2025.32820.
- 18 dedicated alpha checks passed: soft/partial source alpha and edge RGB,
  zero hidden RGB, subject opacity, shadow coverage beyond the cutout,
  paper-independent transparency, particle/glitter coverage, empty output,
  premultiplied dry/wet interpolation, exact dry bypass, opaque-mode return,
  and fully transparent black/white inputs in all three subject-mask modes.
- 27 pixel-exact comparisons with the previous shadow component passed with
  transparency off, at three times, three mask modes, and three layer setups.
- Transparent output remained finite at native 1920×1080 and 3840×2160.
- Show Control capture, apply, and older-look default reset passed; nested
  composition and cue-template copies contain the new control.
- Portable verification of tracked working files passed all 355 tests (four
  expected Windows symlink-permission skips), credentials and artifact checks.

The computer-use skill was used for native building/testing; a checkerboard
composite was visually inspected. Reports and previews are ignored local files
under `build/shadow-alpha-review/` and `build/envoy-validation/`. No GitHub
publication was performed. This is functional validation, not a long-running
multi-projector performance certification.

## Flowing dot pattern in the three ink modules — 2026-10-20

The canonical main TOE and reusable components were rebuilt in TouchDesigner
2025.32820, then the saved main TOE was reopened before the final native audit.
The new **Dot Pattern / Dot Pattern Motion** layer is default-off and inherited
by Ink Dream Flow, Ink Brush Flow and Ink Radial Flow, including the nested
composition branches and cue decks. No reference artwork or private media is
embedded. The previous main TOE is backed up locally under
`build/backups/pre-dot-pattern-20261020/`.

| Coverage | Result |
| --- | --- |
| Ink Dream Flow | All 134 writable values; 708 native checks passed |
| Ink Brush Flow | All 144 writable values; 756 native checks passed |
| Ink Radial Flow | All 154 writable values; 809 native checks passed |
| Full blocking native suite | All 22 validators passed after reopening |
| Pattern cue integration | Capture, parameter fade midpoint/end, rendered changes, pause/resume, and older-look reset passed in all three modules |
| Backward visual compatibility | 18 exact pixel comparisons passed against the prior main-branch components, at three times, with glitter off/on and pattern off |
| Native build | 96 effects, no builder/shader/preview errors; 144 artifact hashes refreshed |
| Portable repository verification | 355 tests passed, 4 expected Windows symlink-permission skips; credential scan and generated-artifact checks passed |

Pattern controls were swept at their range endpoints and representative values,
with distinct pixels checked for every menu choice. Coverage includes both
composite modes, every surface, RGBA channels, density/shape/folding,
zero-mix/off bypass, independent freeze/seek, layer masking, transparent alpha,
both glitter layers on dots, and native 1080p/4K output dimensions. Visual
inspection refined the defaults away from overly stretched streaks toward
separated flowing rows of dots. The native parameter page and its enable switch
were also checked through the computer-use skill.

Portable verification uses a copy of tracked working files to leave the
unrelated local dance experiments and their tests untouched. QA renders and
reports remain under ignored `build/dot-pattern-review/` and
`build/envoy-validation/`; no GitHub publication was performed for this change.
Tests do not certify every parameter combination or sustained multi-projector
performance. Audience windows and audio were not armed.

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
