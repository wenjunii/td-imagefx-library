# Safe task cleanup

Cleanup happens at task completion, after verification and dependency review.
There is no timer, scheduled job, startup deletion or render-thread cleanup.
The user's standing preference authorizes removing known disposable files created
or downloaded for the task without asking again. It does not authorize deleting
arbitrary old files, reference media, user exports or shared dependencies.

## What stays

- Source, tests, manifests, immutable package versions and published TOE/TOX files.
- Personal cues, `.imagefx/` show/runtime data, artwork, reference inputs, user
  exports, prepared motion and important backups.
- Required tools and active/shared environments, including the configured CUDA
  puppet worker. `build/` contains runtime assets as well as disposable outputs.
- Active/shared model weights. When a workflow is explicitly retired, check
  configurations and shared consumers before cleaning its exclusive downloads.
  Model/environment retirement requires a separate dependency audit; the helper
  below deliberately refuses those assets.

Keep anything uncertain. No global package uninstall, GPU-driver change, model
removal or worktree archival is implied by routine scratch cleanup.

## Dedicated task artifacts

Write new one-off scripts, downloaded installers, partial downloads, scratch
copies and generated QA media under:

```text
build/task-artifacts/<unique-task-name>/
```

Keep real show media and user outputs outside that area. Existing legacy folders
are not swept automatically. For legacy cleanup, inspect exact paths and saved
TOE/show/config references separately, preserve backups, and prefer recycling.

The stdlib-only helper `tools/task_cleanup.py` records only explicitly named
artifacts. It does not search for unused files or infer ownership from age.
Registration is the task author's declaration that these artifacts were created
or downloaded for this task; it is not proof that no external consumer uses them.

From the repository root, after the task creates a disposable `scratch/` folder:

```text
python -B tools/task_cleanup.py record my-task build/task-artifacts/my-task/scratch --kind scratch --reason "One-off validation output"
python -B tools/task_cleanup.py clean my-task
```

Kinds are `scratch`, `installer`, `partial_download`, `task_copy`, and `cache`.
Use a new task name for every task. Do not register a directory that will receive
more files; fingerprints intentionally detect content added or changed afterward.
The dry run prints exact targets, purpose, file count and bytes without recycling
anything. Metadata remains in the ignored task folder as `cleanup.json`.

After verification finishes and dependencies are reviewed:

```text
python -B tools/task_cleanup.py clean my-task --apply --verified
```

On Windows, the helper requests the .NET
[SendToRecycleBin option](https://learn.microsoft.com/en-us/dotnet/api/microsoft.visualbasic.fileio.recycleoption)
through PowerShell, on a local fixed drive. It never requests permanent deletion,
empties the Recycle Bin or falls back to `unlink`/recursive permanent removal.
Other operating systems can record and dry-run; apply refuses rather than
silently selecting a different deletion method. PowerShell/backend errors leave
remaining targets in place and produce a failed report. Windows may show an error
or cancellation dialog; cancel it to retain the affected item. Recycle Bin storage
still occupies disk space until the operator empties it separately.

`cleanup-report.json` records completed and remaining paths, bytes and success.
It stays local; do not sync private manifests/reports or media to GitHub.
If an operation partially completes, inspect the report and remaining files;
do not overwrite fingerprints to force a retry.

## Safety boundaries

- Only descendants of the named task folder are eligible; its metadata and the
  task folder itself cannot be targets. Traversal, absolute paths, Windows stream
  aliases, symlinks, junctions, reparse points, hard links and special files fail.
- Targets must be Git-ignored and contain no tracked files. Reserved runtime,
  model, environment and backup names/model extensions are refused.
- Every target is fingerprinted before any operation and rechecked immediately
  before its recycle request. A changed or missing artifact fails closed.
- `--verified` asserts that verification/dependency review is complete. It does
  not stop programs, detect live consumers or eliminate filesystem race windows.
  Run off-air, with relevant workers/encoders stopped and no concurrent writers.
- No cleanup is silently added to `verify_local.py`, CI, TouchDesigner startup,
  playback or video export. A task owner runs the final cleanup explicitly as
  part of finishing the task; this does not mean asking the user every time.

The November 3 maintenance pass recycled about 311 MiB of existing test-only
tools, QA recordings, caches and one-off helpers. It retained source, cues,
runtime environments, shared models and backups; 37 protected-file hashes and
both checked Git worktrees were unchanged. Private evidence stays under ignored
`build/cleanup-20261103/` in the local working project. No native TOE/TOX, shader,
effect parameter or show behavior changed in this cleanup-policy update.
