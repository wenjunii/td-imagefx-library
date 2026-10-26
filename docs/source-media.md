# Source Media

Open the rebuilt `TD_ImageFX_Library.toe`, select `/project1/imagefx_demo`,
and select its **Source Media** custom parameter page.

1. Choose **Image / Video File** using its file picker. Local still images and
   movies are supported; codec support follows TouchDesigner's Movie File In TOP.
2. **Auto (File / Test Pattern)** uses your file when selected. Clear the field
   to return to the test pattern. **Test Pattern** ignores the selected file;
   **Image / Video File** without a file shows the letterbox background.
3. By default **Output → Follow Show Canvas Resolution / Fit** is on. Set
   **Show Control → Output Mode → Canvas Media Fit**: **Auto** uses proportional
   Fill / Crop for panoramic mode and Fit / Letterbox otherwise. Turn Follow
   Show Canvas off to use this page's manual **Image Fit** menu instead.
   Choose **Fit / Letterbox** to keep the whole image, **Fill / Crop** to fill
   the screen without stretching, or **Stretch** to fill with changed proportions.
   Anchor X/Y aligns a fitted image or chooses which part remains when cropping:
   X=0 left, X=1 right; Y=0 bottom, Y=1 top. Color/alpha affect letterbox areas;
   the media's own alpha is preserved inside the image.
4. For movies use **Video Play / Pause**, **Loop Video**, **Video Speed / Reverse**,
   and **Start / Seek (Seconds)**. A speed of 0 freezes; negative speed reverses.
   Seek works while paused. **Restart at Start / Seek** returns to that position,
   not necessarily time zero. **Reload Media File** rereads a replaced file.
   These motion controls do not animate a still image.
5. **Preview Source** shows the fitted input. View `out1_image` for the effects
   result. Read **Media Status** for loading, ready, or missing/unsupported media.

The canvas follows Show Control by default, regardless of file dimensions:
1080p panels give a 1920x1080 normal canvas or 5760x1080 panorama (zero overlap).
The manual **Output → HD / 4K UHD / Custom** settings take effect when Follow
Show Canvas is off. Cropping a 16:9 file to fill the wider panorama removes
top/bottom content; it does not distort the picture.
Do not rename or replace `source_image`; all workflow orders and the derived
secondary fixture continue to use it. No workflow reset is necessary.

This is the main designer's media input. **Show Control cues retain their own
source file, timing and transport in Cue Editor.** Capture Look captures effects,
not this preview file or its manual source fitting controls. The shared Canvas
Media Fit is saved with **Save Show**, not in an individual cue look; cue source
fitting uses a centered crop/letterbox. Source Media controls are
disabled in recalled-look/cue decks, with an explanatory status, so preview files
cannot silently override cue media. Use Two-Image Composition for per-look A/B
files and independent effects; use cue audio controls for sound. This input does
not route embedded movie audio to the laptop or show outputs.

All files remain local. No input image/video is copied into the public repository.
Validation covers shader pixels and alpha, aspect modes and anchors, HD/4K/custom
dimensions, real image/video decoding, pause/play/seek/restart/reload/reverse/loop,
missing-file status, and cue-media isolation. These checks are not a certification
of sustained multi-projector performance or every possible codec.
