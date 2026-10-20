# PreviewGen Studio

**Local-first desktop software for creating diagonal-split JPG previews from creative assets.**

PreviewGen scans a folder, displays supported artwork, lets you adjust the split background, text/logo watermark and (where applicable) 3D camera, and generates JPGs with a batch report. It uses **Python + pywebview** for desktop integration and **React + TypeScript** for the interface.

> **Release status (October 2026):** The latest published installer is **v2.1.1**. The `main` branch contains subsequent development changes with source version `2.1.2`. A successful development test does **not** mean the GitHub Release includes those changes. For a reproducible report, always include the exact EXE version or commit.

![PreviewGen Studio dark theme](preview-dark.png)

## Features at a glance

- **Batch export:** choose a source folder, select an output location, configure appearance, then generate JPG previews. Reports record successes, failures, skips and relevant safety limits.
- **Live preview:** select an asset in the library to inspect the output before exporting.
- **Background and branding:** solid/transparent-looking diagonal split, color presets, text, outline and optional logo/font.
- **3D controls:** camera presets, yaw/pitch and orbit controls where the renderer supports them.
- **Local processing:** inputs are handled locally; image previews are served only over a tokenized `127.0.0.1` endpoint. The app does not require uploading artwork to a remote conversion service.
- **Reliability safeguards:** bounded discovery, cancellable work, isolated rendering, error reports, output overwrite policy and per-operation event IDs.
- **Optional desktop notifications:** disabled by default and subject to your operating system's notification permissions.

**File-format note:** Discovery recognizes more formats than every installation can necessarily render with full fidelity. Some native design/CAD formats rely on embedded thumbnails rather than converting editable project content. See [Format support](#format-support-and-limitations).

## Install

Download the appropriate package from [the latest GitHub Release](https://github.com/mustaqeem66/Freepik-Preview-Generator/releases/latest).

| Platform / package | What happens | Install location / shortcut |
| --- | --- | --- |
| Windows `PreviewGen-Setup.exe` | Inno Setup wizard | Choose the destination; Start Menu entry and optional Desktop icon |
| Windows `PreviewGen-Windows.zip` | Portable application | Extract before running `PreviewGen.exe`; no setup wizard |
| macOS `PreviewGen-macOS.dmg` | macOS app disk image | Drag `PreviewGen.app` to Applications |
| Linux `PreviewGen-Linux.AppImage` | Standalone AppImage | Make executable; desktop integration depends on your environment |

### Windows PowerShell setup

The optional script downloads the **latest published** `PreviewGen-Setup.exe`, checks its SHA-256 against the release manifest and opens the **interactive** installer:

```powershell
irm https://raw.githubusercontent.com/mustaqeem66/Freepik-Preview-Generator/main/install.ps1 | iex
```

Review [install.ps1](install.ps1) before executing downloaded scripts. The installer **does not automatically update** when a new commit lands on `main`. To install a specific published tag, set `PREVIEWGEN_VERSION` before running the script.

**Wizard versus portable:** Double-clicking the `PreviewGen.exe` inside the ZIP launches the app directly. It is *not* supposed to show an installation wizard. Download `PreviewGen-Setup.exe` if you want a selectable destination and normal uninstaller.

Windows may show a SmartScreen publisher warning for unsigned or unrecognized builds. A SHA-256 match protects against download corruption but does not establish publisher identity. Never bypass OS protections without checking the source and release provenance.

On macOS/Linux, review [install.sh](install.sh) before using the optional terminal installer.

## First-run workflow

1. Click **Choose Input Folder** and select the folder containing your source files. You can also paste a folder path. **The native folder-selection dialog intentionally hides individual files**; selecting a folder initiates discovery inside it.
2. Wait for the **Assets** library to populate. If the scan finds nothing, check the folder contents and file formats; if it stops at a safety limit or is cancelled, the results may be partial.
3. Select an asset and adjust its **Background**, **Watermark** and any available **3D camera** options.
4. In **Destination**, optionally choose **Same as input** or use a dedicated output folder.
5. Choose the overwrite behavior and export dimensions, then use **Generate Previews** (batch) or single-file export.
6. Use **Open Output Folder** to inspect JPGs and the batch report. A JPG has an opaque background: the checkerboard visualization is printed, not actual JPG transparency.

The input and output selectors are **folder** pickers, not individual multi-file pickers. Direct file selection and drag-and-drop are planned, not currently implemented.

## Format support and limitations

The configured discovery extensions are:

| Group | Extensions | Important qualification |
| --- | --- | --- |
| Raster/layered | `.png`, `.webp`, `.tif`, `.tiff`, `.psd` | Layered/composite and color handling vary by source |
| Vector | `.svg`, `.svgz`, `.ai`, `.eps` | Some formats require a usable embedded preview or renderer support |
| 3D | `.glb`, `.gltf`, `.obj`, `.stl`, `.ply`, `.3mf`, `.dae`, `.blend` | Models may exceed memory/geometry limits; native project files may expose thumbnails only |
| CAD / design | `.dxf`, `.dwg`, `.max`, `.f3d`, `.mb`, `.ma`, `.step`, `.stp`, `.iges`, `.igs` | CAD conversion and embedded-thumbnail extraction differ by format |
| Creator/font | `.procreate`, `.brush`, `.brushset`, `.clip`, `.kra`, `.afdesign`, `.afphoto`, `.afpub`, `.indd`, `.abr`, `.ttf`, `.otf`, `.woff`, `.woff2` | Not every asset has a visually meaningful standalone preview |
| Archives | `.zip` | Bounded member extraction, depth, size and time limits |

Files that are encrypted, malformed, unsupported by the specific renderer or beyond resource limits can fail individually. Do not treat a scan listing an extension as proof every source of that type will render.

## Troubleshooting

### Windows says “PreviewGen (Not Responding)”

A faded window and “Not Responding” in the title bar mean Windows believes the desktop window is **not processing messages**. This cannot be diagnosed from a screenshot alone. An unresponsive native WebView2 window, blocking filesystem activity, modal system dialog, renderer failure or a graphics-driver problem can look similar.

**Before force-closing the app:**

1. Wait briefly, especially if selecting a large/network folder, opening a picker, or ending a batch. Note whether the issue occurs **at launch**, **while idle**, **after opening a folder**, **during preview**, or **on exit**.
2. If the interface still responds, click **Diagnostics** in the toolbar. Otherwise open `%LOCALAPPDATA%\PreviewGen\logs` in File Explorer and inspect `previewgen.log`.
3. Search for `HANG DIAGNOSTIC`, `WATCHDOG`, `ERROR` and traceback messages. Newer source builds probe the Windows message pump even while idle and record Python stacks after repeated timeouts. These logs establish **where Python threads were**, not necessarily the cause of a native WebView2 hang.
4. Check Windows Event Viewer → Windows Logs → Application for an associated crash or hang event. Check whether the **Microsoft Edge WebView2 Runtime** is installed and functioning.
5. Retry after restarting the app, then test a small local folder of PNGs. Record your Windows version, GPU, app version and exact steps.

If the app is fully frozen, Task Manager → **Details** → right-click `PreviewGen.exe` → **Create memory dump file** may help native debugging. **Do not post dumps publicly**: they may contain artwork, full file paths, tokens or personal data. Redact identifying paths in logs too. Open a GitHub issue with non-sensitive steps and a redacted excerpt.

This repository includes a *diagnostic watchdog*, not an automatic hang cure. Reproducing the Windows freeze and inspecting the resulting traces are still required to confirm the native root cause.

### Folder dialog says “No items match your search”

That is expected if the current directory contains only files: **Choose Input Folder** displays subfolders, not individual images. Select the folder itself using **Select Folder**; the asset list is scanned afterward.

### No supported assets found

Check the selected path, file extensions, access permissions and whether the scan ended partially. Files hidden inside unsupported or encrypted containers may not be discoverable.

### Setup does not appear

Use **`PreviewGen-Setup.exe`**, not the `PreviewGen.exe` extracted from the portable ZIP. Check the installer filename, release tag and Windows security dialogs.

### Batch or renderer errors

Review the output report and `previewgen.log`. Try a single small asset of the same format, then compare results. Limits exist to protect the machine from oversized or malformed input.

## Run from source

Development versions use **Python 3.12.8** and **Node.js 24.15.0** in CI.

```bash
git clone https://github.com/mustaqeem66/Freepik-Preview-Generator.git
cd Freepik-Preview-Generator
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev-lock.txt

cd frontend
npm ci
npm run typecheck
npm test
npm run build
cd ..

python app.py
```

**Checks used by pull-request CI:**

```bash
python -m ruff check .
python -m pytest tests/ -q
cd frontend && npm run typecheck && npm test && npm run build
```

Additional renderer/environment checks (dependent on system libraries and fixture availability):

```bash
python scripts/verify_environment.py
python app.py --render-test-all --fixtures tests/fixtures
```

To make release binaries, use the checked-in workflows; a frontend unit test or Linux build is not proof that the Windows installer, native dialogs and WebView2 message loop work on a clean Windows VM. Release-signing and notarization credentials are needed for official tagged builds.

## Architecture

```text
React UI / TypeScript
    ↕ typed pywebview bridge + operation IDs
DesktopApi (Python)
    ├── ScannerService — bounded discovery
    ├── PreviewCoordinator / ProbeCoordinator — isolated workers
    ├── LifecycleManager — batch cancellation / orderly shutdown
    ├── PreviewFileServer — tokenized loopback JPEG delivery
    ├── Settings — validated, locally stored preferences
    └── UI watchdog — diagnostic-only native responsiveness checks
```

Design direction and outstanding work are tracked in [Premium UI/UX Plan](docs/PREMIUM_UI_UX_PLAN.md) and [Remediation TODO](docs/REMEDIATION_TODO.md). Further priorities: actual multi-file import, resizable panes, searchable thumbnails, explicit renderer capability results, Windows UI scaling tests, and measured performance.

## Screenshots

| Light theme | Dark theme |
| --- | --- |
| ![PreviewGen light theme](preview-light.png) | ![PreviewGen dark theme](preview-dark.png) |

## Privacy and security

PreviewGen is designed for local processing. It stores settings, temporary previews, logs and output files on the user's machine. The preview server listens on loopback; there is no artwork upload step in the standard workflow. Native OS notifications are optional. You are responsible for reviewing files and redacting logs/dumps before sharing them.

Please report security issues privately as described in [SECURITY.md](SECURITY.md). See [LICENSE](LICENSE) for the MIT license.

## Contributions and support

Pull requests should include tests, a reason for the change and a note about Windows/macOS/Linux behavior. Use [GitHub Issues](https://github.com/mustaqeem66/Freepik-Preview-Generator/issues) for reproducible non-sensitive defects and feature requests.

Maintained by [Mustaqeem66](https://github.com/mustaqeem66). Feedback and contributions are welcome.
