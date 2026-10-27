# Native packaged-app evidence integrity re-audit — 28 October 2026

## Problem verified in current source
The existing receipt validator checks an artifact checksum and checksums for individually recorded native QA files. However, it previously allowed all 13 Windows gates (or all 11 Linux/macOS gates) to point at the **same single text file** while returning a PASS when every status was edited to `passed`. The original valid-receipt fixture unintentionally demonstrated this possibility.

A second issue: a basename-only restriction does not reject symlinks inside the evidence folder pointing at content outside that folder. Empty evidence files were accepted as long as the SHA-256 matched.

## Remediation
- Require a distinct evidence basename for each native release gate. Case-fold comparisons prevent filename case clashes on typical Windows/macOS filesystems.
- Reject empty files and symbolic-link evidence; preserve the SHA-256 check of each actual file and packaged artifact.
- Add regression tests that show a single duplicated gate file can no longer satisfy the full matrix; preserve the successful distinct-file receipt path.
- Every gate remains marked `pending` in new receipts. The validator **does not** independently prove what a human reviewer actually observed, verify Authenticode, determine real application behavior, or attest native OS provenance. Human QA still has to approve the content of every evidence file.

## Upgrade guidance for local QA
Existing receipts that reused one file for multiple gates must be updated to link each gate to a separately named, non-empty regular evidence file with its actual SHA-256. Do **not** set a gate to `passed` on a synthetic log or author-only placeholder.

```bash
python -m pytest tests/unit/test_native_release_evidence.py -q
python scripts/check_release_locally.py --mode full
python scripts/native_release_evidence.py verify \
  --receipt local-native/windows.json \
  --artifact path/to/signed/PreviewGen-Setup.exe \
  --evidence-dir local-native/evidence
```

This is a **source-level receipt integrity fix**. Issues #19, #20, #22, #59 and #60 require independent OS, security and real-format evidence before release sign-off. No hosted GitHub Actions were dispatched.
