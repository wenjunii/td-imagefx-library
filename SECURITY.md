# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Security advisories → Report a vulnerability** flow for this repository. Do not open a public issue containing an exploit, credential, private media path, or unpublished advisory detail.

Include the affected package or tool version, operating system, TouchDesigner build, reproduction steps, impact, and any suggested mitigation. You should receive an acknowledgement within seven days. Coordinated disclosure is preferred so users have time to update.

## Supported releases

Security fixes are provided for the current library release. Historical effect packages remain immutable for project reproducibility; a vulnerable historical package is marked or documented as affected rather than silently rewritten. The correction is published under a new exact package version.

## Update and package trust boundary

- Update checking is notify-only. It never installs, activates, imports, or executes discovered code.
- Remote metadata and artifacts require HTTPS. Local sources must be explicitly enabled and confined to an allowed root.
- Feed identity and optional feed digest are bound to the configured source.
- Package staging binds the artifact digest, manifest digest, package identity, and exact version before an immutable install directory is created.
- ZIP extraction rejects traversal, links, special files, collisions, encryption, oversized content, and compression bombs.
- Source URLs stored in status and registry files are redacted to remove queries, fragments, and credentials.
- Project lockfiles are advisory during update discovery and are never rewritten by the checker.

The manually triggered release-preparation workflow does not publish a GitHub Release. It produces deterministic review artifacts, checksums, provenance, and an attestation for a later, separate approval step.

## Secrets

The repository and release archives must not contain credentials, personal access tokens, private keys, `.env` files, machine-local paths, licensed third-party binaries, or private media. Revoke an exposed credential immediately before contacting the maintainers.
