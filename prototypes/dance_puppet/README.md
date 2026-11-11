# Dance Puppet 2.5D — isolated feasibility prototype

## Local ImageFX integration

An optional native `dance_puppet` stage now reuses this rig for prepared
Hap Alpha cue playback and explicit live-camera tracking. It adds black/white
palette controls, true transparency and Show Control look capture/editing.
See [the integration guide](../../docs/dance-puppet.md). The historical native
prototype files below are still separate and are not overwritten. Their
validation counts describe those historical versions, not the new integration.

## Current version: v5 fluid rotations and optional motion finish

v5 is a **separate local prototype**, not an ImageFX show effect. The main TOE,
v3/v4 native files, capture, and navy/pale-ink artwork remain unchanged.

### Changes to the clean animation

- Refines rotations in parent-joint space: upper arms and thighs relative to
  the trunk, forearms and shins relative to their parent limb. Centered cleanup
  reduces isolated angular spikes without introducing a causal playback delay.
- Preserves the taller/slimmer fan character and shorter/broader chain character,
  connected joint anchors, projected bone lengths and ankle-pair translation.
- Adds bounded joint-region bending to sleeves and forearms, continuous shin
  view blends and arm-front opacity, common head-roll transforms across view
  cards, and suppression of brief view-selection flicker.
- Outputs the full 61.6-second dance at **60 fps** using interpolation of the
  existing **30 fps observations**. These are not additional mocap measurements.

### Open v5 and try the finishing effects

Open `build/dance-puppet/DancePuppet25D_Prototype_v5.toe`, select
`/project1/dance_puppet_preview_v5`, and use **Puppet Preview → Open Preview**,
then **GO / Restart**. Keep TouchDesigner's main timeline running. Complete
Bodies, Dark Reference Crop and Match Source Framing remain available.

The new **Motion Finish** page contains:

| Control | Behavior |
| --- | --- |
| Short Motion Blur | Off by default; blends current and two previous rendered frames |
| Motion Blur Amount | 0–1; a starting value of 0.35 keeps the effect subtle |
| Feedback Trails | Off by default; independent of short motion blur |
| Feedback / Trail Mix | 0–1; blends the clean/blurred image with accumulated light-ink trails |
| Trail Half-Life (Seconds) | 0.02–2; controls time-based fading, starting at 0.18 seconds |
| Trail Softness (Pixels) | 0–8; softens accumulated history, not the current source frame |
| Clear Blur / Trail History | Removes old poses, including while paused |
| Reset Motion Finish | Turns both effects off and restores all finish defaults |

Pause and zero speed hold the finished image. Seek, restart, stop, framing,
enable and speed changes clear history; loop jumps also clear it. At amount 0
each effect bypasses. No trails or blur are baked into the three clean videos.
If the output is not being cooked (for example, no viewer or downstream consumer),
history restarts when rendering resumes instead of showing stale poses.

These are image-space finishing effects, **not a physics feedback controller or
optical-flow interpolation**. Short blur is a finite three-frame blend; feedback
uses bounded light-ink accumulation on navy. Strong values can produce ghosted
outlines and should not be mistaken for better tracking or joint deformation.

The native component plays cached renders; the finish, composition and playback
controls are live, but changing the rig itself requires re-rendering. No audio
or audience windows are armed. The offline renderer used Intel Iris Xe in this
environment; this is not an RTX 3080 Ti or multi-projector performance benchmark.

### Local v5 deliverables and reproduction

All media and reports stay under ignored `build/dance-puppet/`:

- `DancePuppet25D_Prototype_v5.toe` and `DancePuppet25D_Preview_v5.tox`.
- `preview-v5/dance-puppet-full-body.mp4`, `dance-puppet-cropped.mp4` and
  `dance-puppet-source.mp4`: 1920 × 1080, 3,696 frames at 60 fps, no audio.
- `preview-v5/dance-puppet-comparison.mp4`: synchronized source/puppet comparison,
  1920 × 620 at 60 fps, no audio; the last source observation is held as needed.
- `preview-v5/layered-motion.npz` (schema 5), `preview-report.json`, QA sheets,
  `v5-attachment-audit.json`, `native-preview-v5-qa.json` and
  `native-preview-v5-finish-qa.json`.

```powershell
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/render_layered.py --version v5 --motion build/dance-puppet/motion-rtm-full.json --fan build/dance-puppet/fan-atlas-v3.png --chain build/dance-puppet/chain-atlas-v3.png --output-dir build/dance-puppet/preview-v5 --ffmpeg "<FFMPEG_EXE>" --smoothing .05 --cloth .65 --output-fps 60
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/compare_preview.py --source "<LOCAL_DANCE_VIDEO>" --render-dir build/dance-puppet/preview-v5 --ffmpeg "<FFMPEG_EXE>"
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/audit_fluid.py
& build/puppet-venv/Scripts/python.exe -m unittest discover -s prototypes/dance_puppet -p "test_*.py" -v
```

In a separate scratch TD session, load `build_td_preview.py` into a Text DAT and
call `build(REPO_ROOT, version='v5')`. Run `validate_td_preview.py` in a
`preview_validation` Text DAT and then `validate_td_effects.py` in an
`effects_validation` Text DAT, each with `begin(component, report_path)`.
The finish validator temporarily demands one output frame per native frame so
tests do not depend on whether its viewer is occluded; that driver stops afterward.
After validation, `save_new_project(REPO_ROOT, version='v5')` writes new filenames
only and refuses existing destinations or a production/harness session.

Validation: **103 prototype unit tests and 57 native TouchDesigner checks pass**
(26 playback/composition checks plus 31 motion-finish pixel/control checks).
All rendered geometry is finite, all lower-robe triangle areas are positive,
and all 338 sampled attachment locations are covered. This does **not** certify
invisible line-art seams or artistic quality: view crossfades, cutout-like deep
bends, approximate foot contact and unobserved side/back views remain. Review
the clean comparison before deciding whether this belongs in the show.
No GitHub sync was performed for this prototype.

## Historical v4 connected character-space rig

v4 is a **separate local prototype**, not an ImageFX show effect. It reuses the
full 61.6-second RTMPose capture and the unchanged v3 navy/pale-ink atlases.
The production TOE, v3 TOE, capture and atlas files are not overwritten.

### What changed

- Separate rest proportions make the fan character taller/slimmer and the chain
  character shorter/broader. The rig transfers movement directions and bounded
  foreshortening instead of copying the dancers' body lengths into the artwork.
- One articulated skeleton owns the head, torso, limb and prop attachments.
  Overlapping joint underlays, softly tucked limb caps and shoulder-following
  torso rows reduce floating pieces. A single connected lower robe replaces
  the three duplicated skirt panels.
- Centered, speed-adaptive motion cleanup reduces isolated spikes without
  resampling the dance or adding causal playback delay. Secondary robe motion
  is bounded; there is **no video-feedback trail** hiding the motion.
- Original choreography timing and stage travel are retained. A weighted
  ankle-pair translation anchors the resized body, but this is not exact foot
  contact IK or a physically reconstructed 3D performance.

**MediaPipe is not required.** This version uses the existing locally extracted
RTMPose/YOLOX observations: 17 measured 2D joints mapped into 33 storage slots.
It does not recover missing depth, finger articulation or hidden body anatomy.

### Open and review v4

Open `build/dance-puppet/DancePuppet25D_Prototype_v4.toe`, select
`/project1/dance_puppet_preview_v4`, and use the **Puppet Preview** page.
**Open Preview** shows the output; **GO / Restart** starts the dance.
The project starts paused, with no audience windows or audio armed. Keep the
main TouchDesigner timeline running so the player's frame callbacks execute.

Composition offers **Complete Bodies**, **Dark Reference Crop** and
**Match Source Framing**. Zoom, pan, seek, speed, pause, stop, loop and enable are
live controls. The native player decodes cached renders; changing rig proportions,
motion cleanup, view overrides or cloth settings requires re-rendering.

Local deliverables under the ignored `build/dance-puppet/` directory:

- `DancePuppet25D_Prototype_v4.toe` and `DancePuppet25D_Preview_v4.tox`.
- `preview-v4/dance-puppet-full-body.mp4`, `dance-puppet-cropped.mp4` and
  `dance-puppet-source.mp4`: 1920 x 1080, 30 fps, 1,848 frames, no audio.
- `preview-v4/dance-puppet-comparison.mp4`: 61.6-second synchronized dancer /
  puppet comparison, 1920 x 620 at 30 fps, no audio.
- `design-v4/full-body-00.00s.png`: neutral proportion review, not dance footage.
- `preview-v4/*-qa.jpg` and timestamped pose stills.
- `preview-v4/layered-motion.npz`: schema 4, including original source points,
  retargeted points, inferred view weights and rigid head rolls.
- `preview-v4/preview-report.json`, `v4-attachment-audit.json` and
  `native-preview-v4-qa.json`: geometry, sampled coverage and native checks.

Validation: **65 prototype unit tests and 26 native TouchDesigner checks pass**.
All 1,848 rendered frames have finite geometry and positive lower-robe triangle
areas. All **338 sampled attachment locations** have opaque coverage. These
tests are not artistic approval: line-art seams, short view crossfades,
approximate feet/contact, cutout-like deep bends and unmeasured side/back views
remain. More matching layered artwork would help those poses; adding MediaPipe
or visual feedback alone would not fix them. Review the comparison before any
decision to use this in a show. No GitHub sync was performed.

### Reproduce v4

Use the existing isolated environment and local atlas/capture files:

```powershell
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/render_layered.py --version v4 --motion build/dance-puppet/motion-rtm-full.json --fan build/dance-puppet/fan-atlas-v3.png --chain build/dance-puppet/chain-atlas-v3.png --output-dir build/dance-puppet/preview-v4 --ffmpeg "<FFMPEG_EXE>" --smoothing .05 --cloth .65
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/compare_preview.py --source "<LOCAL_DANCE_VIDEO>" --render-dir build/dance-puppet/preview-v4 --ffmpeg "<FFMPEG_EXE>"
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/audit_connected.py
& build/puppet-venv/Scripts/python.exe -m unittest discover -s prototypes/dance_puppet -p "test_*.py" -v
```

Use a separate output directory with `--neutral --stills-only` for proportion
review. v4 cleanup accepts `--smoothing 0..0.3` seconds, `--cloth 0..2` controls
secondary robe sway, and existing crop/view override options still apply.
No source-media pixels are edited. Atlas UV remapping and alpha fades occur at
render time; the atlas files remain unchanged.

In a separate scratch TouchDesigner session, load `build_td_preview.py` into a
Text DAT and call `build(REPO_ROOT, version='v4')`. Load
`validate_td_preview.py` into a `preview_validation` Text DAT and call
`begin(component, report_path)`. After validation and visual review, call
`save_new_project(REPO_ROOT, version='v4')`. New filenames are required; the save
helper refuses existing destinations and production/harness sessions. The
builder's default remains v3 for backward compatibility; request v4 explicitly.

## Historical v3 layered rig

v3 renders the **complete 61.6-second dance** (1,848 frames at 30 fps), from the
opening pose, in 1920 × 1080. It keeps the shared dancer placement, navy/pale-ink
appearance, and Complete Bodies / Dark Reference Crop / Match Source Framing
options. It remains a separate prototype, not a production ImageFX effect.

### Deep bends, side views and garments

- Replaces the connected full-character mesh with independently articulated
  heads, torsos, sleeves, forearms, thigh robe panels, shins and props. Arm motion
  can no longer pull a face or another leg through the connected mesh.
- Adds front, right-profile, bowed and back artwork. Left profiles mirror the
  right-profile sprites. View decisions use 2D face/shoulder cues with hysteresis
  and short crossfades; they are **not measured 3D orientation**. Head and torso
  view choices are separate, so a head turn does not force a front-facing chest
  into a side-view drawing.
- Heads/crowns stay rigid; a separate neck/collar bridges the shoulder/head
  attachment during bows. Torso foreshortening does not squash the face.
- Lower robe panels overlap separate shin pieces at the knee instead of folding
  one connected skirt through a deep crouch. Bounded, causal secondary sway
  responds to root motion. The strip's monotone longitudinal coordinate prevents
  triangle inversion, including nearly collapsed projected bones.
- Fans are rigid wrist-driven pieces. The chain is drawn from separate links on
  a hanging curve pinned to both wrists, rather than stretched robe pixels.

### Open this version

Use `build/dance-puppet/DancePuppet25D_Prototype_v3.toe`, then select
`/project1/dance_puppet_preview_v3` and the **Puppet Preview** parameter page.
GO starts playback; Pause/Resume and Stop work independently of the main
TouchDesigner timeline. Keep that main timeline running for frame callbacks.
The project starts paused. No audience windows or audio are armed.

The native player decodes offline renders; it is **not a live native mesh rig**.
Changing rig/view/cloth settings requires re-rendering. Zoom, pan, framing,
enable, speed, seek, pause and loop are live player controls.

Local, ignored deliverables:

- `DancePuppet25D_Prototype_v3.toe` and `DancePuppet25D_Preview_v3.tox`.
- `preview-v3/dance-puppet-full-body.mp4`, `dance-puppet-cropped.mp4`,
  `dance-puppet-source.mp4`, and synchronized `dance-puppet-comparison.mp4`.
- `preview-v3/*-qa.jpg` and timestamped stills for visual review.
- `preview-v3/layered-motion.npz`: source-space points, inferred view weights,
  rigid head rolls and frame rate (schema 3; numeric arrays, no pickles).
- `preview-v3/preview-report.json` and `native-preview-v3-qa.json`.
- `motion-rtm-full.json` and `tracking-full-qa.jpg`.
- `fan-atlas-v3.png` and `chain-atlas-v3.png`: unchanged 1254-square RGBA sheets.
  See [atlas provenance and exact prompts](ATLAS_PROVENANCE.md).

The core repository verifier and **45 focused prototype tests** pass. The v3
geometry audit checks every rendered frame: all coordinates are finite and no
robe-panel triangles invert. Both dancers were detected in all 1,848 frames;
this is coverage, **not joint-accuracy certification**. The native QA report
records the separate TouchDesigner control/pixel checks: **26 checks passed** on
TouchDesigner 2025.32820 after the final render refresh. The Open Preview pulse
and output viewer were also inspected. As with all functional tests, this does
not certify artistic quality, tracking accuracy or show readiness.

Remaining 2.5D limits: artwork for unseen views is interpretive; left profiles
are mirrored; a foreshortened torso card is not a real bent 3D back; depth order
is heuristic; clothes can overlap without physical collision; fingers and prop
roll are not captured. View changes and attachment seams can still read as
cutout animation. These renders need artistic approval before a show.

v1/v2 files and the production `TD_ImageFX_Library.toe` are unchanged. Nothing
from this prototype has been pushed to GitHub.

### Reproduce v3

Use the isolated `build/puppet-venv` described below, not TouchDesigner's Python:

```powershell
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/extract_rtm.py "<LOCAL_DANCE_VIDEO>" --output build/dance-puppet/motion-rtm-full.json --start 0 --duration 62
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/render_layered.py --motion build/dance-puppet/motion-rtm-full.json --fan build/dance-puppet/fan-atlas-v3.png --chain build/dance-puppet/chain-atlas-v3.png --output-dir build/dance-puppet/preview-v3 --ffmpeg "<FFMPEG_EXE>"
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/compare_preview.py --source "<LOCAL_DANCE_VIDEO>" --render-dir build/dance-puppet/preview-v3 --ffmpeg "<FFMPEG_EXE>"
& build/puppet-venv/Scripts/python.exe -m unittest discover -s prototypes/dance_puppet -p "test_*.py" -v
```

`render_layered.py` supports `--cloth 0..2` (secondary sway),
`--smoothing 0..0.5` seconds, `--crop-zoom 1..3`, `--frames N` for smoke tests,
and `--stills-only` for rapid pose reviews. `--overrides <JSON>` accepts a
`fan` and/or `chain` list of `{ "start": 1.0, "end": 2.0, "view": "left" }`
entries, in clip seconds. Views are `front`, `right`, `left`, `bow`, `back`.
These authored corrections affect view selection, not the observed joint cache.

In a separate scratch TOE, execute `build_td_preview.py` and call
`build(REPO_ROOT, version='v3')`. Load `validate_td_preview.py` into a
`preview_validation` Text DAT and call its `begin(component, report_path)`.
After validation, `save_new_project(REPO_ROOT, version='v3')` writes new
filenames only; it refuses existing destinations and ImageFX production/harness
sessions. v3 is now the builder's default; pass v1/v2 explicitly for old builds.

## Historical v2 notes (preserved for comparison)

This is a **20-second motion / look test (v2)**, not a finished ImageFX effect or a
show-ready character rig. It does not modify `TD_ImageFX_Library.toe`, the
effect workflow, cue playback, audience displays, or audio routing.

Two separately tracked dancers drive front-facing textured mesh puppets. The
art uses the dark reference's navy palette and pale linework, with complete
bodies reconstructed as **AI-assisted interpretations**, not exact extractions
of the original drawings. The fan-bearing character uses track 1 (initially
viewer-left); the chain-bearing character uses track 2 (initially viewer-right).

The same animation is available as **Complete Bodies**, **Dark Reference
Crop**, and **Match Source Framing**. The full-body camera fits this entire test
clip; the cropped camera is a closer view. Source framing retains the original
stage coordinates and empty space, for direct comparison with the footage.

## What changed in v2

- Starts at source **0:00**, including the opening pose, instead of 0:04.
- Uses one shared coordinate system for both dancers: no fixed separated
  character centers and no reduced root travel. Their relative hip/shoulder
  placement now comes from the footage.
- Fits the drawn mesh's calibrated shoulders, elbows, wrists, hips, knees,
  ankles and nose to the observed 2D joints, including projected limb lengths.
  This replaces the old angle-only, fixed-length, 85%-strength retargeting.
- Reduces smoothing to 35 ms and preserves the observed first/last poses.
- Keeps faces/crowns rigid and uses the eye line when profile-view ears collapse,
  avoiding false large head rolls. The artwork still remains front-facing.
- Adds a synchronized source/puppet comparison video. No reference audio is
  included. v1 files and the production library are not overwritten.

These changes improve timing and composition, but matching measured joint
coordinates is **not** the same as a convincing finished character performance.
Forward bows, side views and garment folds still expose this simple rig's limits.

## Local deliverables

After rendering and native validation, these are under the ignored
`build/dance-puppet/` folder:

- `DancePuppet25D_Prototype_v2.toe`: separate TouchDesigner preview project.
- `DancePuppet25D_Preview_v2.tox`: preview component, initially paused.
- `preview-v2/dance-puppet-full-body.mp4`, `dance-puppet-cropped.mp4`, and
  `dance-puppet-source.mp4`: 1920 × 1080, 30 fps, 20 seconds, no audio.
- `preview-v2/dance-puppet-comparison.mp4`: synchronized side-by-side review.
- `motion-rtm-opening-20s.json`: observed poses/confidences, source seconds 0–20.
- `tracking-opening-qa.jpg`: sampled pose overlays for review.
- `preview-v2/puppet-animation.npz`: cached mesh positions, per-character UVs
  and triangle indices (schema 2).
- `preview-v2/preview-report.json`: rendering, tracking and mesh-fit metadata.
- `native-preview-v2-qa.json`: live TouchDesigner control / pixel checks.

The previous `DancePuppet25D_Prototype.toe`, `preview/` and 4–16-second motion
cache remain available for comparison.

Open the **v2 prototype TOE**, select `/project1/dance_puppet_preview_v2`, and use its
**Puppet Preview** parameter page:

| Control | Behavior |
| --- | --- |
| Composition | Complete Bodies / Dark Reference Crop / Match Source Framing; time stays unchanged |
| GO / Restart | Start from the beginning (or end when speed is negative) |
| Pause / Resume, Playing | Pause or continue at the current position |
| Stop / Rewind | Pause and return to zero |
| Seek (Seconds) | Scrub while paused or running |
| Playback Speed | −2 to +2; zero holds the current time |
| Loop | Wrap this excerpt; **not seamless**, so defaults off |
| Additional Zoom, Pan X / Y | Refine the selected composition |
| Reset Zoom / Pan | Restore framing adjustments without changing composition |
| Preview Enabled | Hide output and suspend its playback clock |
| Open Preview | Open the component's output viewer |

Keep TouchDesigner's main timeline running for the preview's frame callbacks.
The component has **no audio device or output window**. It plays an offline
render; changing rig / motion settings requires re-rendering with the scripts.
There is no live AI pose inference or live native mesh deformation in this
first TouchDesigner player.

## Important limitations

The prototype has 30 focused Python tests covering playback, joint fitting,
shared placement, opening-pose preservation, degenerate projected limbs and
head-card stability. Native validation checks real TOP pixels, 1080p decoding,
all compositions, seek, pause/resume, speed/reverse, loop boundaries,
enable/disable, numeric bounds and reset pulses. See the local QA report for
the latest TouchDesigner result. Functional checks are not an artistic-quality
or show-readiness certification.

Latest v2 validation: **30 Python tests and 26 live checks passed** on
TouchDesigner **2025.32820**. The Open Preview pulse and actual output viewer
were also inspected using the computer-use workflow. The core repository verifier passed; the production
TOE retained SHA-256 `31c34185af2034653a43306af6e4ede90433c1973d7010d3d57d8ee96ea902f1`.

- Monocular 2D poses are not full 3D mocap. Characters cannot convincingly turn
  around or expose unseen sides; no 3D character models were built.
- Shallow layer order is chosen manually, not recovered from the video.
- Large arm and leg movements can stretch or fold the robe mesh. The chain is
  painted into the artwork rather than independently simulated. Fans follow
  the wrists; the model does not capture finger articulation.
- Head roll is constrained for front-facing cards; neither forward head pitch
  nor turning away reveals a newly reconstructed surface.
- v2 fits tracked positions at full strength. The float32 mesh-anchor residual
  is below 0.001 source pixels, but this measures the solver against its inputs,
  **not** true dancer tracking accuracy or visual correspondence of clothing.
- Both people were detected in all 600 test frames, but detection coverage
  does **not** establish joint accuracy or identity correctness. Sampled overlays
  were reviewed; a full-dance tracking / occlusion audit is still required.
- The footage's soundtrack is not copied into the preview.
- The offline renderer selected Intel Iris Xe in this environment. This is not
  an RTX 3080 Ti performance benchmark or a multi-projector show test.

Before a production module, approve the character design and framing, split
the artwork into proper overlapping body/garment/prop layers, refine the rig,
and manually correct difficult pose spans. A cropped view hides some lower-body
limitations but does not fix the underlying rig.

## Reproduce the experiment

Use a separate Python 3.11 virtual environment. **Do not install these packages
into TouchDesigner's Python** or the core ImageFX environment.

```powershell
py -3.11 -m venv build/puppet-venv
& build/puppet-venv/Scripts/python.exe -m pip install -r prototypes/dance_puppet/requirements.txt
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/extract_rtm.py "<LOCAL_DANCE_VIDEO>" --output build/dance-puppet/motion-rtm-opening-20s.json --start 0 --duration 20
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/audit_motion.py "<LOCAL_DANCE_VIDEO>" build/dance-puppet/motion-rtm-opening-20s.json --output build/dance-puppet/tracking-opening-qa.jpg
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/render_preview.py --motion build/dance-puppet/motion-rtm-opening-20s.json --fan build/dance-puppet/fan-character-v1.png --chain build/dance-puppet/chain-character-v1.png --output-dir build/dance-puppet/preview-v2 --ffmpeg "<FFMPEG_EXE>" --width 1920 --height 1080
& build/puppet-venv/Scripts/python.exe prototypes/dance_puppet/compare_preview.py --source "<LOCAL_DANCE_VIDEO>" --render-dir build/dance-puppet/preview-v2 --ffmpeg "<FFMPEG_EXE>"
& build/puppet-venv/Scripts/python.exe -m unittest discover -s prototypes/dance_puppet -p "test_*.py" -v
```

The extractor uses [RTMLib](https://github.com/Tau-J/rtmlib), YOLOX person
detection, and RTMPose body keypoints. Models are downloaded to the ignored
output folder; all video analysis is local. It observes 17 joints, adapted to
33 storage slots for this experiment; repeated slots are **not extra measured
joints or depth**. Initial identity assignment is left-to-right, then nearest
previous hip association. Do not use this simple assignment without reviewing
crossings and long occlusions.

`extract_motion.py` also retains the first MediaPipe experiment for diagnostics;
it needs optional `mediapipe==0.10.35`. Its two-person tracking was inadequate
for this clip and its output is **not** used by the preview.

Renderer options include `--retarget tracked` (v2 default),
`--smoothing 0..0.5` seconds and `--crop-zoom 1..3`. `--strength 0..1.5` and
`--travel 0..2` apply only to legacy `--retarget angles`, which keeps the v1
fixed-spacing approach. The script rewrites only its
named preview outputs; choose a new `--output-dir` to keep comparisons.

To build the native player from a **separate scratch TOE**, execute
`build_td_preview.py` in TouchDesigner's Textport, then call `build(REPO_ROOT, version='v2')`.
It refuses to replace an existing `dance_puppet_preview_v2` operator. After
validation, `save_new_project(REPO_ROOT, version='v2')` saves new v2 prototype filenames only
and refuses existing destination files. Do not call that helper in a live show
TOE: it saves the current scratch session as the new prototype project.
Both functions accept `version='v1'` to address the legacy player explicitly;
they will still refuse to overwrite existing operators or files.

## Art, privacy and licensing

Original references are unchanged. Built-in image generation produced the two
transparent 1024 × 1536 sprites. Prompt specification: use the light full-body
reference for each character's anatomy, props and robe details; use the dark
reference for navy / pale-ink appearance; one character per image, complete
body, neutral lowered A-pose, transparent background, no text or border.

The calibrated rig is specific to those local sprites. Regenerated art may
need new joint coordinates in `puppet.py`; it is not a universal auto-rigger.

Footage, images, generated art, model weights, caches, reports and native
prototype files remain local under ignored `build/`. Nothing was uploaded to
GitHub. Repository code uses the repository's MIT license, but third-party
model terms and source-media rights remain separate; do not relicense or
redistribute model weights and show footage as MIT project assets.
