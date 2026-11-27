# Offline machine handoff

Use a complete, versioned checkout when moving ImageFX to another workstation.
The main TOE needs supporting sources, operators and packages. Keep the target
machine's private shows, media, device settings and motion/MCP configuration
separate from the transfer.

## Prepare locally

1. Identify a reviewed Git commit that contains a clean native build and its
   `docs/native-validation.json`. Keep the source checkout as-is. The full
   commit below is the merged Rehearsal Log build, PR #33:

   ```console
   python tools/prepare_offline_handoff.py --revision fa3051363d222367f526a3c5b7c4a6cca17a3568 --target 5090
   ```

2. Keep the four files created under `build/handoffs/5090/fa3051363d22/`:
   `ImageFX-5090-fa3051363d22.zip`, `SHA256.txt`, `INSTALL.txt`, and
   `handoff.json`. The target label is only a folder name, not a device address.
   Nothing is transferred, activated, installed, or published.

The tool uses only the pinned committed tree, even if the working checkout has
uncommitted edits. It compares every file in the archive against its Git blob,
applies the credential scan to those bytes, and rechecks all recorded TOE/TOX
artifacts and native source hashes. It refuses machine-local paths, raw audio
and video files, model files, linked entries, transformed exports, and existing
output destinations. Only the published configuration example is allowed under
`.codex/`; do not install it over a working target configuration.

## Install later, alongside the current copy

1. Confirm it is safe to use the target machine, stop playback/recording, and
   make a target-local backup of the working checkout, show JSON, mappings and
   referenced media. Retain its display, audio, camera and worker configuration.
2. Transfer the ZIP and its companion files. Before extraction, compare the
   SHA-256 to `SHA256.txt`. On Windows, run this in the ZIP's directory:

   ```powershell
   Get-FileHash -LiteralPath '.\ImageFX-5090-fa3051363d22.zip' -Algorithm SHA256
   ```

   Stop if the hash differs. Extract to a separate folder; do not overwrite
   the working checkout. Open `TD_ImageFX_Library.toe` from the extracted
   project folder rather than moving the TOE by itself.
3. Keep both blackouts enabled, audio disabled and physical output windows
   closed. Point **Show File** at a target-local test copy of the show JSON.
   Keep relative media references valid by leaving the JSON and media in the
   same relative layout. Do not resave the original show while checking.
4. Run **Pre-Show Check** and confirm the correct GPU is selected. Exercise
   **Rehearsal Log** on representative cues, then stop playback and any
   recording before saving. Verify that timeline and recorder drops remain
   separate. The archive only verifies the source build; it does not test
   the target's TouchDesigner/driver pair, CUDA workers, projectors or sound.
5. Rehearse the actual outputs, audio and any separate motion workers before
   promoting the new checkout. If something fails, close the new session
   without saving over the original show and reopen the previous TOE from its
   untouched checkout.

This is a workstation handoff, not the effect package release workflow. Use
`tools/package_release.py` for installer/feed release candidates.
