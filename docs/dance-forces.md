# Dance Forces for the three flow modules

`ink_dream_flow`, `ink_brush_flow` and `ink_radial_flow` now have the same optional
Dance Forces treatment. It is **off by default** and its bypass is the original
flow output. Existing particles, glitter, patterns, composition, timing and
feedback controls stay available.

This is an artistic movement driver, not a fluid solver or a dancer silhouette.
Two dancers' body/hand/foot velocities create broad directional pushes and curls
in the existing pattern. The force is integrated into foreground material motion,
not applied as a warp to the finished image. The input picture, paper texture,
composition envelope and radial center stay fixed. Motion release damps the
extra velocity when dancers stop; it does not snap the pattern back to its old
position. The effect works before the existing optional feedback stage.

## Try a prepared prerecorded clip

The clean GitHub TOE contains no private dance video, motion cache or configured
camera session. The following local example applies only where the operator has
already prepared `Main Edit.mp4`. For a fresh checkout, first follow **Another
prerecorded video** below and configure the optional worker environment.

1. Open the canonical `TD_ImageFX_Library.toe`, and enable one of the three flow
   modules in the workflow (or in a cue's Look Editor).
2. In that module, open **Dance Source**. **Use Latest Completed Analysis** selects
   the local analysis of `Main Edit.mp4` (206.3 seconds).
3. Open **Dance Forces**, enable **Dance Forces Enabled**, and leave Animate Preview
   running. Start with Strength 1, Radius 0.24, Push 1, Swirl 0.6, Speed Response 1.
4. **Fade In** defaults to 1.5 seconds; 0 is immediate. It ramps the force, not the
   whole image's opacity. Turning the treatment on or starting its cue restarts
   the fade. **Restart Dance Forces Preview** restarts the motion and fade without
   restarting the underlying procedural pattern.
   Recorded cache loading/filtering runs in a bounded background worker shared
   by the flow modules and playback decks. While it prepares, the original
   pattern continues; the fade begins only when valid motion is ready. A one-frame
   zero-field guard prevents stale GPU history on activation/re-trigger, even
   with Fade In set to 0. No model inference or camera starts automatically.
   Editing movement-filter controls keeps the last valid filtered force until
   the new settings are ready, without restarting the fade or pattern clock.
5. **Force Response Delay** defaults to **0.75 seconds**, adjustable from 0 to 5.
   It eases the local force's direction and speed continuously, including moving
   influence areas and strength edits. Higher values feel slower and gentler;
   try 1.5–2 seconds for a soft, gradual response. A steady force reaches about
   63% of its target after the selected time and 95% after three times that time.
   It is response lag, not a fixed wait or video time offset. Set 0 for the
   original immediate velocity response. Sustained force keeps the same eventual
   strength; lower **Movement Strength** or **Flow Speed Response** as well if it
   remains too intense. Fade In still controls the initial activation separately.

**Dance Influence** adjusts body/hands/feet, each dancer's contribution, placement,
scale and mirroring. **Dance Source** provides loop, in-point and playback speed.
Speed changes preserve the current motion phase. Existing Animation Speed remains
separate: it controls the pattern's own animation.

**Dance Influence → Force Coordinate Space → Follow Pattern Composition** is the
default. The force area and its movements follow **Composition → Pattern Scale**,
**Composition Center**, **Pattern Rotation**, and **Ribbon Stretch**. Smaller
patterns get proportionally smaller pushes instead of full-canvas movement.
The local force area has soft edges and zero influence outside its bounds; it
does not warp the input image or paper. Motion Area Scale/X/Y and Influence Radius
now adjust the force *within* that local space. This does not infer an ink/alpha
silhouette or change the existing Composition Spread control.

Choose **Full Canvas (Legacy)** to retain the former screen-space behavior.
Changing composition in Follow Pattern mode moves/resizes the existing local
force history with the pattern; it does not restart the dancers, fade or response
delay. The mode is stored in cue looks and independent A/B layers. Older cues
without this setting use the new Follow Pattern Composition default; choose
Full Canvas and Update Cue Look if their previous mapping is preferred.

**Directional Push** steers the foreground in the local direction of dancer
motion. **Flow Speed Response** (0–4) adds local animation speed according to
movement energy. Set it to 0 for direction-only control; set Push and Swirl to 0
for speed-only control. These do not change the saved Animation Speed, framing,
scale or source-image aspect ratio. Particle Field points move with this material
even when their own Field Speed is 0. Animated glitter follows the material;
static glitter stays anchored, with its visibility still following the flow mask.

The motion field is stateful: GO/restart, source changes, backward seeks, large
time jumps and resolution changes clear its history. A paused cue holds both
the pattern and field, including the delayed force. Changing Response Delay does
not restart the dance or clear material travel. Replaying from the same start
follows the recorded forces; scrubbing directly to a later time does not
reconstruct the intervening history.
Long-running local material travel is bounded for stability. This is a stylized
flow response, not a physical fluid simulation or exact deterministic offline bake.

## Another prerecorded video

Select **Dancers Video to Analyze**, then **Analyze Video on CUDA**. Preparation
runs in a separate local process; the previous valid cache remains selected until
success. **Cancel Analysis** stops only this preparation. The result is a small
local JSON motion cache. The original video is not an output layer and its audio
is not played. The other flow modules can use **Use Latest Completed Analysis**
to share it. A cue needs the cache during playback, not the original dance video.

Maximum supported analysis duration is one hour, sampled at up to 24 fps and no
faster than the source. Models must already be installed locally; the worker does
not download or execute anything described by a show file.

## Live camera

Select **Motion Source → Live Camera**, set **Camera Device Index** on Dance Camera,
then explicitly press **Start Live Camera on CUDA**. Enable Dance Forces on any
of the three modules to consume the same local camera session. **Stop Live Camera**
stops it. Do not use the same camera simultaneously in the puppet tracker.

Loading/recalling/running a cue never opens a camera or starts inference. The
worker stops when its owner disconnects; stale observations produce zero force.
The physical camera/device and venue lighting still need an actual rehearsal.

## Camera compensation and limits

Static background features estimate camera pan, roll and zoom. Detected people
are masked out of that estimate. Pose positions are transformed into a stationary
reference frame before velocity extraction. Invalid camera fits, missing joints
and large reacquisition jumps are gated to avoid accidental kicks.

This is approximate 2D stabilization, not a guarantee against parallax, cuts,
motion blur or prolonged occlusions. Prefer a locked wide camera with both dancers
and some textured, static background visible. Initial selection favors the two
largest central people; other prominently visible performers may be selected.
Confidence and small-motion thresholds reduce jitter but may suppress subtle motion.

## Cues, live editing and export

Capture/Update Cue Look stores all safe force values plus the passive local cache
path, including independent A/B branches. GO, Go Back and export start motion from
the saved in-point; they do not inherit the previous cue's force clock. Pausing a
recorded cue holds its forces and fade. Live editing changes the running treatment;
Update saves settings and Cancel restores them without rewinding ordinary value edits.
The analysis and camera-start buttons are never serialized into cues.
Response Delay is captured with each cue and independent A/B layer and can be
edited while a cue runs. Older looks without this control use the template's
0.75-second default; their existing controls and motion files are preserved.

### Older show files

Cues saved before Dance Forces existed have no prepared-motion file block. Their
recalled and playback decks now inherit the passive cache/video paths from the
matching main or independent A/B workflow. Previously recall cleared those paths,
so enabling Dance Forces in the editor produced no motion. No force toggle, cue
parameter or saved show is changed by this compatibility step. Enable Dance Forces
inside **Look Editor → Effect Module → Edit Controls**, not only in the main panel.
Use **Update Cue Look → Save Show** to pin those files and values into the cue.

Explicit saved paths, including intentionally blank paths, remain authoritative.
Missing caches in a cue that already saved Dance Forces controls still need to be
reselected under **Dance Source → Use Latest Completed Analysis** (or analyzed
explicitly). Loading/GO never runs analysis or starts a camera. The same passive
fallback supports adding the puppet to cues that predate the puppet module;
existing puppet cues keep their own prepared movies and character assets.

The puppet has a separate **Puppet → Fade In** control (1.5 s default, 0 for instant).
It fades the finished puppet layer, including trails, without retiming its movement.
When its background is opaque the whole puppet layer fades; transparent mode fades
the characters over the underlying effect. Preview restart and cue GO restart it;
pause/resume preserve it.

## GPU and local files

Analysis and live person/pose inference use the private CUDA runtime on GPU 0
(RTX 3080 Ti on this workstation). The material motion is a TouchDesigner GPU shader,
using the RTX via Vulkan, not CUDA. Background feature tracking, video decode in
the current OpenCV worker, JSON sampling and filtering remain CPU operations.
No heavy puppet rig or full-frame CPU renderer runs in this motion-force worker.
Its GPU state texture is 240×135 at HD/4K aspect and 720×135 for a 5760×1080
panorama. The original high-resolution foreground shader consumes that field.
The response delay adds one RGBA32Float velocity history at the same small
resolution and one GPU pass. It does not buffer full-resolution video frames or
run additional CUDA analysis.

Backend paths use the existing ignored `.imagefx/puppet-settings.json` keys
`python`, `models`, `live_gpu`. CUDA is required for analysis/live tracking; a
failed CUDA initialization is an error, not a silent CPU fallback. Prepared cache
playback does not need ONNX Runtime. Jobs, caches and source media remain local in
`.imagefx/dance-forces-jobs/`; keep that cache folder with your show backups.

Source: `touchdesigner/scripts/dance_forces*.py`,
`prototypes/dance_forces/service.py`. Additive installer:
`touchdesigner/scripts/install_dance_forces.py` (idle project only). Native pixel
and cue validators: `touchdesigner/scripts/validate_dance_forces.py` and
`touchdesigner/scripts/validate_dance_advection.py`, with
`touchdesigner/scripts/validate_dance_advection_cues.py` for cue integration.
Response lag is covered by `touchdesigner/scripts/validate_dance_response.py`
and `touchdesigner/scripts/validate_dance_response_cues.py`; pattern-local
mapping is covered by `touchdesigner/scripts/validate_dance_pattern_space.py`.
Activation, asynchronous preparation and re-triggering are covered by
`touchdesigner/scripts/validate_dance_activation.py`.
No audience
windows, cameras or audio are opened by validation.

## Local validation (2026-10-27)

The recorded `Main Edit.mp4` analysis used CUDA GPU 0 and produced 4,946 frames
(206.3 seconds); background-motion fits were accepted on about 99.9% of frames.
This is a fit-quality metric, not proof of perfect stabilization or tracking.
Before the material-motion revision, the native suite passed 240 off-air checks
on the RTX 3080 Ti, including all
new numeric ranges, individual force-control pixel changes, exact disabled/
zero-force bypass, cue file/value capture and restoration, and puppet RGBA
fades with feedback enabled. Puppet GO, Animate Preview, pause and resume
were checked separately. Portable checks passed 697 tests (four expected
Windows symlink skips) and 121 puppet tests.
That canonical main TOE was then reopened and passed 346 persistence/
runtime checks, with both existing cues and prior main-look values preserved.
The previous TOE is retained in `build/dance-forces/main-backup-20261027/`.

The subsequent material-motion revision passed 206 native GPU checks across
Dream, Brush and Radial Flow: original pixels with forces disabled; directional
motion and speed-only response; stationary source/paper; moving Particle Field
positions; pause/resume/restart; numeric ranges; real recorded motion; and
1920×1080, 3840×2160 and 5760×1080 output. Another 13 native cue checks verified
capture/recall, fresh history on retrigger, and live-edit cancellation without a
clock jump or history reset. The portable suite passed 699 tests (four skips).
Reports and the pre-migration TOE are local under
`build/dance-forces/advection-20261027/`. Existing cues and control values are
preserved; the new Flow Speed Response defaults to 1.
The saved canonical TOE was reopened and passed 369 persistence/runtime checks
across all 72 main, independent-branch and playback-deck flow instances.

The older-show compatibility follow-up reproduced empty force caches in all
three recalled flow modules, and empty puppet media in pre-puppet cues. The fix
passed 83 native checks through actual Load Show, Recall Look, Edit Running Cue,
Cancel, Update, Save/Load and Pause/Resume actions, including independent A/B
layers. Existing puppet cues retained their movie, transparency and feedback;
adding the puppet to a pre-feature running cue also animated correctly. No
source show, camera session, audience window or main-look values were changed
by the tests. Reports and the prior main TOE are in
`build/dance-forces/legacy-look-20261027/`. The portable suite passed 709 tests
(four expected skips), plus 121 puppet tests.
The saved canonical TOE then passed 17 reopen checks, including legacy recall,
unchanged cue data/main look, closed outputs and the installed extension.

The Force Response Delay addition passed 89 native GPU checks: bounded controls,
original zero-delay behavior, gradual buildup/reversal/release, paused history,
30/60-fps response agreement, seeks, real recorded motion, and HD/4K/panorama.
Another 54 native cue checks verified capture/recall, fresh history on retrigger,
live-edit cancellation without rewinding or clearing the response, old-look
defaults, and independent A/B values. The portable suite passed 714 tests (four
expected Windows symlink skips). The previous main TOE and reports are local in
`build/dance-forces/response-20261027/`; existing cue data and prior control values
were preserved across installation to all 72 flow instances.
The canonical main TOE was saved, reopened, and passed 441 persistence checks,
including both new shader histories, response values, cue data and media paths.

The pattern-local mapping addition passed 96 native GPU checks, including an
independent coordinate-transform oracle at HD and panoramic aspect ratios,
small/large scale, translated/rotated/stretched patterns, zero force outside the
soft local boundary, exact legacy full-canvas output, exact disabled output,
real recorded motion, and history/clock preservation during composition edits.
Another 72 native cue checks verified both coordinate modes, response delay,
old-look defaults, independent A/B capture/recall and live-edit cancellation.
The portable suite passed 718 tests (four expected Windows skips). Reports and
the previous main TOE are local under `build/dance-forces/pattern-space-20261027/`.
The canonical main TOE was saved, reopened, and passed 584 persistence checks
across all 72 flow instances, with existing cue data, look values and media preserved.

The smooth-activation follow-up (2026-10-28) passed 73 native GPU/runtime checks
and 72 cue checks. These cover a cold process cache, exact original pixels on
the activation frame, gradual fade after readiness, repeated off/on without old
history, pause/resume, asynchronous filter edits, instant-fade mode, optional
feedback and cue capture/recall/live editing. All 726 portable tests passed
(four expected Windows skips). Reports and the previous main TOE are local in
`build/dance-forces/activation-20261028/`.
The canonical main TOE was saved and reopened, passing 585 persistence checks
across 72 flow instances; existing cue data, main-look values and media paths
were preserved.

Before the fix, the local clip read/filter could block the render thread for
about 232 ms. File resolution/stat, parsing and filtering now run in one shared,
bounded preparation worker, with yielding chunks for parsing/filtering. Cold
and warm force sampling in the native test stayed below 0.71 ms, excluding GPU
rendering; those measurements are not a whole-show FPS or three-projector
performance guarantee. File changes are checked asynchronously about once per
second. Use Preload before GO; a new uncached force begins fading when ready.
Live device selection and two-dancer venue behavior still require rehearsal.
