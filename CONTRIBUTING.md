# Contributing

Contributions are welcome through focused pull requests. By contributing, you agree that your contribution is licensed under the repository's MIT license and that you have the right to submit every included asset.

## Local-first development checks

Use Python 3.11 or newer and run:

```text
python -m pip install -r requirements-test.txt
python tools/verify_local.py
```

The install command is a one-time environment setup (repeat when requirements
change). On Windows, use `py -3.11` instead of `python` if the default interpreter
is older. A project-local `.venv` is recommended and is ignored by Git.

`verify_local.py` checks immutable package history against the **locally cached**
`origin/main`, including staged, unstaged and untracked changes inside published
package versions, then runs the full repository verifier **once**. The verifier
already compiles Python, scans tracked files for credentials, runs the unit
suite, and checks manifests, native-artifact hashes and generated documentation.
There is no need to run `unittest` or `compileall` separately first.

The gate never fetches, installs, uploads, commits, pushes, repairs files, opens
TouchDesigner, or rewrites a TOE/show. With dependencies and Git history already
available it works offline. For another locally available history baseline:

```text
python tools/verify_local.py --base origin/main
```

It fails rather than silently skipping a missing baseline or NumPy. Fetch the
target branch explicitly when online, or select a known local baseline; an old
cached base cannot account for changes you have not downloaded. NumPy is used
by motion-math tests, not by the package core. The portable checks do not install
CUDA, pose models, camera drivers or media, and do not certify live rendering.

Before committing, stage only intended files and run
`python tools/check_credentials.py --staged`. New untracked files are not covered
by the tracked-file credential scan until they are added to the index. Never
stage private show media, credentials, local caches or personal TOE backups.

## Low-usage GitHub policy

- **Verify repository** runs one Ubuntu/Python 3.11 job for each pull-request
  update and each push to `main`. Feature-branch pushes do not start a duplicate
  verification run. Immutable-history protection is in the same job, with the
  PR base SHA or previous `main` SHA as its baseline. Newer runs cancel obsolete
  runs for the same PR/branch. No verification artifacts or Actions caches are
  uploaded.
- **Full compatibility (manual)** preserves Windows/macOS/Linux with Python
  3.11 and 3.13. Run it from Actions before a release and after changes involving
  paths, subprocesses, dependencies or platform behavior. Check all six results
  for the exact revision being released; it is not an automatic release gate.
  The workflow's Run workflow button is available after it reaches `main`.
- **Prepare deterministic release** stays manual and runs the unit suite only
  once through the verifier. Its deterministic double-build, immutable-history
  guard, attestations and 14-day artifact retention remain intact.
- Repository-managed CodeQL, Dependabot and other security settings are not
  disabled or modified by this policy. Those can still create their own runs.

Do not add scheduled full-matrix runs or register the show laptop as a
self-hosted GitHub runner. Run expensive native/GPU checks locally during
maintenance, not while a show is playing. Use the guarded live-validation
workflow described in [control validation](docs/control-validation.md); keep
actual venue tests separate from portable source checks.

No branch-protection settings are changed. If required checks are configured
later, use the always-triggered **Repository safety check**, not a manual-only
matrix job. Avoid path filters that leave a required check waiting forever.

## Immutable package history

Never edit, add to, rename, or remove a committed `packages/<id>/<version>/` directory. Even a metadata-only adjustment changes the reproducible identity of that exact version. Copy the package to a new SemVer directory, update its manifest and implementation there, and leave the old directory byte-for-byte intact.

The immutable-history CI check compares every previously committed package-version tree with the pull request. Run it locally against the target branch when changing packages:

```text
python tools/check_immutable_history.py --base origin/main
```

## Effect and release changes

- Keep package IDs stable and declare every distributed shader, pass, component, permission, input, and compatibility constraint.
- Do not add credentials, private media, machine-local paths, or unlicensed code/assets.
- Add tests for validators, updater behavior, and release tooling changes.
- Treat update feeds as signed-style security metadata even before cryptographic signing is enabled: use exact hashes, immutable tag URLs, bounded content, and reviewable sources.
- Use the **Prepare deterministic release** workflow only to create review artifacts. Publishing a tag or GitHub Release is a separate maintainer decision.

CODEOWNERS review is required for package history, update metadata, release tools, and workflows.
