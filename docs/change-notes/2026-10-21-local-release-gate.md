# Local QA gate with zero GitHub Actions minutes — 2026-10-21

## Purpose
The project's hosted Actions allowance is exhausted. Multiple substantial PRs (#15 through #35) have been merged or are under review without a complete local frontend/backend/native test record. Do not describe skipped CI as a passed test.

## One-command checks
From the repository root on **Windows, macOS or Linux**, in a Python venv with project dependencies installed and with the supported Node/npm available:

```console
python scripts/check_release_locally.py
```

Default `--mode core` runs, sequentially:
1. `python -m ruff check .` — repository Python lint.
2. `python -m pytest tests/unit -m core -q` — marked core unit regressions.
3. `npm run typecheck` from `frontend/`.
4. `npm test` from `frontend/`.
5. `npm run build` from `frontend/`.
6. `PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE=1 python -m pytest tests/frontend/test_bundle.py -q` — shipping HTML/CSP checks. The environment variable is passed only to this one subprocess and is cross-platform.

Each command prints directly to the local terminal. The result is written to **`local-check-report.json`** (gitignored). The JSON records only command name, arguments, exit code and duration, plus OS/Python and counts. It never captures artwork, rendered assets, file listings, or terminal output, and does not upload data.

## Options
- `python scripts/check_release_locally.py --mode full` runs the entire Python test suite and checks mandatory renderer engines with `scripts/verify_environment.py`. It also builds/tests the frontend. It does *not* build signed installers.
- `--backend-only` or `--frontend-only` narrows the scope.
- `--fail-fast` stops on first failure (default gathers all failures).
- `--npm-ci` explicitly opts into a local `npm ci` run that may access the network. **No dependency installation is performed by default.** If `frontend/node_modules` is absent, install it locally first, or use this flag.
- `--report C:\\temp\\previewgen-qa.json` sets the report path; quotes may be needed for paths with spaces.

## Not covered by a passing local report
- Windows (WebView2) frozen idle behavior or dialog responsiveness.
- macOS Cocoa/GTK/Qt native file picker and shortcut behavior.
- Installer upgrade/repair/uninstall, resource/code signing, notarization, release checksums and Gatekeeper/SmartScreen.
- Stress testing real 3D formats, ZIP bombs, 100k+ assets, blocked permissions and long-running batch cancellation on actual hardware.
- Windows 100/125/150/200% DPI; keyboard screen-reader, high-contrast and reduced-motion accessibility.

Use `scripts/windows_idle_health.py`, the packaging checklist in issue #22, and native platform evidence separately. Do not merge a feature into a public release solely because this source gate reports PASS.

## Change isolation
No workflow files are modified. The script does not call GitHub, make remote API requests, or attempt to activate Actions; the commit uses `[skip ci]`. Tests mock subprocess invocation and verify the ordered plan, safe defaults, bundle env and exit/report semantics.

## Review checklist
- [ ] Run the Python planner unit tests: `python -m pytest tests/unit/test_local_release_gate.py -q`.
- [ ] Run core, frontend-only and full modes in prepared local environments.
- [ ] Verify the report contains no sensitive data.
- [ ] Complete native and packaged acceptance gates before release.
