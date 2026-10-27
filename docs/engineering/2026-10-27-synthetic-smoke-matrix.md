# Synthetic renderer smoke matrix (not a visual fidelity oracle)

The bundled manifest contains 12 samples for 11 distinct extensions. Additional deterministic parser smoke inputs can be generated locally to exercise at least 25 distinct direct-preview extensions **without** committing binary files or shipping third-party artwork.

```bash
python scripts/generate_synthetic_renderer_matrix.py --output-dir local-fixtures
python scripts/audit_renderer_matrix.py --manifest local-fixtures/renderer-samples.json --fixtures-dir local-fixtures --verify-fixtures --report local-fixtures/result.json
python -m pytest tests/unit/test_synthetic_renderer_matrix.py -q
```

**Scope:** the generator copies the checked-in samples unchanged and creates raster variants, SVGZ, simple triangle meshes/glTF, and minimal ZIP/XMP/ABR/AI-PDF containers. The generated examples are explicitly labelled `PreviewGen deterministic synthetic smoke`. Some are deliberately simplified format probes, not native files exported by Autodesk, Adobe, Krita, Procreate or InDesign. Rendering can still fail on clean machines with missing optional decoders; that failure is useful evidence.

**Never self-certify:** the tool does not generate trusted reference images, never supplies an `oracle` object, and cannot make `--strict` succeed while catalog coverage or independently approved visual oracles are absent. Keep [renderer oracle issue #60](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/60) open until lawfully sourced real authoring-app/version files, human-reviewed reference PNGs, hashes, native packaged runtimes and accurate layout comparisons exist.

The output directory is explicit and may be discarded after local checks. The script refuses to overwrite the repository's committed fixture directory. It pins ZIP and PDF metadata timestamps for reproducibility.
