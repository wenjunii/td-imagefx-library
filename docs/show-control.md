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

The panel uses a 1660x900 design canvas with a 720-unit right-hand inspector at
normal text size. It displays only the custom show-control parameters; including
the container's built-in parameters caused dropdown arrows and file-picker `+`
buttons to be clipped, even when their pages were hidden. Widening the window
alone did not fix that issue. Maximize the viewer if its outer window extends
beyond your desktop. The media `+` picker and cue/export dropdowns have been
checked directly in TouchDesigner after the custom-parameter-only correction.

## Cue notes

Select a cue and click **Cue Notes** (or open the **Cue Notes** tab). Enter up to
4000 characters in **Notes**, then press **Save Cue Notes**. This changes only
that cue's notes: playback, timing and the Look Editor draft are untouched.
It also works while the show is running. The legacy Notes field on Cue Editor
is linked to the same value. A **Notes** column beside each cue shows its saved
notes on every cue-list page. Click either the cue or its note to select that
cue. Long or multiline notes are shortened to a one-line preview; the full text
remains in **Cue Notes**. A dash means that cue has no saved notes. Press **Save
Cue Notes** to refresh the row after editing; changing selection does not save
an unfinished edit. The selected cue's note also appears beneath the live-look controls.
Press **Save Show** outside a draft to persist committed notes (playback may continue)
in the show JSON. Unsaved note text is replaced when selecting another cue.

## Go Back and blackout cues

After a completed blackout, GO and Go Back fade in only the destination cue
from its own media in-point and saved animation phase. The previous cue's end
frame is removed from the transition, not revealed underneath the incoming cue.
Normal transitions between visible cues continue to crossfade.

The top toolbar includes **Go Back**. It restarts the previous enabled cue
before the last cue you fired (skipping disabled rows); it does not reverse a
video or rewind the show clock. Before the first GO it uses the selected row
as the starting point. At the first enabled cue it does nothing. Resume first
if paused, and let an in-progress crossfade finish before returning to a visual.
The current output stays on air while the previous visual prepares off-air.
The cue's pre-wait and fade still apply. Pending forward cues and scheduled
auto-follows are cancelled so they cannot immediately jump forward again;
future timestamp cues keep using the existing show clock. Other visual tracks
and audio continue. Go Back is not a whole-show undo or a snapshot restore.

To insert a blackout:

1. **Stop All**, select the row before the blackout, then click **Add blackout**.
2. On **Cue Editor**, choose **Blackout Scope → All Visual Tracks** (default)
   or **Selected Track Only**, and set **Track** for the latter.
3. Set **Fade Seconds** (`0` = instant), pre-wait/timestamp and other cue timing,
   then **Apply edits**. **Duration = 0** keeps it active indefinitely. A finite
   duration completes at black and can auto-follow; it does not restore video.
4. Select the blackout row and press **GO**, or let its timestamp/follow fire.
   **Save Show** includes the blackout cue and its settings in the show JSON.

Blackout affects the visual tracks before output mapping, in both direct-display
and 2×2 wall modes. It leaves audio playing and keeps confidence-monitor labels
and diagnostics available (its projector previews show black). In identical or
panoramic routing all projectors use the Shared Canvas Cue Track (default 1); use independent routing for
individual projector blackout. The next visual on a blacked-out track fades
that track back up; other tracks stay black. Stopping a blackout cue freezes its
current level rather than unexpectedly revealing content. Master Blackout,
per-output blackout and calibration-grid safety/settings remain independent;
turn calibration grids off for normal show playback. Use Stop All or audio
controls separately when you also want silence.

## Review the projector feeds

The bottom of Show Control has a **Projector Review** preview of the final output,
including mapping and blackout, not the main design canvas or off-air draft.
On **Projector Review → Review View** choose:

- **Auto / Follow Output Mode** (default): the full 2×2 canvas in wall mode,
  or three side-by-side projector feeds in direct mode.
- **2x2 Video Wall / Full 4K Canvas**: the actual packed `out1_wall_4k` output,
  with P1 top-left, P2 top-right, P3 bottom-left and confidence bottom-right.
- **Three Projectors / Side by Side**, a single **Projector 1/2/3**, or
  **Confidence Monitor / Quadrant 4**.

Both the inline preview and **Enlarge Projector Review / Open Projector Review**
follow this choice. The inline image is aspect-preserving and downscaled;
enlarge opens the full-resolution source in an operator viewer. It never opens
a physical output window. Selecting the wall view while Direct Displays is active
is labeled as a wall preview only; it does not switch your physical Output Mode.
Existing saved review selections are preserved when reinstalling the controls.

Signal Status reports whether the selected output window is open or closed.
A black feed during blackout is correct. This is a software preview, not proof
of what the HDMI cable, processor or physical projector is displaying.
The existing **Look Preview** is still a separate silent, off-air editing view.

## Output Mode

Use **Show Control → Output Mode**, the second tab after Transport:

**Canvas Layout** chooses content: Identical, Panoramic, or Independent.
**Output Mode** chooses the cable/display delivery below. They are independent:
all three layouts work with both delivery modes.

- **Direct Displays (separate projectors)** opens one borderless window per
  assigned projector. Set **Direct P1/P2/P3 Display** to the display indices
  shown under Connected Displays; `-1` leaves that output unused. Use Windows
  extended-desktop mode. Each window fills its selected display. Set rendered
  width/height on **Output 1 / Output 2 / Output 3** (1080p, 4K or custom).
  The Check result reports render size and display size; differing sizes are
  scaled to fit the display window, not a change to the Windows video timing.
- **4K Wall Processor (2x2 + confidence)** uses one 3840×2160 display, with
  TL=P1, TR=P2, BL=P3, BR=confidence. Each tile stays 1920×1080. Select the
  processor display here; the **Wall Output** tab retains its advanced controls.

Press **Check Selected Output**, then **OPEN SELECTED OUTPUT** when ready.
**CLOSE ALL OUTPUTS** closes both delivery routes, including the legacy atlas.
Transport's existing Open/Close buttons now use these same actions. Changing
mode or active direct display/resolution settings closes the windows and
requires an explicit reopen. Opening does not clear show/wall blackout, and it
is blocked during an offline export. The operator's primary display is protected
unless explicitly allowed; duplicate direct display assignments are rejected.

This selects physical delivery only: cue tracks, saved looks and
Identical/Panoramic/Independent content routing are unchanged. You can assign
cue tracks/projector content later. Mode and physical display indices live in
the TOE, not in cue looks or Save Show JSON. The legacy `audience_atlas` TOP
remains available for compatibility, but the Direct mode no longer requires a
single three-across desktop window. No display is selected or opened by default.

## Wall Output controls

The **Wall Output** tab puts the 4K processor controls directly in Show Control.
These are two-way links to `wall_output`, not a separate output pipeline. It
includes feed enable, both show/wall blackouts, source routing and TOP paths,
fit, calibration pattern, confidence quadrant, diagnostics, display selection,
and the existing safe **Check Display**, **OPEN 4K WALL**, and **CLOSE 4K WALL**
actions. The original wall module remains usable and stays synchronized.

For cue playback choose **Wall Source Mode = Show Control**. For a picture in
Projector Review, **Enable Projector Feeds** must be on and both **Show Master
Blackout** and **Wall Projector Blackout** must be off (per-output blackout/level
also applies). Releasing blackout affects the real projector feeds too; check
your venue before doing it. Opening a window never clears either blackout.
The confidence quadrant can remain visible while projector feeds are black.

Relative TOP paths on this tab are relative to `wall_output`, just like its
original controls. Wall hardware settings are saved with the TOE, not cue looks
or Save Show JSON. See [4K wall setup](wall-output.md) for display assignment and
the fixed quadrant map. Adding the tab does not open or arm any display.

## Export a visual cue to video

1. **STOP ALL** and close audience/wall output windows. Export shares the GPU;
   do it before the performance, not while delivering a show.
2. Select a Visual cue. On **Export Video**, choose **Selected Saved Cue**, or
   **Current Look Draft** for recalled, uncommitted edits. Apply metadata and
   capture the look first when exporting the saved version.
3. Choose an **Export Folder**, format, resolution, FPS, duration and effect
   start time. Defaults: silent MP4, 1920x1080, 30 FPS, 10 seconds, start 0.
   3840x2160, 1280x720 and custom even dimensions (16–4096) are available.
   Rates: 24, 25, 30, 50 or 60 FPS. Maximum duration: one hour.
4. Press **Export Video (Silent)**. Progress counts frames. Rendering is
   frame-stepped, so it can take longer than the finished clip's duration.
5. Check **Export Status** and **Last Output File**. Each export gets a unique
   subfolder; existing clips are never overwritten. **Cancel Export** stops
   the job and retains any partial file, labelled as incomplete.

The default `.imagefx/exports/` folder is local and Git-ignored. A separate cue
copy is rendered; saved cues, the main workflow and an active draft stay intact.
The global project frame rate/realtime setting is not changed. Playback or an
audience window opening during export aborts it. Concurrent exports are rejected.

The **cue/draft** export includes the **cue visual and captured effect chain/final crop**, resized
to the chosen dimensions. It does not export a whole cue sequence, projector
calibration/blackout, packed 4K wall or audio. Use dimensions matching a cropped
aspect ratio to avoid stretching. Effect start offsets the effect clock and
source-video position; feedback/history effects start fresh, without a precomputed
simulation history. Duration rounds to whole output frames (minimum one).

MP4/H.264 needs a Commercial/Pro license and supported encoding hardware;
**MOV / Motion JPEG** is also available. TouchDesigner's license resolution
limits still apply. See the official
[Movie File Out TOP documentation](https://docs.derivative.ca/Movie_File_Out_TOP).

### Record the complete 2x2 wall, including confidence monitor

On **Show Control → Export Video → Export Source**, select
**2x2 Wall + Confidence / Real-Time**. This records the actual
`wall_output/out1_wall_4k` TOP at **3840×2160**, with four 1920×1080 quadrants:
top-left P1, top-right P2, bottom-left P3, bottom-right confidence monitor.
Projector mapping, masks, edges, calibration patterns and blackouts are baked
into the file. The confidence preview and current diagnostics are recorded too.

1. Keep physical output windows **closed** while recording (shared GPU).
2. Set up the three feeds/cues and check **Projector Review → 2x2 Video Wall**.
   Enable **Wall Output → Enable Confidence Quadrant**. Turn **Show Diagnostics**
   on if you want the statistics text included. Clear blackouts only when ready;
   the recorder never changes them for you.
3. Choose the export folder, MP4/H.264 or MOV/Motion JPEG, FPS, and maximum duration.
   Wall resolution is fixed at UHD. The offline resolution/size/start-time
   fields are disabled and ignored; the **Export Mode / Canvas** readout confirms it.
4. Press **Export Video (Silent)**. It records the wall as it currently plays.
   You can run/advance/pause cues during recording; it does not start or rewind
   cues automatically. To capture the lead-in, start recording before **GO**.
5. Recording finishes at the selected length. **Stop Wall Recording & Save**
   finalizes a shorter usable file. **Cancel Export** keeps any partial file
   but labels it incomplete. Check **Export Status** and **Last Output File**.

This mode is **real-time rehearsal capture**, not an offline render of the full
show timeline. Encoding may reduce FPS; inspect the reported dropped-frame count
and review the movie before using it. Low render FPS cannot be turned into smooth
motion by selecting a higher export FPS. Opening an output window, disabling the
confidence quadrant, or a wall/encoder error aborts the capture. No display is
opened, no show/cue/calibration data is saved, no global clock is changed, and no
audio is exported. The file contains the confidence text as recorded, not live
statistics when played later. Play the complete 4K file 1:1 into a processor in
2×2 mode; do not send this packed file to a single projector.

Developer check: `validate_wall_export.py` records local MP4/MOV test clips from
disposable show/wall copies, exercises fixed sizing, confidence validation,
Stop & Save, cancel, cleanup and state preservation. It writes the report to
`build/envoy-validation/wall-export.json`; decode the exported files to confirm
frame counts and quadrant placement. It never opens a physical output.

Developer checks: `show_review_export.py` installs additively, without restarting
ShowControlExt or rebuilding the user's show. `validate_show_review_export.py`
requires stopped playback, closed output windows and no draft. It creates
test cues in a disposable Show Control copy and writes local clips. It verifies
that the original document, selection, unsaved editor fields and main workflow
stay unchanged, then restores wall settings and removes only its test copy.
The clean-release audit exercised H.264 at 1080p/4K/custom size, Motion JPEG,
draft export, video-source timing and cancellation; all five clips independently
decoded with the expected dimensions/frame counts and no audio stream. See the
[control validation record](control-validation.md) for scope and limitations.

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
5. Select a cue row and click **Preload**, then wait for **Ready**. Release Master Blackout for rehearsal,
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

### Edit the running cue live

You do not have to stop playback or Recall Look to adjust the cue on air:

1. Select the Visual cue row marked **PLAY**. GO normally advances selection to
   the next row, so reselect the cue you actually want to edit.
2. Click **Edit Running Cue** on the Show Control panel or Look Editor tab.
   Wait for any crossfade or parameter automation on its track to finish first.
3. In **Look Editor**, choose **Effect Module → Edit Controls**. Edit its module
   sliders, colors, switches, workflow order, rack slots or composition branches.
   These controls target that exact playback deck, not the main design workflow.
   The status reads **LIVE CUE EDIT**. **Open Preview** shows its live effect output.
4. Changes immediately reach the cue's normal track and assigned outputs. Existing
   mapping, masks, output grading, Direct/4K Wall routing and all blackouts still
   apply. No hardware output or audio device is automatically armed.
5. Choose **Update Cue Look** to commit the current settings, or **Cancel Changes**
   to restore the controls as they were when editing started. Neither action
   reloads the main media, recreates its audio voice, or rewinds the playhead.
   Update saves only the look: cue source, timing, track, notes and original
   starting animation phase stay unchanged. The on-air animation continues.
6. **Save Show** writes the committed settings to your local JSON. This is allowed
   while playback runs, but only after finishing/canceling the draft.

Pause/Resume and GO/Go Back remain usable. Continue/Follow cues are not blocked.
When the edited cue ends, stops, is replaced, or a parameter cue takes over its
track, the draft is detached and its settings are retained for **Update Cue Look**
or **Cancel Changes**. The outgoing/held image is not reverted during transition.
Cancel then discards the retained draft only; it never modifies the new cue.
Only one look edit can be active at a time. **Save as New Cue** and the off-air
**Show/Stop Live Look** routing controls are disabled in running-edit mode.

This is live audition, not an undo of rendered history: changing feedback controls
can affect accumulated trails, and Cancel cannot reconstruct past GPU frames.
Changing a layer file or rack effect may need media loading/shader compilation;
test those changes in rehearsal. Keep cue source/timing edits in the stopped
Cue Editor. Reopening the TOE or reinitializing Show Control discards uncommitted
drafts, so Update and Save Show before closing.

### Edit a captured look safely

Every visual module's own **Enabled** switch is bound bidirectionally to its
matching switch on the containing workflow. You can use either switch in the
main designer, a recalled look, or either composition branch. Modules stay
independent; turning one off does not turn the others off. The links survive
cue recall and workflow reordering. The rack's **Master > Rack Enabled** mirrors
**Apply Video Effects**, and every loaded slot's **Enable** mirrors its rack
**Slot Enable**. Rack master bypass preserves the individual slot settings.
Existing saved cues retain their captured on/off state until you explicitly
Capture Look or Update Cue again.

1. **STOP ALL**, select a Visual cue, then press **Recall Look** (also on the
   **Look Editor** page). Apply any pending Cue Editor metadata changes first.
2. Stay on **Look Editor**, choose **Effect Module**, then press **Edit Controls**.
   A parameter window opens for that module in the recalled cue, with its custom
   parameter tabs visible. Choose **Workflow / Module Switches** for the draft's
   enable switches and ordering, or **FX Rack / Slot 1–8** for individual slot
   parameters. **Open Preview** opens the full-size silent off-air output; the
   small preview at the bottom remains available. These shortcuts never open
   the original `imagefx_demo` modules. The temporary workspace is still
   `/project1/imagefx_demo/show_control/look_editor` if you prefer node editing;
   it contains the captured module settings, rack, Layer Composite files and
   effect ordering. Controls are disabled until a draft is active, and an empty
   slot reports an explanatory status instead of opening another workflow.
3. Optionally press **Show Live Look** to audition your changes on projection.
   **Look Editor → Live Look Target Track** starts at the cue's track and can
   select track 1–3. Routing still applies: Independent sends it to outputs
   assigned to that track; Identical/Panoramic use Shared Canvas Cue Track (default 1). Both Direct and 4K
   Wall modes use these same mapped feeds. Projector Review shows the audition.
   The status says **LIVE DRAFT (not saved)**. Mapping, masks, grading, and
   master/per-projector/wall blackouts remain active; this does not open output
   windows or enable audio. Release the appropriate blackouts yourself when
   ready. **Stop Live Look** returns to normal program output without discarding
   the draft. This Recall workflow requires a stopped show, so that output is normally black.
4. Choose **Update Cue** to replace only that cue's look. Its name, media,
   timing, track and audio settings are unchanged. The preview remains on the
   saved frame, marked **SAVED / FROZEN**; **Open Preview** stays available.
   **Recall Look** reopens an editable copy. Or choose **Save as New Cue**
   to append a separate copy without modifying the original. The new copy starts
   **disabled**, with no timestamp and manual next-cue behavior; enable it in
   Cue Editor and Apply Cue Edits when ready.
5. **Cancel Changes** discards the temporary draft. The original cue and main
   design workflow remain untouched. Finish or cancel before selecting another
   cue, playing/preloading, editing cue details, or loading/saving the show.
6. **Save Show** after updating/creating a cue to persist it to your local JSON.

Update Cue, Save as New Cue, Cancel Changes, STOP ALL, and TOE startup turn live
audition off. Updating stores the look; press GO after finishing the draft to
play the committed cue. Live audition is never restored from a saved show.

Recall previews the cue's saved image/video (including in point, speed and loop)
at the show's render dimensions, with effects running or frozen as captured. It does not
play audio or start a show clock. It stays off-air until **Show Live Look**. It is a
look preview, not a rehearsal of pre-wait, fade, duration or parameter cues.
Change the main source and cue timing in Cue Editor after finishing the draft;
manual rewiring or changes to the draft's internal `media` reader are not saved.
Layer Composite file controls are captured normally. Drafts are temporary and
are discarded on TOE reopen/extension reinitialization; **Update/Save New, then
Save Show** before closing. Recalling an invalid look or missing media leaves
the stored cue intact. This editor requires a stopped show, not just Pause.

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

If an automatic next cue targets a track that is still crossfading (or whose
standby deck is reserved), its row stays **WAIT** until that track is available.
It then prepares and starts automatically. This also applies to Follow and
timestamp triggers. Other tracks are not blocked. Pre-wait remains measured
from the original request; resource waiting does not consume the media-decoding
timeout. Pause holds the queue; Stop Selected, Stop All and Go Back can cancel
it. Missing files or decoding failures still show **ERROR**. Manual GO/Preload
during a busy crossfade still reports that the track is busy without queuing.

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

Preparation is staged across frames on the inactive deck. Unchanged rack
packages are reused; shader/media warm-up finishes before the deck is connected
to the track. GO on a not-yet-ready cue waits, while the previous cue continues.
Preload ahead of time for a show: a cold decoder or shader compilation can still
take longer than a frame. Set Fade above zero (for example 0.5–1 second) for a
smooth crossfade; a zero Fade remains a hard cut by design.

Cue playback multiplies its local animation clock by each module's saved
Time Scale. Zero freezes and negative values reverse the procedural animation.
Recall Look uses the same starting phase instead of absolute app uptime.
Capture Look, Update Cue and Save as New Cue store each module's effective
animation phase and running/frozen state, including both composition branches
and the rack clock. Thus saving a procedural ink look does not restart its
pattern at zero. A running animation continues from the saved phase on Recall
or GO; turning **Auto Time** off in the draft preserves its **Manual Time**.
Offline cue/draft export uses the same phase and Time Scale. Cue Media In and
video transport settings are not changed by capturing an effect's phase.
For Ink Dream/Brush/Radial Flow, captures also save the continuous rendered
position (`render_time`). This preserves the look after live Animation Speed
changes, which no longer seek to a different composition. Older captures without
that field retain their former `time × Animation Speed` starting position.
Older show files remain supported and use phase zero until updated. This stores
procedural clocks, not a full GPU feedback/simulation cache: stateful third-party
feedback effects may still require warm-up or prerendering for an exact repeat.

Run `touchdesigner/scripts/validate_look_animation.py` in a Text DAT and call
`module.start()` for the isolated saved-preview/Recall/GO pixel regression on
the three ink modules, reverse/export clocks and A/B branch phase offsets.
The report is `build/envoy-validation/look-animation.json`.
Static controls, palette, dot pattern and both glitter layers are verified with
rendered pixels, not only a parameter round trip. Run
`touchdesigner/scripts/validate_cue_playback.py` as a Text DAT and call
`module.start(1920, 1080)` for the real-frame off-air regression; its report is
`build/envoy-validation/cue-playback.json`. It does not open audience windows,
enable sound, modify the user's show file, or certify physical-projector timing.

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

For **one 4K feed into a 2x2 video-wall processor**, use the dedicated
`imagefx_demo/wall_output` module instead of Open Audience Canvas. It packs
projectors 1/2/3 into top-left/top-right/bottom-left and a confidence multiview
into bottom-right, all at 1920x1080. See [4K wall output](wall-output.md).
Select its Show Control source mode to retain all cue and output mapping below.

### One cue across three projectors

1. In **Output Mode**, set **Canvas Layout → Panoramic (one wide canvas)**.
2. Set **Shared Canvas Cue Track** to the track of your visual cue (1, 2, or 3).
   Other visual tracks are not part of this canvas; audio is unchanged.
3. Set **Canvas Render Width Per Panel = 1920**, **Canvas Render Height = 1080**,
   and overlap **0** to start. This creates one **5760×1080** effect canvas.
   The main workflow follows automatically while **imagefx_demo → Output →
   Follow Show Canvas Resolution / Fit** is on (default). Its Effective Canvas
   field shows the actual size and fit; manual HD / 4K / Custom values are retained
   and become active again when Follow Show Canvas is off.
4. Choose physical **Output Mode → Direct Displays** or **4K Wall Processor**.
   For the processor, keep **Wall Output → Wall Source Mode → Show Control**;
   a standalone wall source override bypasses cue routing and is flagged in Canvas Summary.
5. Select the cue, Preload, and GO. P1 receives the left third, P2 the center
   third, P3 the right third. **Projector Review → Three Projectors / Side by
   Side** shows the continuous panorama; wall review shows its packed tiles.
   Check/Open the selected hardware output and release blackouts when ready.
6. Use each projector's mapping, mask and feather controls to align the picture.
   **Save Show** preserves layout, shared track, render dimensions, overlap and media fit.

**Canvas Media Fit → Auto** (default) uses **Fill / Crop** in panoramic mode:
the original image/video is scaled equally on both axes, then center-cropped
to fill the canvas. A 1920×1080 clip fills 5760×1080 by scaling to 5760×3240
and retaining the center 1080-pixel-high band. It loses top/bottom content but
does not distort proportions. This fit happens **before** the visual effects,
for GO, Recall Look and live cue editing, not only for the projector preview.
Explicit **Fill / Crop**, **Fit / Letterbox**, and **Stretch** remain available;
Stretch is the only option that changes proportions. Auto uses Fit / Letterbox
for Identical and Independent layouts. Wide source media avoids unnecessary crop.

When the main workflow follows Show Canvas, Canvas Media Fit also controls its
source fitting; the manual Source Media → Image Fit control is disabled. Turn
Follow Show Canvas off to use that manual control again. Fit does not alter
video speed or audio. Look modules with their own media/fit settings remain independent.

This is one cue/effect render split three ways, not three duplicated cue instances.
The wall cable remains 3840×2160: three 1920×1080 slices plus confidence, **not**
a 5760-wide HDMI signal. For three directly connected 4K projectors, 3840×2160
per panel gives an 11520×2160 render; this is substantially heavier on the GPU.
The 2×2 processor always outputs 1080p per tile, regardless of render quality.

Canvas controls on Output Mode are two-way links to **Routing**, not a second
copy of the settings. Existing shows without Shared Canvas Cue Track use 1.
Changing layout/dimensions/overlap/track/media fit closes physical output windows for safe
reconfiguration. Prepared, running and recalled decks resize in place without
reloading media or resetting cue time; resolution changes can still incur GPU
allocation/compilation and change aspect-dependent effects or feedback history.
Configure the canvas before the show and rehearse at final resolution.

On **Canvas Layout** (also **Routing → Three-Output Content Mapping**), choose:

| Mode | Content |
| --- | --- |
| Identical | Shared Canvas Cue Track repeated on all three outputs, with individual mapping/grade. |
| Panoramic | One wide Shared Canvas Cue Track cropped across outputs 1–3, left to right. Default 1080p panels use a 5760×1080 render canvas. Three 4K panels use 11520×2160. |
| Independent | Three separate visual tracks; each Output page can select any track. |

Render Width/Height control processing resolution. Each **Output 1–3** page has
its own final width/height (defaults 1920×1080, up to 3840×2160), four corner pins,
source crop, rotation, horizontal/vertical flip, brightness, gamma, blackout, and
four edge fades. **Output Calibration Grid** shows red/green/blue grids.
For organized controls, use **Projection Mapping → Projector to Adjust → Open
Mapping Controls**. Its Shape / Mask / Edges / Output pages are two-way links to
these same settings. New rectangle, ellipse and image masks have position, size,
rotation, inversion, level and softness controls. All-edge feather and blend
curve supplement the existing individual fades. Calibration is saved with the
show, not a cue look. See [projection mapping and masks](projection-mapping.md).
The Projection Mapping page and individual projector panels include section
resets, plus complete calibration resets. Full reset includes output resolution
and grade but preserves routing and blackout. **Save Mapping + Cues to Show File**
uses the same JSON saver as **Save Show** (finish/cancel any look draft first). Applied custom mask
points are embedded in that show; mask images stay external. **Load Show**
restores the complete saved calibration and safely disarms the outputs/audio.

Corner order is bottom-left, bottom-right, top-right, top-left in normalized
coordinates. Invalid/crossed corner quads and reversed/empty crops retain the
last valid transform/crop and report a Mapping Status error; correct them before
opening the audience canvas. Save Show rejects invalid mapping without changing
the previous saved file.

Panorama Shared Edge Overlap gives adjacent panels shared source pixels. Pair
it with edge fades and real projector overlap during alignment; this is not
automatic photometric calibration. Set up routing/render dimensions/overlap
before playback where practical, then Check/Open the output after changes.
Original media is aspect-fitted before the effect chain according to Canvas
Media Fit. Existing shows without that setting use Auto; choose Stretch explicitly
if a legacy look intentionally depended on the former stretched source.

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

`validate_running_look.py` adds 63 real-frame checks for the running-cue editor:
projection pixels, non-destructive Update/Cancel, playback/clock continuity,
all three ink modules, rack/order/branch restoration, video/audio reader retention,
automatic Continue/Follow transitions, and ended-draft handling. It is part of
the deferred control suite and does not open hardware outputs or enable audio.

`validate_show_control.py` checks cue preparation, rendered mapping controls,
all routing modes, pause/resume, parameter automation, missing media retention,
stereo decode/gain/mute, native dimensions, editing and show-file round trips.
It checks all 21 cue-editor fields, 63 mapping/grade/flip controls, all 23 pulse
dispatch routes and twelve panel-button callbacks. Recalled-look checks cover
every captured module/rack/order/layer value, pixel response, update, separate
copy, cancel, invalid recall, playback guards and persistence. Hardware arm/device/window
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
audio disabled and audience blackout on. The full nineteen-validator synchronous
suite includes show-control checks, but asynchronous media QA is a separate run.
The portable `tests/test_show.py` covers deterministic scheduling and quad math;
`tests/test_show_look_editor.py` covers draft transaction safety.
`tests/test_look_editor_controls.py` covers module/slot navigation, preview
targeting, useful parameter tabs, empty/stale drafts, and prevention of a
fallback to the main workflow. Navigation uses a separate embedded helper, so
it can be installed without reinitializing ShowControlExt or discarding an
operator's open draft.
`touchdesigner/scripts/validate_look_editor_controls.py` is a focused native,
read-only audit for an already-recalled draft: it checks all menu targets and
preserves the cue document, designer look, and draft values. It does not run
playback or claim a full-show performance test.

`validate_look_editor_media.py` is a separate real-frame test using the same
generated PNG/MP4 fixtures. Load it into a temporary Text DAT and call
`module.start()`. It checks all four actual look-edit pulse events, decoded
image/video previews, advancing frames, loop/speed/in-point bindings, silent
isolation, missing-media rejection, cancellation and safe restart. It writes
`build/envoy-validation/look-editor-media.json` and removes its disposable show
copy. Run it only after stopping the show and finishing any live look draft.

This version is three outputs, planar corner mapping and one stereo bus. It does
not implement QLab workspace compatibility, groups, OSC/MIDI/timecode input,
curved-surface mesh warping, automatic projector calibration, crash recovery,
redundant playback, guaranteed frame lock, or a show-safe lockout of every
TouchDesigner edit. Local UI/pixel tests are not a substitute for an extended
full-show rehearsal with the actual media, display and audio hardware.
