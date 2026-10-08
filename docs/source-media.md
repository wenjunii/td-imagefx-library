# Source Media

Open the rebuilt `TD_ImageFX_Library.toe`, select `/project1/imagefx_demo`,
and select its **Source Media** custom parameter page.

1. Choose **Image / Video File** using its file picker. Local still images and
   movies are supported; codec support follows TouchDesigner's Movie File In TOP.
2. **Auto (File / Test Pattern)** uses your file when selected. Clear the field
   to return to the test pattern. **Test Pattern** ignores the selected file;
   **Image / Video File** without a file shows the letterbox background.
3. Choose **Fit / Letterbox** to keep the whole image, **Fill / Crop** to fill
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

The canvas follows **Output → HD / 4K UHD / Custom**, regardless of file dimensions.
Do not rename or replace `source_image`; all workflow orders and the derived
secondary fixture continue to use it. No workflow reset is necessary.

This is the main designer's media input. **Show Control cues retain their own
source file, timing and transport in Cue Editor.** Capture Look captures effects,
not this preview file or its source fitting controls. Source Media controls are
disabled in recalled-look/cue decks, with an explanatory status, so preview files
cannot silently override cue media. Use Two-Image Composition for per-look A/B
files and independent effects; use cue audio controls for sound. This input does
not route embedded movie audio to the laptop or show outputs.

All files remain local. No input image/video is copied into the public repository.
Validation covers shader pixels and alpha, aspect modes and anchors, HD/4K/custom
dimensions, real image/video decoding, pause/play/seek/restart/reload/reverse/loop,
missing-file status, and cue-media isolation. These checks are not a certification
of sustained multi-projector performance or every possible codec.
