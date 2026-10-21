# Renderer audit integrity hardening — 2026-10-22

The existing strict renderer audit could report its registry/fixture coverage as complete without running any renderers when invoked with `--strict` alone. Strict now **implies real isolated fixture verification**; inventory-only mode remains intentionally lightweight. A renderer that deletes or makes a source inaccessible during a failed render previously caused the audit's `finally` block to raise, preventing the JSON evidence report from being written. The audit now records `source_modified` and a typed integrity error, and continues auditing subsequent samples.

Tests cover both cases. No real proprietary-format assets or screenshots were supplied, so this does not certify DWG/Maya/Blender/STEP fidelity. Keep issue #60 open pending versioned samples, independent oracle scoring, and native runtime checks.

Local commands: `python -m pytest tests/unit/test_renderer_capability_matrix.py -q`; `python scripts/audit_renderer_matrix.py --verify-fixtures`; `python scripts/audit_renderer_matrix.py --strict`. The strict command is expected to fail until full fixture coverage is obtained. No hosted GitHub Actions or local suite runs were performed in this source-only authoring session.
