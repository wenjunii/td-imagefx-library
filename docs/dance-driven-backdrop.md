# Dance-driven Calligraphic Shadow backdrop (local audition)

This audition is retired and is **not installed in the main project TOE**.
Its source and regression tests are retained for reference only; no private
audition assets are distributed.

This is a separate, editable TouchDesigner audition, not an alteration to the
canonical show TOE. It reuses **observed 2D motion only** from the local two-dancer
cache. No character artwork, puppet rig, garment deformation, or 3D model is used.

The backdrop image is deformed around the dancers' hips, shoulders, hands and
feet. Position relative to a neutral pose and movement velocity produce bounded,
smooth local displacement. The warped image feeds the existing Calligraphic
Shadow module; movement energy can also increase its stretch and turbulence.
The frame edges stay anchored and the source aspect ratio is preserved.

## Audition

Open the locally generated `build/dance-backdrop/DanceDrivenBackdrop.toe` and
select `/project1/dance_driven_backdrop`. It starts paused and silent. It has no
audience Window COMP or audio output. The production TOE and rejected puppet
files are untouched.

- **Backdrop Motion:** complete bypass, separate motion/shadow toggles, strength,
  radius, maximum displacement, energy response, tracking-point overlay and reset.
- **Playback:** GO/restart, pause/resume, stop/rewind, seek, speed (including
  reverse), optional loop, sync offset. The original clip is not a seamless loop.
- **Tracking:** smoothing, confidence threshold, independent dancer/body/hand/foot
  weights, pose-follow vs velocity response, neutral pose selection.
- **Stage Mapping:** zoom, pan and mirror only the motion influence positions;
  these do not zoom or crop the backdrop artwork.
- **Media:** backdrop image, optional connected TOP, silent comparison video,
  replacement motion cache and reload controls. Loading a different video does
  **not** extract new motion; supply its matching converted tracking cache too.
- **Calligraphic Shadow / Timing / Subject / Shadow Flow / Ink Surface / Particle
  Shadow / Glitter / Palette:** all original effect controls remain available on
  the outer component. Auto Time follows clip time (not wall time), so pause,
  reverse and seeking remain deterministic. Manual Time is still available.

**Open Side-by-Side Comparison** shows the dance on the left and the treatment on
the right. `out1_image` is the clean 1920×1080 backdrop output. The dancers are not
composited into that output. Disable the diagnostic overlay before projection.

Use Motion Strength / Pose Follow for larger body-following gestures, Velocity
Response for quick accents, and Influence Radius / Stage Mapping Zoom to spread
the choreography through the composition. Motion-off leaves the independently
adjustable Calligraphic Shadow treatment; complete bypass leaves fitted artwork.

## Rebuild without touching the show

The optional preparation tool needs NumPy (TouchDesigner includes it; the
dependency-free package manager does not require it). Given the existing private
observations, run:

```powershell
py -3.11 tools/prepare_dance_backdrop.py <observed-motion.json> --output build/dance-backdrop/motion.json --video <dance-video.mp4>
```

It refuses to overwrite an existing destination. The converted JSON retains six
observed anchors per dancer, confidence, sample rate and optional video hash.
It does not contain a rig or executable Python. Confidence gates suppress bad
joints, forces are capped, and time-independent smoothing permits repeatable seeks.

In a **separate blank TouchDesigner session**, execute
`touchdesigner/scripts/build_dance_backdrop.py` with the normal TD globals and call
`build(checkout_root, motion_json, backdrop_image, comparison_video)`. Use
`save_new(checkout_root)` only after validation. It refuses production/harness
sessions, rejected puppet sessions and existing native filenames.

Native checks are in `validate_dance_backdrop.py` (bounded values, finite actual
pixels, bypasses, effect bindings) plus real-frame transport/pulse tests. The
focused unit tests use synthetic data and do not require the private media.

## Limits and privacy

The 2026-10-06 local audit passed **110 native control/pixel checks**, including
both endpoints of **77 editable numeric controls**, plus **12 real-frame
transport/button checks**. The repository suite completed **280 tests**, with
four expected Windows symlink-permission skips. A 12-second silent side-by-side
review was rendered from source seconds 10–22. These are functional checks, not
certification of artistic quality or the three-projector hardware setup.

### Playback performance regression

The first audition had a GO-playback slowdown of approximately **4.4 FPS**.
The controller was setting custom slider range metadata every frame, causing
TouchDesigner to rebuild parameter interfaces after the Python callbacks.
Ranges are now configured once per loaded motion clip. Normal playback and
seeking update values only; loading a different-duration cache still updates
the ranges correctly. Three portable tests guard this behavior.

On the local RTX 3080 Ti Laptop, the corrected native benchmark measured
**60.0 FPS at 1920×1080** and **60.0 FPS for the 1920×540 comparison** with both
the video and effect rendering. Each stage rendered 180 frames, discarding
15 warm-up frames; no resolution or effect-quality reduction was used.
These short single-module measurements are not a three-projector show guarantee.

For repeatable testing, load `benchmark_dance_backdrop.py` into a Text DAT in
the isolated audition and call `start(component, new_report_path)`. It tests
both outputs, records cook-count deltas and frame intervals, checks a 30 FPS
regression threshold, and restores transport values. It does not save the TOE.

This is recorded **2D pose-driven visual response**, not recovered 3D motion,
physical fluid simulation, live camera tracking, or pixel-perfect choreography
reconstruction. Tracking swaps/occlusions can still need authored corrections.
The effect is intended to respond artistically to movement; it does not turn the
flames into dancer silhouettes. Artistic approval and show rehearsal remain
necessary before integrating the output into cues or the 4K wall.

All generated native files, motion caches, media paths and review renders remain
under ignored `build/`. **Do not publish these private audition files.** The
reusable scripts contain no private input paths. No media is uploaded and no
GitHub sync is performed by the builder.
