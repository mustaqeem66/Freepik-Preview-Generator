# Renderer oracle provenance guard — evidence versus synthetic smoke

**Issue:** [#60](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues/60)

The deterministic 25+ format generator is useful for parser/packaging smoke tests, but its files are deliberately *not* real exports from Adobe, Autodesk, Procreate, etc. Until now, simply inserting an `oracle` object with a checksum, threshold and reviewer was enough to make the audit **attempt** a fidelity certification, even when the manifest itself openly labeled the input `PreviewGen deterministic synthetic`.

This PR rejects clearly synthetic or PreviewGen-authored `sourceApp`, unknown/blank authoring apps, synthetic `sourceVersion`, and an `oracle.image` that is the *same basename* as the tested source. The existing positive ExampleCAD/Design QA unit fixture is preserved. These checks are **supplementary guardrails**, not proof of a genuinely independent source: a falsified external application name or reviewer can still pass the metadata parser. A human must inspect application provenance, exact source version, licensing, and independently approved reference images.

There is **no change** to ordinary no-oracle smoke fixtures, the 46-extension registry, decode timeouts, or existing 0–32 RGB mean-error range. The strict gate should continue to fail until all genuine versioned samples are certified.

### Local tests

```bash
python -m pytest tests/unit/test_renderer_oracle_fidelity.py tests/unit/test_synthetic_renderer_matrix.py -q
python -m ruff check scripts/audit_renderer_matrix.py tests/unit/test_renderer_oracle_fidelity.py
python scripts/check_release_locally.py --mode full
```

The change does **not** claim a real format, native build, or release passed. Hosted GitHub Actions were not manually invoked.
