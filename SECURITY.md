# Security Policy

## Supported versions

Security fixes are shipped on the latest published release and on `main`.
Older releases may not receive backports.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private vulnerability reporting:
<https://github.com/Mustaqeem66/Freepik-Preview-Generator/security/advisories/new>

If that is unavailable, email **zenartisan66@gmail.com** with:

- the affected version or commit,
- reproduction steps or a proof of concept,
- the impact you believe it has.

You can expect an acknowledgement within a few days. Please allow time for a
fix and release before public disclosure.

## Scope

PreviewGen processes untrusted local files (images, archives, 3D assets,
documents). Reports involving archive extraction, path handling, renderer
sandboxing, the pywebview bridge, installer verification, or update/release
integrity are especially welcome.

## Release integrity

Official builds are published on the GitHub Releases page with a
`SHA256SUMS.txt`. Verify downloaded artifacts before running them. Release tag
builds are required to be signed (Windows) and signed plus notarized (macOS);
the workflow fails instead of publishing unsigned release assets.
