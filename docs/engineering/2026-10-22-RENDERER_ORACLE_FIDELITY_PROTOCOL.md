# PreviewGen renderer oracle protocol

## Purpose
The isolated rendering audit previously accepted any decodable multicolored JPEG, which can incorrectly certify distorted CAD geometry, wrong 3D camera framing, missing geometry, or an unrelated embedded thumbnail. A smoke test cannot establish visual fidelity.

This protocol **never manufactures references** from the PreviewGen output being scored.

## How to provide independent evidence
For each application/version/extension being evaluated, a tester must obtain a lawful source fixture and an independently approved reference image exported from the authoring application or another verified renderer, using the **same composition, camera and expected output resolution**.

Keep the original input and approved oracle image under the local fixture directory. Add a sample entry:

```json
{
  "file": "real-model.step",
  "sourceApp": "CAD authoring application",
  "sourceVersion": "Actual version and export settings",
  "oracle": {
    "image": "real-model-reference.png",
    "sha256": "REPLACE_WITH_ACTUAL_64_CHARACTER_SHA256_HEX",
    "reviewedBy": "Named human reviewer / QA team",
    "maxMeanAbsoluteError": 12.0
  }
}
```

The SHA must match the actual reviewed image. Do not copy the placeholder. To generate it locally:
```powershell
python -c "import hashlib,pathlib; p=pathlib.Path('tests/fixtures/real-model-reference.png'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

The output and oracle must have exactly the same dimensions. The audit resamples both to 96×96 RGB and computes mean absolute channel difference. This detects wrong or blank visual output even if a JPEG has many colors. It is **a useful automated mismatch gate, not complete visual proof**: reviewers must still assess camera, geometry, text, clipping, material fidelity and image semantics. Fix a tolerance before running the audit; do not raise it after a failure without an independently justified change.

## Commands
For the existing nine bundled fixtures (smoke/inventory evidence):
```powershell
python scripts/audit_renderer_matrix.py --verify-fixtures
```

For a local subset with independently approved oracles:
```powershell
python scripts/audit_renderer_matrix.py --manifest path/to/oracles.json --fixtures-dir path/to/fixtures --verify-fixtures --require-oracles --report renderer-matrix-local.json
```

Full release certification:
```powershell
python scripts/audit_renderer_matrix.py --strict --timeout 60
```

`--strict` requires both all advertised previewable extensions with actual renderable fixtures **and** independent passing oracle evidence for each present sample. It should fail on the current nine-fixture manifest: do not weaken the gate to report 100% without licensed samples and native acceptance runs.

## Trust and safety limits
- Manifests and oracle paths must remain fixture-local single basenames. The oracle file's SHA-256 is pinned. Image size is restricted to 16 million pixels.
- Every execution uses the isolated renderer subprocess, bounded time and a temporary output directory. The report records source SHA-256 preservation, output dimensions, distinct colors, reviewer/version, oracle matching status and numeric error. It does not publish source artwork.
- This is a **source-level** audit; real Windows WebView2, macOS Cocoa, Linux WebKit and *packaged* native CAD/library compatibility must also be checked.
- Current 47-extension inventory includes formats that only expose embedded thumbnails rather than native editable geometry. Fidelity expectations must reflect each capability's documented mode.

**Status**: implementation and unit tests authored, no real proprietary/CAD oracle fixture evidence supplied or signed off. Do not close #60 solely due to this PR.

## Fail-closed follow-up
An empty manifest cannot pass `--require-oracles`. If a source file disappears between inventory and actual isolated rendering, the tool records `missing_fixture`, `sourcePreserved=false`, and the exception type instead of crashing and losing the audit report. Oracle thresholds are capped at a 32-channel-value mean absolute error to prevent a meaningless `255` threshold from treating unrelated images as approved. This is still not a substitute for human geometry and texture checks.
