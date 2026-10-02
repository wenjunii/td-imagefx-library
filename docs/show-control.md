# ImageFX Show Control — rehearsal preview

This is a native TouchDesigner cue workstation inspired by show-control
workflows, not QLab itself or a QLab workspace importer. It is a first rehearsal
version. Do not put it into a public performance until you have run a complete
rehearsal on the actual laptop, displays, adapters, audio system and media.

## Open it

Open the canonical `TD_ImageFX_Library.toe`. Enter `/project1/imagefx_demo`,
right-click `show_control`, and choose **View** to open its control panel.
The original ImageFX demo and effects remain available for designing looks.
Audience windows start closed, Master Blackout starts on, and audio starts off.

## Create and run cues

1. Click **Add cue**, then select the **Cue Editor** page on the right.
2. Choose Visual, Audio, Parameters, Stop, or Wait. Select the local media file
   and track 1–3. A blank Visual source uses the built-in test image.
3. Set timing, level and playback options; click **Apply edits**. Editing is
   allowed only after **STOP ALL**. Choosing another row discards unapplied
   editor changes, so apply them first.
4. For visual effects, adjust the modules and eight-slot rack in the original
   `imagefx_demo`, return to the cue panel, and click **Capture look**. This
   saves the enabled modules, their editable values, rack order and effect
   selections into that cue. Layer Composite also captures its backdrop and top
   image/video paths; see the [two-layer media guide](layer-composite.md). Layer
   videos follow the cue clock; embedded audio from those two layers is not routed.
   Use the main movie-audio route or an audio cue for sound. A fresh
   cue with no captured look has effects off and no retained layer files.
5. Select a cue row and click **Preload**. Release Master Blackout for rehearsal,
   then click **GO**. GO advances selection to the next row; it does not stop
   other tracks or audio cues. Use the Cue List Page control for lists over 12.
6. **Pause** freezes the show clock, effects, video and audio. **Resume** resumes
   them. **Stop Selected Cue** targets the selected row. **STOP ALL** clears all
   tracks/audio and resets show time; it does not exit TouchDesigner.
7. Choose a local JSON **Show File** and **Save Show**. Existing valid show files
   get a uniquely named backup. **Load Show** restores cues and output mapping
   with blackout on and audio off. Media is referenced, not copied or uploaded.

Use `.imagefx/shows/` for private show files; that folder is ignored by Git.
Keep a separate backup of both the JSON and its media. Relative media paths are
resolved against the JSON's directory. Save Show is separate from saving the TOE;
rebuilding the library resets the built-in demo cue, but not your saved JSON.

### Timing

| Control | Meaning |
| --- | --- |
| Timestamp | Blank = manual GO. Seconds or `HH:MM:SS.mmm` schedules one trigger relative to the show clock. The clock begins with the first GO. This is not wall-clock time, SMPTE or MIDI timecode. |
| Pre-wait | Delay after manual/scheduled trigger before cue start. GO also waits for media readiness. |
| Duration | Seconds after actual start. Zero holds indefinitely until replaced/stopped, except zero-duration parameter/stop actions are immediate. |
| Fade | Visual crossfade, or audio fade-in and fade-out within its duration. |
| Next Cue Behavior | Manual: no automatic next cue. Continue: trigger next after this cue starts + post-wait. Follow: trigger next after this cue finishes + post-wait. Follow requires a nonzero duration. |
| Hold Visual At End | Freeze the final visual rather than clearing that track at cue duration. Embedded audio stops at that point. |
| Media In / Loop / Speed | Start offset in seconds, looping, and video speed. Standalone audio uses its original speed. |

Timed cues and auto-follow fire at most once in a run. Stop All resets that
history. Stop Selected also disarms that cue's future timestamp/auto-follow for
the current run. A Stop-type cue cancels running, pending and preloaded cues on
its track and their pending follow actions; other tracks keep playing. Automatic
chains skip disabled rows. Timing sliders use practical drag ranges (0–10 seconds
for waits/fades, 0–300 seconds for duration/media in); type exact values for longer
times, up to 86400 seconds. Scheduled cues on a busy standby track report an error instead of
silently replacing its prepared content. Prepare the next cue well ahead of GO:
loading effect networks may cause a hitch and is not guaranteed seamless under
all GPU loads. Each visual track has two decks; finish a crossfade before loading
another cue on that same track. There can be up to eight loaded audio voices.
Preloading a running or held cue is rejected without changing its output; stop
that cue before preloading it again. A first cue after Stop All fades from black.

### Change parameters during a cue

Add a **Parameters** cue targeting an already running visual track. Specify
`module/Parameter`, for example `calligraphic_shadow/Particleamount`,
`motion_studio/Mix`, or `slot1/Mix`. Enter a JSON scalar target value (for
example `0.7`, `true`, or a menu name). Duration interpolates numeric values;
toggles and menus change at the end. Easing is Linear or Smooth. Cue-owned clock,
enable-routing, file, pulse and read-only parameters cannot be automated.

Ink Radial Flow is available as `ink_radial_flow`, including every inherited
Brush/particle/glitter value and its ten radial controls. For example,
`ink_radial_flow/Radialspeed` changes expansion/reverse and
`ink_radial_flow/Staticglittershimmer` changes the stationary grains' twinkle.
Enable the module and desired glitter layer before Capture Look. Its radiation
and glitter use the same pauseable cue clock as the other modules.

To change whole effect combinations or module on/off states, capture a new
Visual cue using the same media and crossfade into it. A new Visual cue cancels
parameter automation on its track. Parameter cues must follow the target Visual
cue; don't rely on simultaneous scheduled entries to establish that dependency.

## Three projectors / monitors

On **Routing**, choose:

| Mode | Content |
| --- | --- |
| Identical | Track 1 copied to all three outputs, with individual mapping/grade. |
| Panoramic | One wide Track 1 canvas cropped across outputs 1–3, left to right. Default 1080p panels use a 5760×1080 render canvas. Three 4K panels use 11520×2160. |
| Independent | Three separate visual tracks; each Output page can select any track. |

Render Width/Height control processing resolution. Each **Output 1–3** page has
its own final width/height (defaults 1920×1080, up to 3840×2160), four corner pins,
source crop, rotation, horizontal/vertical flip, brightness, gamma, blackout, and
four edge fades. **Output Calibration Grid** shows red/green/blue grids.
Corner order is bottom-left, bottom-right, top-right, top-left in normalized
coordinates. Invalid/crossed corner quads and reversed/empty crops retain the
last valid transform/crop and report a Mapping Status error; correct them before
opening the audience canvas. Save Show rejects invalid mapping without changing
the previous saved file.

Panorama Shared Edge Overlap gives adjacent panels shared source pixels. Pair
it with edge fades and real projector overlap during alignment; this is not
automatic photometric calibration. Stop All and preload again after changing
routing/render dimensions/overlap, so cue decks are prepared at the new size.
Media is stretched to the render canvas; use prepared panoramic media, or the
existing fit/fill effect in a captured rack to choose an aspect treatment.

The borderless **Audience Canvas** packs the three outputs horizontally into
one window. Set Windows displays to **Extend**, arrange them left-to-right with
matching desktop scaling, and set Audience Canvas Desktop X/Y relative to the
primary display's top-left. Use **Open Audience Canvas** only after checking the
position. Close it before changing window dimensions or desktop placement.
Different output heights are bottom-aligned in the atlas; equal-height panels
are the simplest arrangement. Separate TOPs `out1_projector`, `out2_projector`,
and `out3_projector` are also available for custom routing networks.

The laptop must actually expose three usable display outputs at the requested
resolution/refresh rate; the GPU model alone does not establish this. A splitter
that only mirrors one signal cannot provide independent or panoramic outputs.
Check the laptop's ports, adapter/dock capabilities, GPU routing and display count.
Start with three 1080p60 outputs, then benchmark 4K with the heaviest real cues.

TouchDesigner Non-Commercial has a 1280×1280 resolution limit, so these show
resolutions need an appropriate paid license. Paid work requires Commercial or
Pro. See [Derivative licensing](https://docs.derivative.ca/Licensing) and
[multiple-monitor guidance](https://docs.derivative.ca/Multiple_Monitors).

## Stereo audio

Choose **Audio** for audio-only cues, or enable **Use Video's Embedded Audio**
on a Visual cue. Mono is duplicated to stereo; stereo preserves L/R; additional
channels are ignored. Audio mixes into one stereo output bus with per-cue gain,
master level and mute. Choose **Stereo Output Device**, then explicitly enable
audio when ready. Default selects Windows' default output; verify it is the
physical headphone jack, not HDMI, a VR device or virtual audio driver.

The 3.5mm output carries two channels only. Ask the venue's audio engineer about
the appropriate stereo cable/DI connection and level into their console. Start
quiet and test both channels. Summed cues can clip: leave headroom; the device's
hard output clamp is not a mastering limiter. Blackout does not mute audio.

The audio and graphics engine share this TouchDesigner process. Heavy rendering
can cause audio dropouts; for a critical show, a separate playback machine or
process may be preferable. The software tests do not prove glitch-free physical
audio. See [Audio Device Out CHOP](https://docs.derivative.ca/Audio_Device_Out_CHOP).

## Verification and current limits

`validate_show_control.py` checks cue preparation, rendered mapping controls,
all routing modes, pause/resume, parameter automation, missing media retention,
stereo decode/gain/mute, native dimensions, editing and show-file round trips.
It checks all 21 cue-editor fields, 63 mapping/grade/flip controls, all 19 pulse
dispatch routes and eight panel-button callbacks. Hardware arm/device/window
controls receive wiring checks only; no sound or audience window is opened.
It never opens audience windows, enables audio output or saves the TOE.
`validate_show_media.py` separately tests image/video decoding, moving frames,
embedded stereo audio and pause/resume across real TouchDesigner frames. Run
`validate_show_control.py` first to generate the image/audio fixtures. Generate
the optional video fixture with FFmpeg from the repository root:

```powershell
ffmpeg -n -f lavfi -i testsrc2=size=320x180:rate=30 -f lavfi -i sine=frequency=440:sample_rate=48000 -t 3 -c:v libx264 -pix_fmt yuv420p -c:a aac -ac 2 build/envoy-validation/show-av-fixture.mp4
```

Load `validate_show_media.py` into a Text DAT inside `show_control`, then call
that DAT's `module.start()` in the Textport. It schedules its own frame-by-frame
checks and writes `build/envoy-validation/show-media.json`; do not save this
temporary QA DAT into your performance TOE. Both validators leave physical
audio disabled and audience blackout on. The full thirteen-validator synchronous
suite includes show-control checks, but asynchronous media QA is a separate run.
The portable `tests/test_show.py` covers deterministic scheduling and quad math.

This version is three outputs, planar corner mapping and one stereo bus. It does
not implement QLab workspace compatibility, groups, OSC/MIDI/timecode input,
curved-surface mesh warping, automatic projector calibration, crash recovery,
redundant playback, guaranteed frame lock, or a show-safe lockout of every
TouchDesigner edit. Local UI/pixel tests are not a substitute for an extended
full-show rehearsal with the actual media, display and audio hardware.
