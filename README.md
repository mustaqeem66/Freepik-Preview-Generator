# PreviewGen

**The Automated Batch Preview Studio for Marketplace Contributors & Digital Artists.**  
Transform folders of transparent **2D assets (PNG, WebP, SVG, TIFF, PSD)**, **3D models (GLB, GLTF, OBJ, STL, PLY, BLEND)**, and **CAD drawings/solids (DXF, DWG, MAX, F3D, MB, STEP, IGES)** into marketplace-compliant, split-diagonal JPG previews in seconds.

---

## 🎯 The Purpose: Why We Built PreviewGen

Selling digital assets on top marketplaces like **Freepik, Adobe Stock, Shutterstock, Creative Market, Envato, and Etsy** is a high-volume business. However, digital asset platforms have a strict requirement:

> **Every transparent asset (PNG, PSD, 3D model, or CAD drawing) must be accompanied by a high-resolution JPG preview that clearly proves transparency to potential buyers before they purchase.**

### The Pain Points We Solve

| The Pain Point | How Designers Handled It Before | How PreviewGen Solves It |
|---|---|---|
| ⏳ **Extreme Time Waste** | Manually opening Photoshop, drawing diagonal masks, generating checkerboards, pasting text badges, and saving one file at a time. | **1-Click Batch Processing**: Queue a whole folder with live per-file progress. Throughput depends on format, resolution and hardware; benchmark your own library before quoting a rate. |
| ❌ **Marketplace Rejections** | Rejections from reviewers because the preview didn't clearly communicate transparency or lacked a standard split. | **Strict Marketplace Compliance**: Standard diagonal split (checkerboard transparency vs. solid background) approved by reviewers. |
| 🔒 **Privacy & Cloud Leaks** | Uploading unreleased, proprietary art to sketchy "free online converter" websites that steal or scrape artwork. | **100% Local & Offline**: Your files never leave your computer. Complete privacy and zero data leakage. |
| 🔍 **Distortion & Cropping** | Batch scripts that accidentally stretch, crop, trim padding, or decimate complex 3D meshes (like vehicle wheels). | **Zero Distortion Guarantee**: Original alpha channel, dimensions, and pristine 3D vertices/normals are preserved with zero decimation. |
| 🎨 **Ugly / Generic Watermarks** | Bland or unreadable watermarks locked to rigid corners that obscure critical artwork details. | **Full Customization Studio**: Custom brand logo upload, custom font file upload (`.ttf`, `.otf`), outline strokes, and continuous freeform X/Y position sliders. |
| 🛠️ **Missing 3D & CAD Software** | Unable to preview `.blend`, `.dwg`, `.max`, or `.f3d` files on computers without Blender, AutoCAD, or 3ds Max installed. | **Zero-Dependency Native Extraction**: Extracts embedded scene renders and converts CAD solids directly in pure Python without needing host software. |

---

## 👥 Who Is This For?

- **Stock Marketplace Contributors** (Freepik, Adobe Stock, Shutterstock, 123RF, Dreamstime)
- **Freelance Illustrators & Vector Artists** preparing asset packs for commercial clients
- **Icon & UI/UX Designers** exporting hundreds of transparent components for showcase
- **3D Artists & Game Asset Creators** packaging transparent character renders, props, and textures
- **CAD Engineers & Industrial Designers** generating previews for AutoCAD drawings, SolidWorks parts, and 3D prints
- **Creative Studios & Agencies** looking to automate repetitive post-production export workflows

---

## 💡 Why You Should Use PreviewGen

1. **Reclaim Hours of Your Week**: Stop doing repetitive monkey-work in Photoshop. Load your folder, click one button, and let the background worker handle thousands of assets while you focus on creating art.
2. **Increase Submission Approval Rates**: Reviewers on platforms like Freepik accept submissions faster when previews follow the industry-standard diagonal split convention.
3. **Studio-Grade Control**: Whether your brand uses pure white, off-white, light gray, or dark solid backgrounds, customize colors with the interactive palette and instant live preview.
4. **Responsive Native Desktop UI**: An asynchronous background renderer keeps the bridge usable during large batches. Preview and 3D-orbit smoothness depend on model complexity, output size and GPU; no fixed frame rate is guaranteed.

---

## ⚡ Install PreviewGen

On Windows, the standard setup wizard lets you choose the installation folder and optional Desktop shortcut. The portable ZIP does not open an installation wizard.

### 🪟 Windows (PowerShell)
Open PowerShell and run:
```powershell
irm https://raw.githubusercontent.com/Mustaqeem66/Freepik-Preview-Generator/main/install.ps1 | iex
```
- Downloads `PreviewGen-Setup.exe` from the latest published GitHub release, or the release specified by `PREVIEWGEN_VERSION`.
- Requires `SHA256SUMS.txt` and verifies the downloaded installer before launching it.
- Opens the Inno Setup wizard for destination choice, Start Menu integration, an optional Desktop shortcut, uninstallation and optional launch.
- Code-signing reputation and Windows SmartScreen warnings are separate from checksum verification.
- Review downloaded scripts before executing them in PowerShell.

### 🍎 macOS (Terminal)
Open **Terminal** and run:
```bash
curl -fsSL https://raw.githubusercontent.com/Mustaqeem66/Freepik-Preview-Generator/main/install.sh | bash
```
- Installs directly to `/Applications/PreviewGen.app`
- Strips Apple Gatekeeper quarantine (`xattr -cr`) to bypass the "Unidentified Developer" block
- Creates a **Desktop Shortcut** (`~/Desktop/PreviewGen`)
- Launches PreviewGen automatically

---

### 🐧 Linux (Terminal)
Open your terminal and run:
```bash
curl -fsSL https://raw.githubusercontent.com/Mustaqeem66/Freepik-Preview-Generator/main/install.sh | bash
```
- Installs standalone AppImage to `~/.local/bin/previewgen`
- Configures permissions (`chmod +x`) and installs system icon
- Registers desktop entry (`previewgen.desktop`) and creates **Desktop Shortcut**
- Launches PreviewGen automatically

---

## 📦 Alternative: Manual Download (GitHub Releases)

Prefer downloading manually?
1. Visit the [**Latest Releases**](https://github.com/Mustaqeem66/Freepik-Preview-Generator/releases/latest).
2. Download your platform package:
   - **Windows (Installer Wizard)**: `PreviewGen-Setup.exe` — Complete setup wizard with License Agreement, custom directory picker, and Desktop icon checkbox.
   - **Windows (Portable)**: `PreviewGen-Windows.zip` — Extract and double-click `Install-Desktop-Icon.bat`.
   - **macOS**: `PreviewGen-macOS.dmg` — Open DMG, drag to Applications, run `xattr -cr /Applications/PreviewGen.app` if prompted.
   - **Linux**: `PreviewGen-Linux.AppImage` — Run `chmod +x PreviewGen-Linux.AppImage` and double-click.

---

## 📖 How to Use PreviewGen (Step-by-Step Guide)

PreviewGen makes bulk preview creation effortless in 6 simple steps:

```
 1. Select Folder ──► 2. Browse Files ──► 3. Adjust 3D Angle ──► 4. Add Brand Logo ──► 5. Pick Colors ──► 6. Batch Export!
    (or ZIP file)       (◀ Prev / Next ▶)   (Orbit 360° View)      (Freeform Sliders)     (Diagonal Split)     (1-Click JPGs)
```

1. **Select Input Folder (or ZIP Archive)**:
   - Click **Browse…** in panel `1 · Folders` or paste your folder path directly into the input box and press Enter!
   - 💡 **Best Practice (Clean Batches)**: For consistent branding and maximum speed, organize your files into dedicated folders containing **one type of asset at a time** (e.g. one folder with all your `.png` cutouts, another folder with `.psd` files, and another with your `.glb`/`.obj` 3D models). This ensures 3D camera angles and watermark settings remain perfectly calibrated for the entire batch.
   - Use the **`◀ Prev`** and **`Next ▶`** buttons in the toolbar (or press **Left/Right Arrow keys** on your keyboard) to preview any asset in your folder instantly.
3. **Rotate 3D Models & CAD Solids in Full 360°**:
   - Click and drag your mouse directly on the preview image to orbit the model in 360°.
   - Or click an angle preset like **Isometric (3/4)**, **Front**, **Side**, **Top**, or **Back**.
4. **Add Brand Watermarks (Logo, Text, or Both)**:
   - Upload your logo image (`.png`, `.svg`, `.ico`) and adjust **Scale** and **Opacity**.
   - Upload custom brand fonts (`.ttf`, `.otf`, `.woff`) for watermark text.
   - Use the **X** and **Y** position sliders to place your logo and watermark text at any exact percentage coordinate on the canvas.
5. **Choose Split Direction & Background Color**:
   - Choose whether the solid color sits on the Left or Right half.
   - Click the color swatch or choose a preset (White, Off-White, Light Gray, Dark).
6. **Click "Generate All JPG Previews"**:
   - The asynchronous worker processes files in the background without freezing the UI.
   - Optionally enable **Desktop notifications** in Settings to receive an OS notification when a batch finishes (off by default; requires system notification permission).
   - Once finished, click **Open Output Folder** to inspect your ready-to-upload marketplace JPG previews!

---


## 🚀 Key Features

### 1. Multi-Format 2D Ingestion (PNG, WebP, SVG, TIFF, PSD)
- **PNG**: Pixel-perfect alpha compositing with zero canvas crop or distortion.
- **WebP**: Full support for modern web & mobile transparent assets, with animated WebP keyframe fallback.
- **SVG Vector**: Smooth vector rasterization with exact dimension preservation using high-performance `resvg`.
- **TIFF / TIF**: High-bit-depth cutouts with Pillow's built-in CMYK/YCbCr to RGB conversion. Embedded ICC profile management is not performed.
- **PSD (Photoshop)**: Headless composite layer extraction directly from Photoshop binaries via `psd-tools` — no Adobe software required!

### 2. Full 360° 3D Model Studio (GLB, GLTF, OBJ, STL, PLY, BLEND)
- **360° Interactive Orbit**: Click and drag your mouse directly on the preview image to rotate 3D models from any angle in real-time.
- **Zero-Distortion Mesh Rendering**: Complex geometries (such as car models, thin vehicle panels, wheels, and interior parts) preserve their exact vertices, normals, and submesh transforms without destructive mesh decimation.
- **Zero-Dependency .blend Previews**: Extracts embedded preview renders directly from `.blend` file headers in pure Python—no need to install Blender!
- **Studio Angle Presets**: 1-click presets for **Isometric 3/4**, **Front**, **Side**, **Top**, and **Back** views with sliding pill animations.
- **Fine-Grained Controls**: Sliders for horizontal **Yaw (0°–360°)** and vertical **Pitch (-85° to +85°)** with two-sided directional lighting.

### 3. CAD & Engineering Formats (DXF, DWG, MAX, F3D, MB, STEP, IGES)
- **AutoCAD DXF (`.dxf`)**: Vector path & geometry rasterization via `ezdxf` with automatic line drawing transparency conversion.
- **AutoCAD DWG (`.dwg`)**: Pure Python binary header extraction of embedded BMP/PNG thumbnail sections without needing AutoCAD.
- **Autodesk 3ds Max (`.max`)**: OLE Structured Storage thumbnail extraction via `olefile`—reads the embedded viewport render.
- **Autodesk Fusion 360 (`.f3d`)**: Native archive decompression extracting pre-rendered high-res thumbnails.
- **Autodesk Maya (`.mb`, `.ma`)**: Header IFF / base64 swatch parser extracting viewport preview chunks.
- **Universal Solids (`.step`, `.stp`, `.iges`, `.igs`)**: Converts B-Rep engineering solids directly into 3D meshes for 360° interactive orbit!

### 4. Custom Brand Logo & Icon Overlay
- **Upload Any Logo**: Upload brand watermarks (`.png`, `.webp`, `.svg`, `.ico`).
- **Independent Sizing & Opacity**: Scale logos from 20% to 250% and adjust opacity from 10% to 100%.
- **Freeform Position Sliders**: Position logos and text anywhere with continuous horizontal (X: 0–100%) and vertical (Y: 0–100%) offset sliders.
- **Dual Branding**: Run logo only, text watermark only, or display both concurrently.

### 5. Bounded ZIP Member Extraction & Auto-Cleanup
- **One-Level Member Traversal**: Scans supported files inside folder levels within a `.zip`; nested `.zip` archives are not expanded recursively.
- **Zip-Slip and Resource Limits**: Rejects escaping paths and enforces member, size, depth and timeout budgets.
- **Metadata Rejection**: Skips `__MACOSX`, `.DS_Store`, `._*` AppleDouble files, and `Thumbs.db`.
- **Path-Collision Protection**: Automatically prefixes folder slugs (e.g. `archive_assets_vectors_icon.jpg`) if duplicate file names exist across different subfolders.
- **Safe Auto-Cleanup**: Automatically deletes all temporary unzipped artifacts immediately upon completion across Windows, macOS, and Linux.

### 6. Diagonal Split Backgrounds
- **Two Equal-Area Triangles**: Cuts the canvas from corner to corner.
- **Directional Flip**: Choose between *Left Solid / Right Transparent* or *Left Transparent / Right Solid*.
- **Interactive Color Palette**: Pick any custom hex color or select from one-click presets (White, Off-White, Light Gray, Dark).

### 7. Typography, Custom Fonts & Outline Engine
- **Custom Font Upload**: Click **Browse Font File…** to load any `.ttf`, `.otf`, or `.woff` font file from your PC and render watermarks in your exact brand typography.
- **Customizable Label**: Defaults to `100% TRANSPARENT`, or enter your own custom text (or leave blank).
- **Outer Outline / Stroke**: Toggleable stroke with custom color and thickness (Thin, Normal, Medium, Thick, Extra Bold) so text remains readable over any image.
- **Live Sliders**: Real-time Font Scale (50% to 180%) and Text Opacity (10% to 100%).

---

## 📸 App Preview & Visual Showcase

### Light Mode (graphite-neutral `#ececef` surface with `#f7f7f9` cards)
<p align="center">
  <img src="preview-light.png" alt="PreviewGen Light Mode Interface" width="850">
</p>

### Dark Mode (`#161618` surface with `#202023` panels)
<p align="center">
  <img src="preview-dark.png" alt="PreviewGen Dark Mode Interface" width="850">
</p>

---

## 💻 Developer Quickstart (Run from Source)

CI builds with **Python 3.12.8** and **Node.js 24.15.0** (see `.github/workflows/build.yml`).

```bash
# Clone the repository
git clone https://github.com/Mustaqeem66/Freepik-Preview-Generator.git
cd Freepik-Preview-Generator

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate

# Install dependencies
# Reproducible, hash-pinned install (recommended, byte-for-byte reproducible builds):
pip install --require-hashes -r requirements-lock.txt
# Or, for development/build work (adds pytest, ruff, pyinstaller at pinned versions):
# pip install --require-hashes -r requirements-dev-lock.txt
# Loose top-level spec (resolves to the latest matching versions):
# pip install -r requirements.txt

# Run Desktop Studio (pywebview + React + Vite)
python app.py

# Or run with Python launcher
python main.py
```

### ✅ Verifying a build (reproducible audit)

Prove every advertised format works on a given machine with one command (no
frozen build required):

```bash
# 1. Confirm all mandatory renderer engines resolve (raster, SVG, PSD, 3D, DXF, STEP, text)
python scripts/verify_environment.py

# 2. Run the full Python suite (add PREVIEWGEN_REQUIRE_FRONTEND_BUNDLE=1 to require the React bundle)
python -m pytest tests/ -v

# 3. Render every deterministic fixture through the real renderer stack
python app.py --render-test-all --fixtures tests/fixtures
```

Notes for independent audits:

- The **frontend** gate is Node 24.15.0: `cd frontend && npm ci && npm run typecheck && npm test && npm run build`.
  `npm ci` must finish before `vitest`/`vite` exist; a time-limited sandbox should allow it to complete.
- The **packaged gate** (`tests/integration/test_release_renderers_gate.py`) exercises the frozen
  binary when `PREVIEWGEN_BINARY` points at a built `dist/PreviewGen/PreviewGen[.exe]` and
  `PREVIEWGEN_RELEASE_GATE=1` is set; otherwise those tests skip.
- `scripts/verify_environment.py` reports which optional engines (`olefile`, `pypdfium2`, `brotli`)
  are missing; only the mandatory engines block a release.

---

## 📜 Licensing Terms

PreviewGen operates under a **Dual-Licensing Model**:

### 🟢 Free for Personal & Non-Commercial Use
PreviewGen is **100% free** for personal evaluation, educational purposes, hobby projects, and non-profit use. You can download, run, and experiment with the application at zero cost.

### 💼 Paid License Required for Commercial Use
If you use PreviewGen to produce previews for:
- Assets sold or monetized on stock platforms (Freepik, Adobe Stock, Shutterstock, Creative Market, Etsy, Envato, etc.)
- Client deliverables, freelance design projects, or agency production
- Commercial products, studios, or enterprise workflows

👉 **A commercial license is required.**

To acquire a commercial license, request volume seats, or discuss enterprise terms, please contact:
- **Email**: [zenartisan66@gmail.com](mailto:zenartisan66@gmail.com)
- **Subject**: `PreviewGen Commercial License Inquiry`

---

## 🤝 Sponsorships & Partnerships

Are you a design agency, marketplace vendor, or tool developer interested in supporting PreviewGen, requesting custom integrations, or featuring your brand?

We welcome sponsors and partners! Get in touch directly:
- **Email**: [zenartisan66@gmail.com](mailto:zenartisan66@gmail.com)
- **Subject**: `PreviewGen Sponsorship / Partnership`

---

## 👤 Author

Created with care by **[Mustaqeem66](https://github.com/Mustaqeem66)** (ZenArtisan).  
If PreviewGen saves you time, please give the repository a **⭐ Star** on GitHub!
