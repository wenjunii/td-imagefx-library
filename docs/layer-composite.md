# Layer Composite

Combine a backdrop with a separately graded foreground. Either layer can be an
image or a video, independently. Both files are optional: blank **Backdrop Image / Video** uses TOP input 1, and blank **Top Image / Video** uses
TOP input 2. Without a second input or file, the top layer is transparent.
Local files take priority over connected inputs; clearing a file restores the input.
Media is referenced, not copied into the repository or embedded as media assets.

## Use it in the project

1. Open the current `TD_ImageFX_Library.toe` from the full project folder.
2. Select `/project1/imagefx_demo` and enable **Layer Composite Enabled**.
3. Select `/project1/imagefx_demo/layer_composite`, then use the file pickers on
   **Images** to choose **Backdrop Image / Video** and **Top Image / Video**.
4. Click **Preview This Layer** to view just this composite, or view
   `imagefx_demo/out1_image` for the final effects chain.
5. Adjust **Top Color**, **Top Placement**, **Flicker** and the two **Playback** pages.
6. For a plain two-layer composite, disable other demo modules and **Apply Video Effects**.

This module is first in the demo chain, so the existing effects can process the
combined image. Other enabled modules may intentionally replace or transform it.
The reusable component is `touchdesigner/core/LayerComposite.tox`.

## Controls

- **Images:** module enable, two media pickers, independent Stretch / Fit / Fill modes,
  read-only routing/file status and a direct preview button.
- **Top Color:** opacity (0 = transparent, 1 = full source alpha), RGB tint,
  hue rotation, saturation, contrast, brightness, exposure and color inversion.
- **Top Placement:** position X/Y, scale and rotation.
- **Flicker:** enable, regular on/off / soft pulse / random on/off, rate in Hz,
  visible fraction (or random probability), minimum visibility, soft edge, phase and seed.
- **Timing:** auto time, reversible time scale, manual time and read-only effective time.
- **Backdrop Playback / Top Playback:** separate play/pause, loop, speed/reverse,
  start/seek time in seconds, restart and reload buttons.

## Video playback

With **Auto Time on**, each video runs independently. Turn its **Play / Pause**
off to hold it; **Restart** jumps to its **Start / Seek** time. Changing that
time seeks immediately. **Loop** repeats the file; off holds at the ends.
Speed 1 is normal, 0 holds, and negative values reverse. These controls do not
animate a still image. Use **Reload** after changing a file on disk.

With **Auto Time off**, both videos follow **Manual Time**:
`media time = Start / Seek + Manual Time * layer Speed`. Play/Pause and Restart
are disabled in this mode; moving Manual Time seeks both videos. The show-cue
clock uses this mode so cue pause freezes both layers. **Time Scale** controls
flicker, not video speed; use each layer's **Speed / Reverse** for video.

Layer videos are **visual-only**: their embedded sound is not sent to speakers.
Use the existing show-control audio cue or primary movie-audio route for sound.
Decode support depends on the file's codec and the installed TouchDesigner build;
check the media status fields if a file cannot open.

Flicker starts **off**: the foreground is steady. Minimum Visibility = 0 permits
complete off intervals; 1 makes flicker steady. Visible Fraction = 0 is always
off and 1 always on, in every mode. Rate = 0 freezes at Phase. Soft Edge affects
only Soft Pulse; Seed affects only Random. Random decisions are repeatable per
cycle, not per frame. Set Manual Time to reproduce a cue exactly. In show cues,
the show clock owns Manual Time; use Flicker Rate, not Auto Time Scale, for speed.

High-rate flashing may affect photosensitive viewers. Keep flicker off during
setup, preview at low rates and assess audience suitability before a show.

## Image and alpha behavior

Color controls affect only the foreground. RGB tint multiplies its colors;
inversion is applied after grading and does not invert alpha or the backdrop.
The shader uses straight-alpha Over. Transparent PNGs retain their transparency;
an opaque JPEG covers the backdrop where visible until you lower Opacity.
For premultiplied external TOP inputs, unpremultiply them before connecting.

The output follows input 1's resolution (the demo's HD / 4K / Custom canvas),
or uses 1920x1080 when the reusable component has no input. File dimensions do
not change the canvas. Fit leaves transparent margins; Fill crops; Stretch may
distort the aspect ratio.
Disabling the module bypasses to input 1, including when a backdrop file is set.

## If the output looks blank

Check **Output Status** first. If it says **BYPASSED**, enable **Layer Composite
Enabled** on the demo (or **Module Enabled** on a standalone component). Check
both media status fields for missing files or loading. Set Top Opacity to 1
and disable flicker while diagnosing. The component viewer now references its
own output using a relative path, so copied components no longer display the
empty library template. Use the rebuilt canonical TOE/new TOX, not an older
open copy. **Preview This Layer** isolates the composite from later effects.

## Show cues

**Capture Look** stores both media paths and all artistic settings. Paths are
local, validated on cue load/preflight, and cleared when a later look omits them
so reused decks cannot retain an old foreground. Relative imported paths resolve
against the show JSON's folder. Cue loading waits for both active media files to
decode. File fields cannot be targeted by parameter cues; use numeric controls
such as `layer_composite/Opacity` or `layer_composite/Flickerrate` instead.

The live suite includes `validate_layer_composite.py`: it creates a temporary
test copy, exercises every writable control and file-picker binding, compares actual
pixels for alpha/inversion/flicker behavior, and checks HD/4K rendering. It never
saves the TOE. These fixture checks do not replace multi-projector rehearsal.

That script's `validate_files()` function schedules additional checks on real
TouchDesigner frames and writes `build/envoy-validation/layer-composite-files.json`.
Run `validate()` first to generate its private PNG fixtures. It verifies decoded
PNG color/alpha and compositing; a loading placeholder is not accepted as a pass.
The separate `validate_show_media.py` frame-based test covers waiting for both
layer images before GO and animating opacity with a parameter cue.

`validate_videos()` uses the local generated `show-av-fixture.mp4` and writes
`build/envoy-validation/layer-composite-videos.json`. It checks actual decoded
video motion, manual seek/freeze/reverse, independent per-layer play/pause,
zero-speed holds, start-time seeking while paused, restart/reload, loop repetition,
end holding, mixed still/video inputs, and missing-file status. Test media is not published.
