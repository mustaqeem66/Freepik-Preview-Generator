# Native packaged release evidence (issues #19, #20, #21, #22, #59, #60)

The existing source checks and synthetic format matrix are not a native desktop release signoff. This script records a *local*, human-produced receipt for one actual packaged artifact and one exact commit. It never launches GitHub Actions, and an `init` receipt always starts with **all gates pending**.

## Operator procedure

1. Build an actual **Windows**, **Linux** or **macOS** binary from one documented source SHA. Preserve its checksum and build environment separately.
2. Create one receipt per operating system/artifact (replace the 40-hex SHA and platform):

   ```powershell
   python scripts/native_release_evidence.py init --platform windows --commit 0123456789abcdef0123456789abcdef01234567 --artifact dist/PreviewGen-Setup.exe --output local-native/windows.json
   ```

3. Run native installed/portable workflows on that OS. Record actual platform versions, steps, timestamps, outcomes, screenshots, redacted logs and failed scenarios under `local-native/evidence/`. Investigate failures, especially the unresolved Windows freeze; never claim that a test which wasn't executed passed.
4. Edit the JSON receipt, add a named human `reviewer`, and set a gate to `passed` **only** after observing that case. For each passing gate, enter `evidenceFile` (single filename, not a private absolute path) and the SHA-256 of the supporting redacted evidence. Different gates may refer to the same appropriate evidence file if it proves both.
5. Verify the entire receipt against the **actual same binary** and local evidence directory:

   ```powershell
   python scripts/native_release_evidence.py verify --receipt local-native/windows.json --artifact dist/PreviewGen-Setup.exe --evidence-dir local-native/evidence
   ```

Until every required native gate has human-reviewed evidence, the verifier returns nonzero, reports individual blockers and never says release certified. It is an evidence integrity helper, not an independent external auditor. A falsified receipt is still possible; a human release reviewer must confirm the evidence quality.

## Coverage and limits

Common checks on every platform: native file picker grants and revoked sources; explicit denied sibling/symlink/ZIP access; protected exports and nonmutation; ZIP/3D/CAD/creator previews with cancellation; multi-folder Add Files and batch reports; native bridge and CSP rejection; independent visual renderer oracles; light/dark and keyboard/accessibility checks.

Windows additionally: setup/upgrade/repair/uninstall, portable startup, 300-second idle and freeze diagnostics, 100/125/150/200% scaling, signing truth. Linux: AppImage and GTK/WebKit smoke. macOS: DMG/Cocoa and signing/notarization verification.

**Sensitive data:** evidence files and receipts remain local unless deliberately reviewed and sanitized. Never commit dumps, user documents, path inventories, private keys or machine-identifying logs. The reporter records basenames and digests, not source artwork. Signing, independent renderer fidelity and native runtime security still need real evidence from the user's devices.

Tests:
```bash
python -m pytest tests/unit/test_native_release_evidence.py -q
```
