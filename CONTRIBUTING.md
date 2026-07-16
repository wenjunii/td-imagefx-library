# Contributing

Contributions are welcome through focused pull requests. By contributing, you agree that your contribution is licensed under the repository's MIT license and that you have the right to submit every included asset.

## Development checks

Use Python 3.11 or newer and run:

```text
python -m unittest discover -v
python tools/verify_repository.py
```

CI repeats these checks on Windows, macOS, and Linux with supported Python versions.

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
