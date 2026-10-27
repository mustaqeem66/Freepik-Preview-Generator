# Freepik Preview Generator — verified re-audit remediation

27 October 2026 • Source baseline: `cefa8b20e2658304711a3b4c1bbd277ea82d3bca` • Target: `main`

This ledger reconciles the nine source-level findings supplied in the audit. Findings were checked against source code, not claimed reproduced on all frozen desktop binaries.

| # | Finding | Source disposition | Pull request |
|---|---|---|---|
| 1 | Changing untextured model color does not re-render | Add missing React effect dependency and regression | #95 |
| 2 | Local Windows installer omits 3D runtime collection | Include collada, lxml, networkx and enforce manifest parity | #95 |
| 3 | Environment verification underreports renderer engines | Match release gate; include fontTools; correct DXF description | #95 |
| 4 | ZIP-sourced mesh cache keyed by new temp path each job | Key by canonical archive/member identity and filesystem fingerprint, scoped per job | #98 |
| 5 | Missing Krita image and unbounded nested brush ZIP | Explicit missing-preview diagnostics; validate nested brush directory before decoding | #96–97 |
| 6 | Maya .ma thumbnail scanner consumes unbounded lines | Bounded ASCII prefix scanning and multiple quoted base64 chunks | #96–97 |
| 7 | Multi-node scene visuals flattened too late | Normalize each scene component before concatenate, including CAD scenes | #96–97 |
| 8 | Folder instructions encourage forbidden path pasting | Native picker-only placeholder, help instructions and UI tests | #95 |
| 9 | Dead Help component; UI cannot select supported watermark presets | Delete intentionally unmounted diagnostics UI; wire watermark preset through schema, preview, batch and Inspector | Follow-up PR |

## Product scope, not misrepresented as completed fixes

- The full 47-extension fidelity matrix still needs expanded real files with provenance and true on-device oracle evidence.
- Textured UV/PBR shading is **not** fully implemented by per-node color normalization; the software painter still approximates materials.
- Proprietary formats without embedded thumbnails remain conditional, not guaranteed renderable.
- True z-buffer, custom text fitting, contact sheets, brand presets, tiled watermarking, and auto-framing are separate product enhancements and should get independent design/proof gates. No release claim for these is made here.

## Validation required before shipping

1. Verify the branch HEADs and merge conflicts after each PR. Re-run the local Python core and integration suites, and frontend typecheck/test/build.
2. Build on Windows from `build_windows.bat`, test `.dae`, `.3mf`, `.step`, `.kra`, `.brushset`, `.ma` and ZIP-contained orbit rendering.
3. Verify both native file grants and read-only source fields remain protected.
4. Compare 3D orbit latency and cache hit counts at fixed source SHA, and exercise cancellation/temp cleanup.
5. Independently test watermark presets in both live preview and batch output, Windows/Linux/macOS; retain screenshots/artifacts.
6. Release gate #22 (signed native artifacts) and renderer oracle issue #60 remain separate outstanding acceptance tracks until evidence is collected.

**Status language:** PR created/merged is not equivalent to native binary verification. The engineer who runs the operating-system tests should record command, OS, artifact SHA, fixtures and failures.
