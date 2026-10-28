# Dance Puppet in ImageFX

`imagefx_demo/dance_puppet` is an optional, reorderable workflow stage. It is
also available in the two independent composition branches and Show Control
cue decks. It starts disabled; old cue looks and their effect ordering are
preserved. The standalone v3, v4 and v5 TOEs remain available unchanged.

## Play the supplied dance as a cue

The personal local project can contain the prepared cue described below. The
clean GitHub TOE does **not** include that cue, the private reference artwork,
character profile, pose models or prepared movies. On a fresh checkout, configure
the optional worker and a calibrated character profile, prepare your own media,
then use Add Cue / Capture Look. The code is reusable; artwork and profiles are
operator-supplied assets.

The local integration adds **Black & White Dance Puppet** after the existing
cues. Select it in Show Control and use **Preload**, then **GO**. Its prepared
61.6-second motion plays from the opening pose. Pause/Resume and Go Back use
the cue clock. It is a visual-only cue; no soundtrack or camera is started.
Assign its track/projector destination using the existing output controls.

For changes while it plays, select its PLAY row, choose **Edit Running Cue**,
then **Effect Module → Dance Puppet → Edit Controls**. **Update Cue Look**
keeps changes; **Cancel Changes** restores the prior settings. For off-air work,
stop playback and use **Recall Look**. **Save Show** preserves the committed
cue settings and media paths. The prepared movie remains an external local file.

To make another puppet cue, enable Dance Puppet in the designer, choose a
prepared movie and the desired appearance, then Add Cue / Capture Look.
**Reset Preview to Opening Pose** sets preview time to zero and pauses it;
enable **Animate Preview** to run again. Cue capture stores the current phase,
so use the opening pose when a cue should start at the beginning.

## Black/white style, framing and transparency

- **Black / White Reference Palette** is on: black bodies and pale linework.
  Body Color and Line Color remain independently adjustable. Turning it off
  restores the prepared atlas colors without repainting source artwork.
- **Complete Bodies / Cropped Composition**, Zoom, X/Y Position and Mirror
  change framing without stretching the characters. A wider output fits the
  16:9 puppet canvas, preserving body proportions.
- **Transparent Background** is on. `dance_puppet/puppet_rgba` contains real
  straight RGBA, including opaque black bodies; black is not keyed away.
- Put Dance Puppet after a backdrop effect in Workflow and enable **Over
  Upstream Effects** to composite the figures over it. Turn this off for a
  standalone transparent puppet output. Downstream effects can still change
  or discard alpha; the supplied standalone puppet cue disables those stages.
- **Feedback Trails** starts off. Trail Amount, Half-Life, Softness and Clear
  Trails are optional image-space finishing effects, not additional tracking.
  Playback seek/restart/loop boundaries clear accumulated history.
- **Puppet → Fade In** starts at 1.5 seconds; set it to 0 for an instant entrance.
  It fades the finished RGBA layer, including feedback trails. Enabling the
  puppet, Animate Preview/restart and cue GO start a new fade; Pause/Resume
  hold/continue the existing fade. Transparent mode reveals the upstream image
  behind the fading figures. The setting is captured in the cue look.

## Use another prerecorded dance

### Fixed camera and preview transport

**Remove Source Camera Motion** is on by default for new preparation. It tracks
static background features while excluding the dancers, then compensates 2D
pan, roll and zoom before rigging. It does not pin the dancers' hips or remove
their choreography. Rebuild after changing it; the existing prepared movie is
not modified in place. Keep the original Dancers Video available for rebuilding
an unstabilized motion cache. A stabilized cache is never compensated twice.
Strong parallax, cuts or insufficient background can limit estimation; low
confidence holds the last transform, and unreliable jobs fail safely.

Turning **Animate Preview** on starts at motion time zero (plus Motion In
Point). Turning it off holds the current frame. **Pause Preview** holds and
**Resume Preview** continues from that frame. **Reset Preview to Opening Pose**
returns to zero and pauses. Playback Speed changes do not jump the phase. Show
Control owns running cue clocks; use its Pause/Resume for a running cue. A/B
branches inherit their parent composition clock.

### Together or on separate projectors

**Puppet → Characters / Projection Mode** offers **Both Characters Together**,
**Fan Character Only**, and **Chain Character Only**. Preparation writes three
synchronized 60-fps RGBA movies. Solo movies include the complete individual
character with fixed framing over its choreography, not a crop of the combined
movie; overlapping dancers therefore do not cut each other out. All three
retain alpha and the native black/white palette controls.

Capture a Both cue on the center projector's track, or capture Fan and Chain
cues on the left/right tracks. To start the side cues together, preload them
and use Continue with zero pre/post wait and the same start time/speed. Stop or
black out the center track when switching to the side composition. Choose
**Independent** routing for separate cue canvases; Direct vs 2×2 Wall Output is
only the physical delivery mode. These settings are stored in each cue look.
For Panoramic routing, one cue supplies all panels; use Layer Composite's fixed
1080p placement if a character should occupy one panel of that shared canvas.

1. In **Motion Files**, select **Dancers Video (for analysis)**.
2. Keep the supplied calibrated Character Profile, or choose another profile.
3. Press **Analyze New Video and Build**. Preparation runs in a separate local
   Python process; progress appears in Preparation Status. Do this off-air.
4. The new **Prepared RGBA Movie** replaces the selected file only after the
   job succeeds. Cancel Preparation leaves the previous prepared movie intact.
5. Review crossings, deep bends and hidden limbs, then Capture/Update Cue Look.

Analysis observes 17 two-dimensional joints per person, represented in the
rig's 33-slot adapter. The first two dancers are assigned left-to-right and
subsequently associated by hip position. This is not measured 3D mocap, and
overlaps can still swap identities. No MediaPipe dependency is required.

Preparation uses RTMPose/YOLOX and the connected v5-style rig, then writes a
60-fps Hap Alpha movie. Interpolation is not extra motion measurement. Cue
playback decodes this movie rather than running pose inference. The original
dancer video is not needed to play an already prepared cue. Clips are limited
to ten minutes per preparation job; split longer sequences into cues.

## Live camera mode

Select **Motion Source → Live Camera**, set **Local Camera Device Index**, and
press **Start Camera / Tracking Explicitly**. Both dancers must be visible for
initialization. The status shows tracking readiness/rate. Start the camera
before GO; a live cue cannot silently launch a camera. All live cue instances
read the one shared local session, using the same character profile. Stop and
restart the camera after changing profile, camera index or Live Smoothing.

**Stop Camera** releases the device. Losing the TouchDesigner heartbeat also
stops the worker. Unavailable/stale live frames become transparent, not a
stale frozen performer. The worker has no network listener and does not record
camera footage. The UI leaves Windows camera privacy decisions to the user.

Live mode is a rehearsal feature, not a certified 60-fps performance path.
The original combined-view live pipeline measured roughly 20–23 tracking
updates/second using DirectML adapter 1. The newer camera-stabilized,
three-view pipeline measured about 11.5 updates/second while native tests were
also running; that is not a dedicated performance benchmark. CPU-only was about
1.4 in the earlier test. A local camera connection and heartbeat shutdown were checked separately,
but two live dancers, venue lighting, occlusions and end-to-end latency still
require rehearsal. Prepared playback is the more predictable show option.

## Reuse with other characters

You do not need to rebuild ImageFX or Show Control. A character profile points
to calibrated body/garment/prop atlases and may override proportions and sprite
UV rectangles. A different flat drawing is **not** automatically rigged: prepare
overlapping parts and calibrate their anchors/atlas layout first, then rebuild
the prepared motion for those characters. The current rig types remain `fan`
and `chain`; different prop mechanics require a rig extension.

Example profile (atlas paths are relative to this JSON):

```json
{
  "kind": "imagefx.puppet.profile",
  "version": 1,
  "characters": [
    {"name": "Tall fan figure", "rig": "fan", "atlas": "fan-atlas.png"},
    {"name": "Broad chain figure", "rig": "chain", "atlas": "chain-atlas.png"}
  ]
}
```

The current default is `build/dance-puppet/characters-default.json`. Original
reference images and calibrated artwork are unchanged; palette conversion is
a shader operation. Unseen side/back anatomy and cloth contact remain stylized
2.5D approximations, not a physically reconstructed body.

## Local backend and validation

Keep the backend outside TouchDesigner's Python. This workstation now uses
`build/puppet-cuda-venv/` with RTMLib, ONNX Runtime GPU (CUDA), NumPy, SciPy,
OpenCV, Pillow and ModernGL. The previous `build/puppet-live-venv/` DirectML
environment and existing CPU/prototype environments are retained.
Private `.imagefx/puppet-settings.json` contains the Python/model/FFmpeg paths
and explicit adapter selection. All build jobs and shared RGBA buffers stay in
ignored local folders. Neither credentials nor artwork/model weights are
bundled into the code or uploaded by this integration.

### RTX and CUDA routing

Launch the main TOE from the project folder with:

```powershell
./tools/start_imagefx_rtx.ps1
```

The launcher locates the RTX 3080 Ti bus using `nvidia-smi` and starts
TouchDesigner with `-gpubusid`. This laptop currently uses `0:1:0:0`.
It does not close an existing TD session; save/close that session before
launching another. `-Project` and `-TouchDesigner` override the file/executable.
The per-app Windows High performance preference is also configured, but the
explicit launcher provides a stronger, inspectable selection at startup.
Verify `sysinfo.GPUName` in TD: it should report the NVIDIA RTX 3080 Ti.
GPU affinity is a launch setting, not a setting stored inside the TOE.
See [Derivative's GPU affinity documentation](https://docs.derivative.ca/Using_Multiple_Graphic_Cards).

The isolated worker uses CUDA **device 0** (not the old DirectML adapter 1).
CUDA device numbering is separate from Windows display/DirectML numbering.
Local `.imagefx/puppet-settings.json` now selects:

```json
{
  "python": "<project>/build/puppet-cuda-venv/rtx/python.exe",
  "live_provider": "cuda",
  "live_gpu": 0,
  "render_gpu": "RTX 3080 Ti"
}
```

Keep the existing model/FFmpeg path fields. The shared provider setting applies
to both Analyze & Build and Start Camera. Existing prepared movies do not need
to be rebuilt; playing them does not run pose inference. CUDA loads its private
pip CUDA/cuDNN DLLs, verifies both model sessions use CUDA, and rejects silent
whole-session CPU fallback. Some small ONNX shape operations may still execute
on CPU. The renderer also rejects a device that does not match `render_gpu`.
The live status line reports the actual provider and graphics renderer.

GPU responsibilities are deliberately distinct:

- Pose detection/estimation: ONNX Runtime CUDA on the RTX.
- External puppet rendering: OpenGL on the RTX.
- TD effects, feedback, layer compositing, mapping and output: Vulkan on the RTX.
- Rig deformation/smoothing, camera-motion compensation, capture/readback and
  file operations: existing CPU paths. Hap Alpha preparation remains CPU
  encoding to preserve transparency; ordinary H.264 NVENC is not a substitute
  for these alpha movies.

The Windows venv redirector was observed launching the shared base Python,
which ignored the venv GPU preference and selected Intel Iris Xe for OpenGL.
`tools/create_puppet_gpu_entrypoint.py`, run with the isolated venv Python,
copies that installation's CPython executable/runtime DLLs into its private
`rtx/` folder. The existing `pyvenv.cfg` still selects the same environment.
Only this private executable receives the RTX preference; other Python apps
and global GPU settings are unchanged. Recreate the entry point after a base
Python upgrade. `tools/configure_imagefx_gpu.py --app <exe> --apply --backup
<new-json>` applies only explicitly listed per-app preferences and backs up
their previous values. Without `--apply` it is read-only.

To reproduce the isolated package setup, create a fresh Python 3.11 venv, install
`prototypes/dance_puppet/requirements-cuda.txt`, then install
`rtmlib==0.0.16 --no-deps`. Do not install both `onnxruntime` and
`onnxruntime-gpu`: RTMLib's declared CPU dependency shares the same import files
and can overwrite the GPU runtime. `pip check` may consequently report RTMLib's
CPU package requirement as absent; use a real CUDA model inference check.
Do not install these packages into TouchDesigner's Python. This setup was
checked with NVIDIA driver 617.42 / CUDA driver 13.4; see the
[ORT CUDA requirements](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)
before reproducing it on another machine.

For a repeatable GPU check (using a prerecorded video, never the camera), run
the private worker Python with `prototypes/dance_puppet/validate_gpu.py
--models <local-model-folder> --video <dancer-video> --start 4
--output <new-local-report-folder>`. It checks actual CUDA kernel events in
both models and the actual OpenGL renderer; a provider merely being installed
is not sufficient. The output directory must be new so earlier reports are
not overwritten.

The 2026-10-27 CUDA check executed kernels in both model sessions (8,196 CUDA
kernel events, 96 CPU shape/support events in a 12-frame profile), detected both
dancers, and confirmed the RTX OpenGL renderer. A separate 60-frame live-path
replay, with three 1280×720 RGBA views and camera-motion compensation, measured
about **17.3 tracking updates/second** while TD was open (median inference
34.0 ms, rig 23.1 ms, rendering/readback 10.2 ms). This is a short prerecorded
diagnostic, not a camera/venue rehearsal or a 60-fps guarantee. A two-second
CUDA motion cache also rendered all three 1920×1080 Hap Alpha movies at 60 fps.
The 60 fps is the movie's playback rate, not the live tracking rate.

For a stage-by-stage live-worker profile without opening the camera, run the
private RTX worker Python with:

```powershell
& '<private-rtx-python.exe>' prototypes/dance_puppet/profile_live.py `
  --config '<existing-local-job/config.json>' --video '<local-dancer-video.mp4>' `
  --output '<new-local-report-folder>' --frames 180 --warmup 15
```

This runs the real pipelined live worker against the supplied recording, keeps
camera-motion compensation enabled according to the config, and changes no
TouchDesigner settings. It requires explicit CUDA and RTX-renderer settings,
local model/character files, and a new report folder. Timing wrappers are scoped
to the diagnostic process. `profile.json` separates decode, person detection,
pose estimation, stabilization, rig deformation, render/readback, shared-memory
publication and status-file writes. Camera IDs are rejected by the diagnostic.

On 2026-10-27, a 180-frame replay with 15 warm-up frames, 1920×1080 input and
three 1280×720 RGBA output views measured **19.8 steady updates/second** while
TouchDesigner was open. Median CPU rig deformation was **25.0 ms**; the CUDA
pose-estimation path including its CPU preprocessing/postprocessing was
**24.2 ms**. Person detection was **43.1 ms** when run (every fourth frame).
Camera stabilization was **7.0 ms** and input decode **4.2 ms**. RTX drawing plus
readback was **3.3 ms per view**, including **1.6 ms** of framebuffer readback/
GPU wait. The p95 completed-update interval was **78.6 ms**.

These are overlapping/nested host timings: do not add the medians or interpret
them as CUDA kernel times. Unlike the earlier 17.3 result, the steady rate
excludes initialization/warm-up; it is **not evidence of a speedup**. The next
optimization candidates are the CPU rig path and inference preprocessing/
detector cadence, with tracking quality rechecked before changing cadence.
Moving every CPU step to CUDA is not automatically faster. No rig, tracking,
stabilization or animation behavior was changed by this profiling pass.
The local report is `build/dance-puppet/cuda-validation/live-profile-20261027/profile.json`.

The previous local settings, main TOE and per-app preferences are backed up in
`build/dance-puppet/gpu-backup-20261027/`. CUDA jobs and diagnostics remain local
in ignored folders. No camera or audience output was opened for these checks.
The GPU follow-up passed 665 portable tests (four expected skips), 117 puppet
tests, 41 native cue/control checks and 14 saved-main-TOE reopen checks. All
24 embedded puppet runtimes were updated; both existing cues and the main look
were preserved. This is a local GPU-routing check, not a new clean release.

Focused native validation uses a disposable Show Control copy, checks cue
time/alpha/control pixels, update/discard, and show save/reload, and never opens
audience windows. A separate live-bridge check uses the prerecorded dancer video
as diagnostic input. It is not evidence of a full live stage rehearsal.

The local integration check on 2026-10-27 passed 641 portable tests (four
expected Windows symlink skips), 109 puppet tests, 41 native cue/control checks,
12 sample-cue checks and 17 saved-project reopen checks. A different two-second
dance clip was analyzed and rendered successfully. These focused checks do not
recertify every legacy effect or three-projector performance. The original main
TOE is preserved in `build/dance-puppet/integration-backup-20261027-144822/`.

The camera/preview/layer follow-up passed 649 portable tests (four expected
skips), 112 puppet tests, 41 existing puppet checks, 47 new cue/layer checks,
and 181 Layer Composite checks. The current dance has synchronized combined,
fan-only and chain-only alpha movies in `build/dance-puppet/camera-fixed-separated/`.
The preceding main TOE is retained in
`build/dance-puppet/camera-preview-composite-backup-20261027/`; the updated local
show is `.imagefx/puppet-camera-layers-20261027.show.json`.
Both the staged and canonical saved TOEs passed 25 reopen/playback checks.

The A/B editing, feedback and panel-layout follow-up adds complete module/slot
navigation for each Layer Composite branch. Trails now accumulate transparent
history separately from the final background and strength mix. Low FPS is not
mistaken for a seek; Trail Half-Life uses elapsed animation seconds. Turning
Transparent Background off no longer hides all older trail pixels.

Its focused checks passed 658 portable tests (four expected skips), 112 puppet
tests, 155 native editor/trail/layout checks, 187 Layer Composite checks,
47 cue/layer checks, 41 puppet checks and 34 projector-review checks. The native
trail fixture measures actual top-layer alpha/brightness, pause, decay, amount,
clear and bypass behavior. The preceding TOE is retained in
`build/dance-puppet/ab-feedback-backup-20261027/`.
Both the staged and canonical TOE passed 15 additional saved-layout/editor/
feedback checks and the existing 25 saved-project playback checks after reopening.

Those 2026-10-27 checks describe the additive **local integration**. The
2026-10-28 publication recheck rebuilt clean source-bound artifacts and passed
the broader control suite; see [Control validation](control-validation.md).
The personal TOE, private cue paths and character assets remain local and are
not part of the clean distribution.

Older-show compatibility was checked alongside Dance Forces in
`validate_legacy_motion_looks.py`: existing puppet cue media, animation,
transparent alpha, preview pause/resume, live feedback editing and saved look
reload all passed. Cues from before the puppet module existed now inherit the
matching main/A/B workflow's passive prepared files so the puppet can be enabled
in a recalled or running draft. No effect is enabled automatically, and explicit
saved paths (including blanks) are not replaced. Update Cue Look and Save Show
commit new puppet settings; Cancel leaves the older cue untouched. This focused
suite passed 83 native checks and 121 portable puppet tests.
