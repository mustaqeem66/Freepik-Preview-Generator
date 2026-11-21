# Native packaged release evidence (issues #19, #20, #21, #22, #59, #60)

The existing source checks and synthetic format matrix are not a native desktop release signoff. This script records a *local*, human-produced receipt for one actual packaged artifact and one exact commit. It never launches GitHub Actions, and an `init` receipt always starts with **all gates pending**.

## Operator procedure

1. Build an actual **Windows**, **Linux** or **macOS** binary from one documented source SHA. Preserve its checksum and build environment separately.
2. Create one receipt per operating system/artifact (replace the 40-hex SHA and platform):

   ```powershell
   python scripts/native_release_evidence.py init --platform windows --commit 0123456789abcdef0123456789abcdef01234567 --artifact dist/PreviewGen-Setup.exe --output local-native/windows.json
   ```

3. Run native installed/portable workflows on that OS. Record actual platform versions, steps, timestamps, outcomes, screenshots, redacted logs and failed scenarios under `local-native/evidence/`. Investigate failures, especially the unresolved Windows freeze; never claim that a test which wasn't executed passed.
4. Edit the JSON receipt, add a named human `reviewer`, and set a gate to `passed` **only** after observing that case. Each passing gate needs its own redacted evidence file (a single filename, not an absolute path) and that file's SHA-256. The verifier rejects reused filenames.
5. Verify the entire receipt against the **actual same binary** and local evidence directory:

   ```powershell
   python scripts/native_release_evidence.py verify --receipt local-native/windows.json --artifact dist/PreviewGen-Setup.exe --evidence-dir local-native/evidence
   ```
6. Tag CI stages signed artifacts as a **draft** release. Verify its `SHA256SUMS.txt`, verify each platform receipt against those exact artifacts, and resolve outstanding P0 issues before publishing the draft manually. A successful hosted build does not authorize publication.

Until every required native gate has human-reviewed evidence, the verifier returns nonzero, reports individual blockers and never says release certified. It is an evidence integrity helper, not an independent external auditor. A falsified receipt is still possible; a human release reviewer must confirm the evidence quality.

## Coverage and limits

Common checks on every platform: native file picker grants and revoked sources; explicit denied sibling/symlink/ZIP access; protected exports and nonmutation; ZIP/3D/CAD/creator previews with cancellation; multi-folder Add Files and batch reports; native bridge and CSP rejection; independent visual renderer oracles; light/dark and keyboard/accessibility checks.

The packaged GUI smoke requires the bridge-ready marker, refusal of inline and blob scripts, and a decoded JPEG from PreviewGen's loopback server. Engine events, when present, are uploaded separately as diagnostics. The two script probes prove neither external network restrictions nor sandboxing; keep the broader WebView directive and platform checks in the release evidence.

Windows additionally: setup/upgrade/repair/uninstall, portable startup, 300-second idle and freeze diagnostics, 100/125/150/200% scaling, and **independently verified Authenticode signing**. An unsigned development binary can be tested, but the stable Windows release signing gate must remain pending/failed, not marked passed by an explicit 'untrusted' exception. Linux: AppImage and GTK/WebKit smoke. macOS: DMG/Cocoa and signing/notarization verification.

**Sensitive data:** evidence files and receipts remain local unless deliberately reviewed and sanitized. Never commit dumps, user documents, path inventories, private keys or machine-identifying logs. The reporter records basenames and digests, not source artwork. Signing, independent renderer fidelity and native runtime security still need real evidence from the user's devices.

Tests:
```bash
python -m pytest tests/unit/test_native_release_evidence.py -q
```


## 2026-11-21 — Signing material required by the release gate

The release job now signs `SHA256SUMS.txt` with GPG and publishes the
signature and the public key beside it. `install.ps1` verifies that detached
signature before trusting any hash, and reads back the installer's
Authenticode signature. The Windows build job reads the Authenticode
signature back for both `PreviewGen.exe` and `PreviewGen-Setup.exe` and
requires a valid status, a signer certificate and an RFC3161 timestamp.

These gates need secrets that this repository does not carry. Configure them
before the next tagged release, or the release job will fail closed:

| Secret / variable | Purpose |
| --- | --- |
| `WINDOWS_CERTIFICATE` | Base64 PFX used to sign the Windows EXE and setup EXE |
| `WINDOWS_CERTIFICATE_PWD` | Password for that PFX |
| `MACOS_CERTIFICATE` | Base64 P12 used to sign the macOS `.app` |
| `MACOS_CERTIFICATE_PWD` | Password for that P12 |
| `MACOS_DEVELOPER_IDENTITY` | Developer ID Application identity name |
| `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` | Notarization credentials |
| `GPG_PRIVATE_KEY` | Base64 ASCII-armored private key for the release signature |
| `GPG_PASSPHRASE` | Passphrase for that key |
| `GPG_KEY_ID` | Key ID or fingerprint to sign with (repository variable) |

Until `GPG_PRIVATE_KEY` and `GPG_KEY_ID` are set, the release job fails
closed rather than publishing an unsigned checksum file. This is intentional:
a checksum published next to the artifact proves only that the two files
agree, and an attacker who can replace the artifact can replace the checksum
too.
