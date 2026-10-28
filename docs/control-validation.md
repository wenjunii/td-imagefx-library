# Control validation

## Full control and publication recheck — 2026-10-28

The clean publication TOE was reopened and audited again, separately from the
operator's two-cue session. No operator cue or media was used as release content.

- **757 portable tests** passed (four expected Windows symlink skips), with
  immutable-history, artifact/source-hash, credential and generated-file checks.
- **29 native groups / 6,609 checks** passed for the control inventory, value
  limits, bindings, menus and callbacks. This includes all **58 Show Control
  pulses, 20 panel buttons and 63 mapping/grade controls**.
- **17 frame-based groups / 590 checks** passed for real event dispatch,
  media, cue playback, Continue/Follow, editing, mapping and feedback.
- **12 additional groups / 926 checks** passed for force response, activation,
  pattern-relative motion, puppet/layer controls, 14-section navigation and
  export. **83 older-cue checks** passed with local prepared-motion fixtures.
- **16 readiness checks** now include slider minimum/midpoint/maximum and
  defaults, all five FPS menu entries, read-only result fields, non-arming
  pulses, 1/3/12-frame cue warm-up and recording/cancellation behavior.
- **36 panoramic-preview checks** passed, plus visible maximize/restore and
  focus testing. **62 clean-startup checks** passed; **4,307 runtime text DATs**
  passed the credential scan. The published TOE's hash stayed unchanged during
  these tests. The personal main TOE was restored with **12 preservation checks**
  confirming both cues, effect values, editable show values and the canonical
  file hash were unchanged, with no native errors or warnings.

The independent export check exposed a test-fixture mistake: the first readiness
test reused the original wall, whose Show Control master blackout correctly
made the projector quadrants black. Encoder completion alone was not sufficient
evidence of a calibration picture. The validator now copies both Show Control
and Wall Output into an isolated host, verifies RGB quadrant pixels and a
nonblank confidence monitor, and confirms the original wall values, expressions
and modes are untouched. It also refuses armed audio, released blackouts,
open audience windows and overlapping sample/export/audit jobs before changes.

The corrected warm-up recordings each contain 90 decoded frames at
3840×2160 / 30 FPS, with zero reported encoder drops in this short run.
Independent ffprobe/ffmpeg checks passed for **26 export clips**: codec,
dimensions, frame rate/count, complete decoding and silent audio; packed-wall
clips also passed quadrant-order and confidence-content checks. These short
fixtures do not certify sustained heavy-effects performance. The performance
sampler still reported startup/timeline drops after constructing the test copy;
those warnings remain visible rather than being treated as a pass.

Physical projector/processor routing, live camera capture and audible stereo
playback were deliberately not armed. Launch buttons for those paths receive
wiring checks only. Rehearse the actual show, displays, camera, audio and media
before public use. Detailed local reports/recordings remain ignored under
`build/`; only sanitized summaries and clean distributable artifacts are synced.

## Pre-show readiness and render warm-up — 2026-10-28

Show Control now includes a non-arming **Pre-Show Check**, a current-workload
performance sample, distinct-render-frame cue warm-up, and a configurable
0–10-second render warm-up before real-time wall recording (default 2 seconds).
It never treats missing telemetry as a pass. GPU identity describes the selected
TouchDesigner renderer, not whether every external worker is using CUDA.

The portable suite contains **752 tests** with four expected Windows symlink
skips. The 17 new regressions cover missing/invalid/slow performance samples,
memory and dropped-frame warnings, callback dispatch, sample-job isolation,
distinct-frame cue warm-up, preload timeout preserving the on-air cue, and wall
recording warm-up timing and bounds. The existing layout test covers all 14
Show Control sections.

The native Show Control regression passed **50 groups**, including dispatch for
all **58 pulses and 20 panel buttons** and rendered checks for 63 mapping/grade
controls. The real-frame ink playback suite passed **15 checks** across all three
ink modules: recall, GO, timed pixels, unchanged on-air pixels during preload,
and continuous crossfade endpoints. No physical outputs or audio were armed.

The initial TouchDesigner 2025.32820 / RTX 3080 Ti Laptop GPU test exercised
the pre-show button and performance sample, section navigation, cue warm-up at
1/3/12 frames, wall recording with warm-up at 0 and 2 seconds, cancellation
during warm-up, and preservation of the original cue document. Both 3-second
UHD H.264 encoder-test clips decoded as 90 frames at 3840×2160 / 30 fps.
The zero-second case reported **1 dropped frame**; the 2-second case reported
**0 dropped frames**. These are short calibration tests, not a sustained show
or heavy-effects performance guarantee. They did not verify calibration pixels;
the isolated, pixel-verified rerun above supersedes that part of the evidence.
Warm-up prepares the render pipeline;
the encoder still opens when recording starts and may stall on its first frame.

Use **Sample Current Performance** while representative cues are running, then
rehearse actual projector/processor routing, audio, codec, disk and duration.
The earlier recording warning below is retained as historical evidence.
Reports and test recordings stay local under `build/show-readiness/`.
An offline expansion of the saved release TOE confirmed the exact new runtime
sources, dispatch guard, page and warm-up value, clean test cue and no personal
look/media. All **1,835 saved text DATs** passed the credential scan. A subsequent
fresh-open runtime check passed **62 startup/persistence checks** with no native
errors or warnings; all **4,307 runtime text DATs** passed the credential scan.
The render GPU remained the RTX 3080 Ti Laptop GPU, with audience windows closed
and audio disarmed.

The personal main TOE was separately upgraded through a backed-up candidate.
Its fresh-open validation passed **29 checks**, preserving both cues, **19 effect
components** (values, modes, expressions and bindings) and **199 existing Show
Control values**. All 24 embedded puppet runtimes received the existing preview
clock correction; this removed three cook-dependency warnings reproduced in the
untouched original. The upgraded candidate reopened without native errors or
warnings before promotion to `TD_ImageFX_Library.toe`. The original file and
private preservation reports remain local in `build/show-readiness/` and are not
part of the clean publication artifact.

## Local-first verification policy — 2026-10-28

The local safety gate passed **735 portable tests** on Python 3.11.9 / NumPy
1.24.4 (four expected Windows symlink-permission skips). Its 18 new regressions
cover failure propagation, missing prerequisites, safe subprocess arguments,
single-pass verification and the low-usage workflow policy. Immutable package
history, tracked/staged credential scans, generated artifacts and documentation
checks passed; all three workflow files passed actionlint 1.7.12.

Routine repository verification now has one Ubuntu job on PR updates and `main`
pushes, with no duplicate feature-branch push run. The full six-way OS/Python
matrix is manual. Security settings and branch protection are unchanged.
That initial local-first commit changed no TOE, TOX, shader, runtime, cue or media
files. Later readiness/control commits include rebuilt clean native artifacts
and the validation described above. Neither stage certifies live-camera,
physical projector or sustained recording performance.

## Motion, controls and clean publication recheck — 2026-10-28

The publication copy was rebuilt in TouchDesigner **2025.32820** on the
**RTX 3080 Ti Laptop GPU**, separately from the operator's personal TOE and
show files. All 96 current catalog effects compiled with zero builder, shader
or preview errors. The distribution has clean defaults: no personal cues,
artwork, prepared motion, camera session, model weights or credentials.

- **717 portable tests** passed with NumPy 1.24.4 and again with NumPy 2.4.6;
  four Windows symlink-permission skips are expected. Both GitHub verification
  workflows now install the motion-math test dependency explicitly.
  Two media-path assertions now compare canonical paths, covering macOS `/var`
  aliases and Windows 8.3 temporary-directory names found by cross-platform CI.
- **121 optional puppet tests** passed in the configured worker environment.
- **29 blocking native groups / 6,609 checks** cover the complete control
  inventory, slider ranges/endpoints, menus, values, bindings and callbacks.
  The new motion audit covers all three Dance Forces panels and Dance Puppet.
  Camera/analysis/viewer launch pulses receive wiring checks, not unattended
  activation. Other rendered behavior has separate frame-based tests.
- **17 real-frame groups / 590 checks** cover playback, media, transitions,
  Continue/Follow, running-look edits, events, mapping and feedback. The runner
  now also refuses open physical output windows or active export jobs.
- **12 additional native groups / 922 checks** cover local force advection,
  response delay, pattern-relative coordinates, smooth asynchronous activation,
  cue inheritance, puppet fade/alpha/trails, independent A/B editing, navigation
  and export. **83 older-show checks** exercise recall, live edit, cancel,
  update and save/reload with prepared local fixtures.
- **36 panoramic preview checks** preserve the running deck, values, playhead
  and 5760×1080 pixels across window sizes. A visible maximize/restore/focus
  smoke test retained the letterboxed image and accessible pinned preview.
- **24 finished export clips** passed independent ffprobe/ffmpeg decoding:
  HD, UHD, custom, full panorama and the packed wall with confidence monitor.
  Dimensions, codecs, frame counts and silent streams were checked; wall
  quadrant colors and confidence content were also verified.
- A fresh 12-frame CUDA check recorded actual CUDA execution in both pose
  sessions (3,756 detector and 6,660 pose kernels). OpenGL rendering identified
  the RTX 3080 Ti. Small CPU support operations remain; this does not mean every
  operation is CUDA or certify live camera/show frame rate.

The audit corrected stale validator assumptions about workflow stage counts,
fade-in, and activation timing, and repaired the export validator's missing
driver reference. Reopening also exposed a puppet Time cook-dependency loop:
the preview clock now uses per-DAT ephemeral state rather than writing dependent
operator storage from its own time expression. Two portable regressions cover
storage-free evaluation and isolated clocks for copied modules.
The final saved TOE passed **58 startup/persistence checks** after reopening,
with no native errors or warnings. All **4,306 embedded text DATs** passed the
credential scan. The operator's original TOE and personal shows were preserved.
Saved motion roots, independent rack paths and Show Control
paths now follow the opened project folder instead of the developer checkout.
The rejected dance-driven-backdrop prototype stays local and unpublished.

**Performance warning:** the 30-fps H.264 real-time UHD wall test reported
**10 startup dropped frames**. The 25-fps MJPEG and 24-fps H.264 early-stop
fixtures reported zero. Controls/file correctness passed; seamless real-time
wall recording is not certified. Rehearse the actual duration, codec and disk.
Physical cameras, projector/processor cabling/EDID, stereo listening and a
sustained three-projector show load were not tested. No audience output or
audible audio was enabled. Automated sweeps do not manually drag every GUI
slider or exhaust every possible parameter combination.

Detailed reports remain local under `build/envoy-validation/`,
`build/dance-forces/`, `build/dance-puppet/` and `build/audit/`. The public
`docs/native-validation.json` records source-bound native artifact hashes.

## Panoramic offline export — 2026-10-27

The new **Export Video → Resolution → Panoramic / Full 3-Projector Canvas**
preset renders the selected saved cue or current draft at the full three-panel
size, normally 5760×1080. The existing packed 3840×2160 wall recording stays
separate. No projector output was opened and no audio was enabled.

- **614 portable tests**, with four expected Windows symlink-permission skips,
  passed in a publication-only source snapshot. Rejected local prototypes remain
  untouched and excluded.
- **29 native review/export checks** passed, producing 12 short files: existing
  HD/4K/custom cue/draft/video and three animated ink particle/feedback fixtures,
  plus panoramic saved-cue, draft, image and Final Crop cases.
- Independent ffprobe/ffmpeg decoding verified dimensions, codec, FPS, frame
  counts and silent streams for all 12 files. The panoramic image's first frame
  contains a proportionally fitted circle, not an initial blank frame. A loading
  race found during testing was fixed by waiting for fully decoded media rather
  than merely an open file.
- Export works while the live layout stays Identical; the render copy has its
  own wide resolution and media fit. Saved cues, the main look and unsaved cue
  editor fields remain unchanged. Cancellation removes only the job's copy.
- Unit checks cover overlap/even-pixel sizing, 4K-per-panel geometry, unsupported
  H.264 dimensions, Auto/explicit fit, reader readiness and unchanged wall sizing.

These short functional exports do not certify long-duration disk throughput,
11520×2160 performance, or physical projector/video-wall hardware.

## Panoramic output publication recheck — 2026-10-25

A fresh load of the saved canonical TOE passed **28 blocking groups / 5,758
checks**, **17 real-frame groups / 590 checks**, and **29 startup/persistence
checks**. The publishable source snapshot passed **600 portable tests**, with
four expected Windows symlink-permission skips. All 4,907 embedded text DATs
passed the credential scan; the private show JSON and saved TOE remained
byte-for-byte unchanged during the audit. The rejected dance prototypes and
their local tests remain outside the publication snapshot.

The blocking runner now rejects active/paused cues, unfinished drafts, armed
audio, released blackouts, open physical windows, active exports and overlapping
deferred audits before it touches parameters. Seven new portable regressions
cover these guards, including leaving the operator's windows and export jobs
alone. See the README's complete live validation instructions.

The separate Look Editor navigation pass completed **64 checks**. Cue/draft
export completed **20 checks**, and independent decoding verified eight clips,
including animated particle/feedback looks in all three ink modules. The wall
recorder completed **seven checks**; three finished UHD clips decoded with the
correct projector quadrants and confidence preview/diagnostics. The short
30-fps H.264 wall recording again reported **10 startup dropped frames**, while
25-fps MJPEG and the 24-fps H.264 early-stop fixture reported none. File/control
checks pass, but this real-time recording performance warning remains open.

Parameter sweeps verify ranges, endpoints, bindings, callbacks and pixel response;
they do not manually drag every GUI slider or cover every combination. Real
projectors, processor cabling/EDID, stereo listening and sustained three-channel
performance still require an on-site rehearsal. No audience output was opened
and no audible audio was enabled during this recheck.

## Automatic canvas sizing and distortion-free crop — 2026-10-25

The main workflow now follows Show Control's canvas dimensions and media fit
by default, retaining its manual HD / 4K / Custom size and Image Fit settings
for the Follow Show Canvas off state. Cue source media now passes through an
aspect-preserving fit shader before effects; Auto fills panoramic canvases by
center-cropping and letterboxes other layouts. Explicit Fill, Fit and Stretch
remain available, and Canvas Media Fit is persisted with show mapping.

- **28 blocking groups / 5,758 checks** passed, including actual main-source and
  output dimensions at 5760x1080, normal-layout return to 1920x1080, retained
  manual sizing, enabled/disabled controls, and cue-deck resize identity.
- Native circle pixels verify proportional Fill / Crop (equal width and height),
  letterbox fitting, intentional Stretch, alpha preservation, filled image
  borders, actual cue source-switch output, and fit changes after resizing.
- **17 real-frame groups / 590 checks** passed, including real image/video
  playback, cue transitions, running-look editing, export, and both directions
  of the Canvas Media Fit binding with one safe window-close event per change.
- The publication-only snapshot passed **593 portable tests**, with four
  expected Windows symlink-permission skips; rejected prototypes were excluded.
- The saved main TOE reopened successfully: **29 persistence/safety checks**
  passed, including fresh 5760x1080/1920x1080 rendering and default Auto fitting.
  No native errors or warnings were present; all **4,907 embedded text DATs**
  passed credential scanning. Personal show JSON remained byte-for-byte unchanged.
- Small-fixture shader sweeps explicitly opt out of automatic canvas sizing
  during validation and restore that setting afterward. Live diagnostics now
  compare against the effective automatic size, not the inactive manual preset.
- Physical projector/processor output and sustained show-load performance are
  not certified by these checks. Projector feeds remain 1920x1080 by default;
  the wall-controller packing remains 3840x2160 with confidence in Q4.

Focused regressions: `tests/test_show_panorama.py`, `validate_output_resolution.py`,
and `validate_output_mode.py`. Runtime/TOE changes are additive; existing effect
and core TOX files are unchanged.

## Shared panoramic cue canvas — 2026-10-25

Show Control now exposes Canvas Layout, Shared Canvas Cue Track, per-panel
render dimensions and overlap beside Output Mode. The same single wide cue
works with direct displays or the existing 4K 2x2 wall; independent routing
and legacy defaults remain intact. Only the main TOE needs this additive
Show Control update; effect/core TOXs and shaders are unchanged.

- **28 blocking groups / 5,724 checks** and **17 real-frame groups / 586 checks**
  passed in TouchDesigner 2025.32820 on the RTX 3080 Ti Laptop GPU.
- Native pixel checks confirmed a **5760x1080** three-color panorama is split
  into the correct **1920x1080** left, center and right feeds. Direct and wall
  routes retain those same pixels; the **3840x2160** wall places them in Q1-Q3
  and preserves the confidence monitor in Q4, without a second crop.
- Shared cue tracks 1-3, overlap, independent/identical modes, and Save/Load
  Show all passed. Changing canvas dimensions resizes preloaded, playing and
  recalled decks without replacing their identities, restarting cue time or
  changing saved look values. Real callback tests verify both directions of
  the Routing/Output Mode links and safe output-window closure.
- The publication-only snapshot passed **588 portable tests**, with four
  expected Windows symlink skips. The rejected dance prototypes remain
  excluded. The native Canvas Layout dropdown and 5760x1080 summary were
  also inspected directly in Show Control.
- Physical projector/processor output and sustained panoramic show-load
  performance were not tested. Configure the canvas before playback; resizing
  still incurs GPU allocation and can clear feedback history. Audience windows
  and audible audio remained disarmed, and the personal show JSON was preserved.
- A fresh canonical-file reopen passed **23 persistence/safety checks** with
  no native errors or warnings. All **4,906 embedded text DATs** passed credential
  scanning. Repository verification passed for the updated native artifact,
  source fingerprints, tests, gallery, feeds and benchmark records.

Regression: `tests/test_show_panorama.py`, `tests/test_show_output_mode.py` and
`touchdesigner/scripts/validate_output_mode.py`. The focused native report is
`build/envoy-validation/output-mode.json`; full reports are `live-suite.json`
and `deferred-controls.json` in the same ignored directory.

## Running-cue look editing — 2026-10-25

The main TOE has an in-place Show Control update for **Edit Running Cue**.
Effect shaders and the existing core/package TOXs are unchanged by this update.
The full control and export suites were rerun against the saved canonical TOE
after the update; the results below include that release recheck.

- **63 focused native checks** verify live projector pixel changes, Cancel,
  Update without a frame/clock reset, independent track isolation, mapping and
  blackout safety, pause/resume, rack/workflow/branch restoration, and preservation
  of all three ink modules' saved starting phases. Video and embedded-audio
  reader identities/play states remain intact. Continue/Follow and Stop All retain
  an unfinished draft without changing the next cue. Save Show works after commit
  while playback continues. The new panel button is checked for size and preview
  non-overlap; its label is also visually verified in the saved TOE.
- The full audit passed **28 blocking groups / 5,682 checks** and **17 real-frame
  groups / 580 checks**. The latter includes the 63 new checks. The visible
  **Edit Running Cue** pulse and panel-button route are included in the exhaustive
  dispatcher check.
- **20 cue/draft export checks** and **seven wall-recorder checks** passed again.
  Independent decoding confirmed all eight cue movies and three completed UHD
  wall movies, including projector quadrant order and confidence-monitor pixels.
  The H.264 30-fps wall test again reported **10 startup frame drops**; MJPEG
  25-fps and H.264 24-fps early Stop reported none. This remains a recording
  performance limitation, not a failed control or file-format check.
- The publication-only source snapshot passed **579 portable tests** with four
  expected Windows symlink skips. The local, rejected dance prototypes were not
  included. The tracked-file credential scan passed.
  GitHub's macOS run exposed a temporary-directory alias in the new Save Show
  fixture; resolving that test directory keeps the production symlink guard
  intact. A documentation assertion also keeps the README's real-frame group
  count synchronized with the audit dispatcher.
- The previous main TOE was backed up locally before patching; the personal
  show JSON was unchanged. Audience windows and physical audio remained disarmed.
  These checks do not certify venue hardware or sustained show-load performance.
- A fresh canonical-file reopen passed **14 persistence/safety checks** with
  no native errors or warnings. All **4,906 embedded text DATs** passed the
  credential scan; the new button and scoped editor code match the saved source.

Regression: `tests/test_show_running_look.py`, `tests/test_look_editor_controls.py`,
and `touchdesigner/scripts/validate_running_look.py`. The last runs automatically
in `validate_deferred_controls.py`; its local report is
`build/envoy-validation/running-look.json`.

## Release recheck — 2026-10-25

The final Particle Field, point-motion and optional Feedback build was checked
again in TouchDesigner 2025.32820 on the RTX 3080 Ti Laptop GPU. Both optional
effects remain off by default; existing flow composition and movement are
unchanged when Particle Field is off.

- **28 blocking groups / 5,682 checks** and **16 real-frame groups / 517 checks
  passed**. These cover parameter bindings, slider endpoints, numeric values,
  menus, colors, pulse buttons, cue playback, mapping and resets. The three flow
  modules include **477 writable values / 2,948 checks**, **93 motion/feedback
  checks**, and **126 cue animation checks** at 1080p.
- The export validator now records all three flow modules with custom Particle
  Field, point motion and Feedback settings. It checks every custom value in the
  isolated export deck and observes active, non-clearing GPU history after
  initialization. Portable regressions protect these fixtures and their template.
- **20 cue/draft export checks** passed. All **eight exported movies** decoded
  with the expected codec, dimensions, frame rate and frame count, no audio
  stream, and non-black output. The three new flow movies also had measurably
  different first/last frames. Cancel and preservation of the main look/show
  passed.
- **Seven wall-recorder checks** passed, including early Stop and Cancel. All
  three completed UHD recordings decoded at **3840 × 2160** with correct
  top-left / top-right / bottom-left projector ordering and a bottom-right
  confidence preview plus diagnostics.
- The legacy-renderer comparison passed **159 checks**, with all **27 off-mode
  comparisons pixel-exact**. The final canonical reopen passed **660 checks**
  across **81 flow instances** and **324 local shader diagnostic targets**, with
  zero native errors/warnings. All **4,903 embedded text DATs** passed credential
  scanning. The personal show JSON and final TOE hashes were unchanged by this
  recheck.
- The publication-only snapshot passed **561 portable tests** (four expected
  Windows symlink skips), credential scanning, native-artifact provenance,
  all 96 preview baselines, feeds and benchmark checks. The main TOE and nineteen
  core TOXs are included; personal media, show files, credentials and unrelated
  rejected dance prototypes are excluded. Existing package versions are unchanged.

**Recording limitation:** the short UHD H.264 30-fps test reported **10 dropped
frames at startup**. The MJPEG 25-fps and later H.264 early-stop fixtures reported
zero. Successful control/export checks do not certify seamless real-time
recording under show load. Physical projector/processor connections and audible
stereo output were not tested; output windows and audio stayed disarmed. Rehearse
the actual media, feedback and recording workload before a performance.

Fresh local reports are in `build/envoy-validation/`, with the saved-file audit
in `build/flow-motion-feedback/reopen.json` and original-renderer comparison in
`build/optional-particle-review/comparison.json`. These machine-local fixtures
and reports remain ignored. The main canonical TOE is reopened with clean,
stopped/disarmed defaults; the personal show remains backed up and unchanged.

## Point movement and optional flow feedback — 2026-10-25

Ink Dream Flow, Ink Brush Flow and Ink Radial Flow now have a continuous
**Point Motion Speed / Reverse** control and an independent, default-off
**Feedback** page. Point centers move along bounded flow-aligned paths; changing
speed preserves the current point phase. Zero holds positions, negative reverses,
and the default remains zero for compatibility. Particle Field itself stays off.
The original flow composition is not warped by the added motion.

Feedback provides trail mix, retention, zoom, rotation, X/Y offset and a reset
pulse. It works with the original renderer or Particle Field. History is cleared
on cue load, re-enable, large seeks and resolution changes; pauses hold it.
Settings and point phase are captured in looks, but GPU history is not saved.
Recalled looks/exports therefore build fresh trails from their saved phase.

- The main TOE and nineteen core TOXs rebuilt without builder, shader or
  preview errors in TouchDesigner 2025.32820. Removing a stateful phase readout
  resolved a dependency warning in copied cue/composition modules; phase remains
  internal and is still saved with cues.
- All **28 blocking groups / 5,682 checks passed**, including sweeps of
  **149 Dream / 159 Brush / 169 Radial writable values** (2,948 checks).
- All **16 real-frame groups / 517 checks passed**, including cue/media,
  mapping, Continue/Follow, live look editing and the new history fixture.
- The dedicated real-frame motion/feedback fixture passed **93 checks** across
  all three modules. It isolates alpha support to prove that point positions
  move, not only colors. It tests no-jump rate edits, hold/reverse, continuity,
  real history trails, pause, reset pulse, every history transform, zero-mix
  bypass, zero retention, clean re-enable/seek, transparency and module bypass.
- Cue animation tests passed **126 checks** at 1080p, including the saved point
  phase and feedback settings through Update Cue Look, Recall, GO and isolated
  export setup, alongside existing preview stability and composition checks.
- The original-renderer comparison was repeated after the point-motion change:
  **159 checks passed**, with all **27 off-mode comparisons pixel-exact**.
- Reopen testing also found legacy absolute targets in rack shader Info DATs.
  Builder, rack and library loaders now repair those diagnostic references in
  loaded copies, leaving immutable package files unchanged. A portable
  regression test covers each loader.
- The final canonical reopen passed **660 checks**: current code and safe
  defaults in all **81 flow instances**, **324 valid local diagnostic targets**,
  no native errors/warnings, disarmed outputs and an unchanged personal show.
  Credential scanning also passed for **4,903 embedded text DATs**.
- The tracked-file verification snapshot passed **558 portable tests** (four
  expected Windows symlink skips), credential scanning, native provenance,
  96 gallery baselines, feeds and benchmark checks. Unrelated local dance
  prototypes were preserved and excluded from the snapshot.

The prior local TOE, core TOXs and personal show are backed up under
`build/backups/pre-flow-motion-feedback-20261025/`. The personal show JSON was
preserved, and rejected dance prototypes remain separate and untouched. Reports
are in the ignored `build/envoy-validation/` and `build/flow-motion-feedback/`
folders. Physical outputs/audio stayed disarmed. This is local functional
validation, not GitHub publication or sustained multi-projector performance
certification; feedback adds GPU history work when enabled.

## Optional Particle Field with original flow restored — 2026-10-25

This correction supersedes the earlier always-particle revision. Ink Dream Flow,
Ink Brush Flow and Ink Radial Flow retain their original renderer, defaults,
parameter labels and ranges. **Particle Field Enabled** is a separate, default-off
switch; it converts the finished foreground without changing the flow generator,
composition coordinates, seed or animation clock. The paper/input background is
retained. New cell-fill and point-size controls do not reuse the original pigment
density/size controls.

- A side-by-side native comparison against the pre-particle source passed
  **159 checks**. All **27 off-mode frame comparisons were pixel-exact** across
  three modules, three configurations and three times. Old parameter definitions
  and defaults matched exactly; new controls were inert while conversion was off.
- On-mode checks verified unchanged foreground support and palette, a stable
  point mask across time, zero-density behavior, exact toggle round-trips and no
  animation-clock reset. 1080p original/converted previews were inspected.
- A clean TouchDesigner 2025.32820 build completed with no builder, shader or
  preview errors. The canonical TOE and nineteen core TOXs were rebuilt.
- Native pixel sweeps passed **141 Dream / 151 Brush / 161 Radial writable
  values**, totaling **2,876 checks**. Coverage includes exact bypass, new controls,
  alpha/gaps, glitter/shimmer, no-jump speed changes with conversion on and off,
  deterministic seeking, radial fallback, and 1080p/4K output dimensions.
- The complete blocking workflow suite passed **28 groups / 5,610 checks**,
  including the module sweeps above and existing control/binding/output checks.
- The real-frame suite passed **15 groups / 397 checks**, including all six
  optional field controls in Capture/Update, Recall and GO, legacy-cue default-off
  behavior, preview/phase stability, Continue/Follow and blackout playback.
- Reopening the canonical TOE passed **334 startup checks**: current shaders and
  default-off field controls in all **81 module instances**, empty native
  diagnostics, safe/disarmed outputs and the personal show hash unchanged.
  Credential scanning passed for all **4,093 embedded text DATs**.
- The tracked-file snapshot passed **551 portable tests** (four expected Windows
  symlink skips), credential scanning, native provenance, 96 gallery baselines,
  feeds and benchmarks. Unrelated local dance prototypes were preserved and
  excluded from this snapshot.

The prior local TOE, core TOXs and personal show are backed up under
`build/backups/pre-optional-particle-field-20261025-160320/`; the original ink-style
backup remains under `build/backups/pre-particle-flow-20261025/`. The personal show
JSON is not modified. Comparison reports and previews are in the ignored
`build/optional-particle-review/` folder. This is local validation, not a GitHub
publication or sustained multi-projector performance certification. Physical
outputs/audio remain disarmed during tests.

## Full control revalidation and publication — 2026-10-23

The clean main TOE containing the Continue/Follow fix and per-cue Notes column
was tested again in TouchDesigner 2025.32820 on the RTX 3080 Ti Laptop GPU.

- **28 blocking groups / 5,412 checks passed**, including all module bindings,
  parameter endpoints, effect selection, pulse routes, mapping and reset controls.
- **15 real-frame groups / 385 checks passed**, including 52 live-look/notes
  checks and 35 Continue/Follow checks. Custom ink cue playback, crossfades,
  animation speed, notes pagination and selection all passed.
- **14 cue/draft export checks** and **7 wall-recorder checks** passed. Five
  cue/draft/movie exports and three completed UHD wall recordings were decoded
  independently; dimensions, frame counts, non-black images, projector quadrant
  order and confidence diagnostics were correct. Stop and Cancel also passed.
- **548 portable publication tests passed**, with four expected Windows
  symlink-permission skips. Credentials, native-artifact provenance, all 96
  preview baselines and benchmark checks passed; 124 package versions remain
  immutable. Rejected dance prototypes stay local and are not part of this release.
- Reopening the canonical saved TOE passed **20 startup checks** with zero
  native diagnostics. All **4,093 embedded text DATs** passed credential scanning;
  the show remained stopped, blackouts on, audio/windows off and personal show
  data unchanged. The final Show Control panel was visually inspected.

Performance caveat: the short UHD H.264 30-fps recording still reported **10
dropped frames**, while the 25-fps MJPEG and early-stop fixtures reported zero.
The largest preparation step in this rerun was **7.476 ms** (an earlier run
reached 65.4 ms). These are functional checks, not a sustained show-performance
certification. Physical projector/processor connections and audible stereo output
were not tested; rehearse the actual media, output and recording workload.

The saved personal show and canonical TOE were not modified by the tests.
A local safety backup is under `build/backups/pre-full-validation-20261023-1935/`.
Fresh native reports are in `build/envoy-validation/live-suite.json`,
`deferred-controls.json`, `show-review-export.json`, `cue-export-media.json`,
`wall-export.json`, `wall-export-media.json` and `cue-notes-reopen.json`.
Test fixtures and private show
files remain outside the publication set.

## Per-cue Notes column — 2026-10-23

Show Control now displays saved notes beside each visible cue. The two columns
stay aligned through 12-row pagination and reordering; clicking a note selects
that cue. Long/multiline notes use a single-line preview without modifying the
full saved text. Save Cue Notes refreshes the row without resetting playback or
committing the live-look draft. The show JSON format is unchanged.

- Eight new portable regressions cover row identity, empty/long/Unicode notes,
  pagination, reordering, compact cue labels and refresh behavior. All **548
  public-source tests passed**, with four expected Windows symlink skips.
- The rebuilt main TOE was inspected with the computer-use skill in
  TouchDesigner 2025.32820. Both columns fit inside the existing cue-list area,
  with the right-hand parameter inspector and Look Editor toolbar unobstructed.
- **75 blocking checks** passed across Show Control and navigation; **15
  real-frame groups / 385 checks** passed, including **52 live-look/notes checks**
  and the retained **35 Continue/Follow checks**. Audio stayed disarmed and
  physical projection windows stayed closed.
- Repository verification, credential scanning, native-artifact provenance,
  all 96 preview baselines and benchmark checks passed. All 124 immutable
  package versions were preserved. Existing local changes and rejected dance
  prototypes were retained and excluded from the publication set.
- Reopening the canonical saved TOE passed **20 startup checks**, including
  all twelve notes cells/callbacks, the embedded Continue/Follow fix, safe
  output defaults, unchanged personal show data, zero native diagnostics and
  a credential scan of all 4,093 embedded text DATs.

The canonical main TOE was rebuilt with clean defaults. The saved personal show
JSON is byte-for-byte unchanged and backed up under
`build/backups/pre-cue-notes-20261023-183940/`. Native reports are in
`build/envoy-validation/cue-notes-blocking.json`, `show-live-look.json`, and
`deferred-controls.json`; saved-file checks are in `cue-notes-reopen.json`.

## Continue / Follow queue regression — 2026-10-23

Automatic cue requests now distinguish temporary track/deck reservations from
real errors. A cue targeting a busy crossfade remains WAIT, then prepares and
plays when the track is free. Media errors still show ERROR. Manual GO and
Preload retain their explicit busy-track warning.

- **20 new portable regressions** cover Continue chains, Follow timing,
  timestamps, independent tracks, reserved standby decks, long fades, decoding
  timeouts, Pause/Resume, Stop Selected, Stop All and Go Back cancellation.
- **35 real-frame TouchDesigner checks passed** in an isolated test show.
  Red/green/blue pixel checks verify the active image survives resource waiting,
  crossfades contain both images, and the final cue renders its own source.
  Follow respects Duration, Post-Wait and the next cue's Pre-Wait, pauses its
  clock, cancels when its parent is stopped, and recovers from a busy track.
- The public-source verification snapshot passed **540 portable tests**, with
  four expected Windows symlink-permission skips, plus credential, native
  provenance, package, gallery and benchmark checks. Local rejected dance
  prototypes were excluded without modifying or deleting them.
- The main TOE and nineteen core TOXs were rebuilt with TouchDesigner
  2025.32820; all 96 current effects built without shader/preview/builder errors.
  The 124 published package versions were preserved.
- The complete regression rerun passed **28 blocking groups / 5,412 checks**
  and **15 real-frame groups / 376 checks**, including the 35 new queue checks.
- Reopening the saved canonical TOE passed **17 startup checks**, including the
  embedded queue fix, safe output defaults, unchanged personal show, zero native
  diagnostics and a credential scan of all 4,055 embedded text DATs. The report
  is `build/envoy-validation/continue-reopen.json`.

The computer-use skill was used to build and test inside TouchDesigner. The
personal show JSON remains byte-for-byte unchanged, with a local backup under
`build/backups/pre-continue-fix-20261023/`. Native regression details are in
`build/envoy-validation/show-continue.json`. Audio stayed disarmed and physical
output windows stayed closed. These checks do not certify sustained projector
or processor performance or resolve the recording limits documented below.

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

The October 27 local puppet/layer extension has an additional focused validator,
`validate_puppet_layers.py`: 47 checks cover opening-pose preview, pause/resume,
solo-character cue synchronization, independent A/B effects, saved cue recall,
and fixed 1080p foreground placement within a 5760×1080 panorama. A circle fixture
checks both aspect ratio and pixel size at left/center/right. The updated Layer
Composite regression passes 181 checks. These local results do not replace a
clean release build or rehearsal on the physical projection system.

The focused `validate_module_bindings.py` regression first audits the installed
two-way links without repairing them, then uses disposable cue copies to check
every module and rack slot in both directions. It covers independent states,
capture/recall, A/B branches, reorder, preset/slot reload, and the rack master
bypass's rendered pixels. The October 7, 2026 in-place main-TOE upgrade passed
830 focused checks and preserved the current cue document and designer look.
This focused result is not a new complete native-build certification.

`validate_layer_editing_feedback.py` checks both independent editor scopes,
all module/slot targets, nonrecursive navigation, alpha-preserving puppet
trails, half-life/strength independence, pause, clear, bypass and the Show
Control geometry/section selector. The October 27 local follow-up passed its
155 native checks. `validate_layer_composite.py` now distinguishes editor-only
menus from visual controls and passes 187 checks. A separate pure-Python layout
test rejects intersecting control rectangles and misaligned cue/notes rows.
Projector review reinstallation also retains the new one-section inspector.

The subsequent preview/navigation fix adds `validate_preview_navigation.py`:
61 native checks exercise the real Section value-change callback across all 13
pages, explicit inspector rebinding, dedicated fitted-preview wiring, unchanged
render pixels/resolution, draft/document preservation and audience-window safety.
The visible dropdown was also tested in Show Control; scope-value checks alone
did not detect the original cached-page bug. The preview was checked at normal,
square and maximized sizes. The additional `validate_preview_panorama.py`
regression passes 36 checks with a running 5760×1080 cue, including live editing,
pause/resume, preserved pixels and unchanged cue/deck state during resize. The
Look Editor window stays above TouchDesigner after resize and focus changes;
Projector Review is unchanged. The 662-test portable suite passes (four expected
Windows symlink-permission skips). These are local UI regression tests,
not a new clean release build or physical-projector certification.

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
