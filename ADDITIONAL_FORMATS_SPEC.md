# PreviewGen: Additional Formats Technical Specification
**Document Version:** 2.0  
**Status:** Architectural Blueprint & Research Specification  
**Scope:** Adobe Creative Suite (`.ai`, `.eps`, `.indd`, `.abr`), Procreate (`.procreate`, `.brush`, `.brushset`), Clip Studio Paint (`.clip`), Affinity Suite (`.afdesign`, `.afphoto`, `.afpub`), Krita (`.kra`), Typography Fonts (`.ttf`, `.otf`, `.woff`, `.woff2`), and Audio Waveforms (`.wav`, `.mp3`).

---

## 1. Executive Summary & Market Context

Digital marketplace creators (selling on **Freepik**, **Creative Market**, **Adobe Stock**, **Shutterstock**, **Envato Elements**, **Etsy**, and **Creative Fabrica**) submit multi-software product packages. A single marketplace bundle frequently includes:
1. **Vector Artwork**: `.ai` (Illustrator native) and `.eps` (standard stock vector requirement).
2. **Digital Art & Painting**: `.procreate` (iPad illustration), `.clip` (Clip Studio Paint manga/anime), `.kra` (Krita).
3. **Creator Presets & Brushes**: `.brushset` / `.brush` (Procreate brushes), `.abr` (Photoshop brushes).
4. **Desktop Publishing**: `.indd` (Adobe InDesign brochures, flyers, book layouts).
5. **Modern Vector Alternatives**: `.afdesign` and `.afphoto` (Affinity Designer / Photo).
6. **Typography**: `.ttf`, `.otf`, `.woff`, `.woff2` (Font design packages).

### The Invariable PreviewGen Contract
Every format adapter—regardless of whether it parses an SQLite database, decompresses an OASIS ZIP container, rasterizes a PDF stream, or renders font glyphs—must produce an identical in-memory **`PIL.Image.Image (mode="RGBA")`** buffer. Downstream compositing, diagonal triangle splitting, live canvas rotation, and watermark stamping remain 100% unified and deterministic.

---

## 2. Format Feasibility & Dependency Matrix

| Category | File Extension | Software Origin | Underlying Binary Structure | Python Extraction Strategy | New Dependencies Needed | Feasibility Rating |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **Vectors** | `.ai` | Adobe Illustrator | PDF-1.4/1.5 dual-stream (CS2–CC 2026) | Render page 1 vector stream via `pypdfium2` (Apache-2.0) | `pypdfium2` (lightweight, wheels for all OS) | **9.5 / 10** |
| **Vectors** | `.eps` | Universal PostScript | PostScript Level 2/3 with 30-byte DOS EPS header or ASCII XMP packet | Extract embedded binary TIFF thumbnail (bytes 20–27) or XMP `<xmpGImg:image>` | **None** (Pillow + pure Python header slice) | **9.0 / 10** |
| **Illustration** | `.procreate` | Procreate (iPad) | Standard ZIP container with binary plist & layer tiles | Extract `QuickLook/Thumbnail.png` directly from ZIP in memory | **None** (Standard library `zipfile`) | **10 / 10** |
| **Illustration** | `.brush`, `.brushset` | Procreate Brushes | Nested ZIP archives containing `shape.png`, `grain.png`, and `QuickLook/Thumbnail.png` | Extract brush tip thumbnail or shape mask and composite specimen | **None** (Standard library `zipfile`) | **10 / 10** |
| **Manga / Anime** | `.clip` | Clip Studio Paint | Standard SQLite 3 database (`SQLite format 3\x00`) | Query `SELECT ImageData FROM CanvasPreview LIMIT 1;` | **None** (Standard library `sqlite3`) | **10 / 10** |
| **Open Source Art**| `.kra` | Krita Painting | OASIS OpenDocument ZIP archive | Extract `mergedimage.png` (full-res flattened composite) or `preview.png` | **None** (Standard library `zipfile`) | **10 / 10** |
| **Affinity Suite** | `.afdesign`, `.afphoto`, `.afpub` | Serif Affinity 1, 2, 3 | Proprietary Serif block container with embedded PNG preview chunk | Scan file header for `\x89PNG\r\n\x1a\n` ... `IEND\xaeB`\x82` slice | **None** (Standard library byte slicing) | **9.0 / 10** |
| **Layout** | `.indd` | Adobe InDesign | OLE compound file with XMP packet | Extract `<xmpGImg:image>` base64-encoded JPEG thumbnail chunk | **None** (Pure Python regex / XML parse) | **8.5 / 10** |
| **Presets** | `.abr` | Adobe Photoshop Brushes | Binary chunk structure (v1/v2 RLE PackBits or v6+ 8BIM `sampled_brushes`) | Parse 8BIM brush tip alpha masks to PIL grayscale stamp | **None** (Pure Python PackBits decoder) | **8.0 / 10** |
| **Typography** | `.ttf`, `.otf` | TrueType / OpenType | SFNT font tables (`cmap`, `glyf`, `CFF `) | Render alphabet & pangram specimen card using FreeType | **None** (Pillow `ImageFont.truetype`) | **9.5 / 10** |
| **Web Typography**| `.woff`, `.woff2` | Web Open Font Format | WOFF zlib / WOFF2 Brotli compressed SFNT font container | Decompress WOFF container to TTF bytes using `fonttools` / `brotli` | `brotli` (for WOFF2) | **8.5 / 10** |

---

## 3. Deep Architectural Analysis by Format

### 3.1. Adobe Illustrator (`.ai`)
* **Underlying Anatomy**:
  Since Adobe Illustrator 9.0 (and universally across CS, CC, and modern 2026 releases), `.ai` files are saved with the default **"Create PDF Compatible File"** setting. This generates a dual-stream format: the file is literally a valid PDF document enclosing an encrypted private Illustrator dictionary in the trailer.
* **Extraction Strategy**:
  1. Inspect the first 1024 bytes. If `%PDF-` is present (typically starting at byte 0), instantiate `pypdfium2.PdfDocument(source_path)`.
  2. Select `page = doc[0]` (page 1 is the primary artwork canvas).
  3. Render page at requested target dimensions (e.g., $2400 \times 2400$ for batch export, $850 \text{px}$ for live UI preview) with a transparent background (`render(scale=..., fill_color=None)`).
  4. Convert the rendered raw bitmap buffer to `PIL.Image.Image (mode="RGBA")`.
* **Fallback Strategy (PDF-uncompressed or legacy AI 8 and older)**:
  If the file lacks `%PDF-` at the header:
  - Search for the embedded XMP metadata block (`<?xpacket begin=...?>`).
  - Extract the `<xmpGImg:image>` tag containing a base64-encoded JPEG composite preview.
* **Licensing & Dependencies**:
  - `pypdfium2` is released under the liberal **Apache-2.0 / BSD-3-Clause** license (Chromium PDFium engine). It provides pre-compiled, self-contained manylinux, macOS, and Windows wheels without requiring system poppler or ghostscript installations.

---

### 3.2. Encapsulated PostScript (`.eps`)
* **Underlying Anatomy**:
  EPS files generated for stock marketplaces (Freepik, Shutterstock) follow the Adobe DOS EPS binary format or ASCII PostScript DSC 3.0:
  - **DOS EPS Binary Header** (first 30 bytes):
    - Bytes `0..3`: Magic signature `\xC5\xD0\xD3\xC6` (`0xC6D3D0C5`).
    - Bytes `4..7`: PostScript code start offset (little-endian unsigned 32-bit int).
    - Bytes `8..11`: PostScript code length.
    - Bytes `20..23`: **TIFF thumbnail start offset**.
    - Bytes `24..27`: **TIFF thumbnail byte length**.
* **Extraction Strategy (Fast Path — 0 Dependencies)**:
  1. Read the first 30 bytes. If magic matches `0xC6D3D0C5`, read `tiff_offset = uint32(bytes[20:24])` and `tiff_len = uint32(bytes[24:28])`.
  2. If `tiff_offset > 0` and `tiff_len > 0`:
     - Slice `tiff_bytes = file_bytes[tiff_offset : tiff_offset + tiff_len]`.
     - Open directly using Pillow: `Image.open(io.BytesIO(tiff_bytes)).convert("RGBA")`.
     - Execution time: **$0.001\text{s}$**, zero memory allocation overhead.
  3. If ASCII EPS (starts with `%!PS-Adobe-3.0 EPSF-3.0`):
     - Scan for `%%BeginPhotoshop` or `%%BeginXMLPacket` containing `<xmpGImg:image>`. Decode base64 JPEG thumbnail.
* **Vector Fallback Path**:
  If no embedded TIFF or XMP thumbnail is present, pass to Pillow's native EPS loader (`Image.open(file_path)`), which reads the `%%BoundingBox:` header.

---

### 3.3. Procreate (`.procreate`)
* **Underlying Anatomy**:
  A `.procreate` file is a standard PKZip archive containing:
  - `Document.archive`: Apple binary plist containing canvas dimensions, DPI, orientation, and color profile.
  - `QuickLook/Thumbnail.png`: High-resolution, full-color rendered composite of the canvas generated by the iPad Procreate engine on save.
  - Layer subdirectories with LZO-compressed BGRA tile data.
* **Extraction Strategy**:
  1. Open via `zipfile.ZipFile(source_path, "r")`.
  2. Locate `QuickLook/Thumbnail.png` (or case-insensitive variations).
  3. Read file stream:
     ```python
     with zipfile.ZipFile(source_path, "r") as zf:
         with zf.open("QuickLook/Thumbnail.png") as thumb_stream:
             img = Image.open(thumb_stream).convert("RGBA")
     ```
  4. Execution time: **$0.002\text{s}$**, memory overhead $<5\text{MB}$.
  5. Dependencies: **Zero** (standard library `zipfile` + Pillow).

---

### 3.4. Procreate Brushes (`.brush` and `.brushset`)
* **Underlying Anatomy**:
  - `.brushset` is a ZIP container containing multiple `.brush` files.
  - Each `.brush` file is a ZIP container containing:
    - `QuickLook/Thumbnail.png`: Rendered stroke preview showing how the brush paints.
    - `shape.png`: Grayscale alpha mask of the brush tip.
    - `grain.png`: Texture grain pattern.
* **Extraction Strategy**:
  1. For `.brush`: Extract `QuickLook/Thumbnail.png` directly. If absent, load `shape.png`, invert if necessary, and render an aesthetic brush tip preview stamp on transparent RGBA.
  2. For `.brushset`: Extract the first 4 to 8 brush thumbnails and tile them into a preview sheet or render the representative lead brush.
  3. Dependencies: **Zero** (standard library `zipfile` + Pillow).

---

### 3.5. Clip Studio Paint (`.clip`)
* **Underlying Anatomy**:
  Clip Studio Paint documents (the dominant software format for manga, comics, and anime character art) are stored in an **SQLite 3 database container**.
  - File header bytes 0–15: `SQLite format 3\x00`.
  - Database Table `CanvasPreview`:
    - Column `ImageData`: Raw binary BLOB containing the pre-rendered PNG or JPEG preview.
    - Column `ImageWidth`: Integer canvas width.
    - Column `ImageHeight`: Integer canvas height.
* **Extraction Strategy**:
  ```python
  import sqlite3, io
  from PIL import Image

  with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as conn:
      cur = conn.cursor()
      cur.execute("SELECT ImageData FROM CanvasPreview LIMIT 1;")
      row = cur.fetchone()
      if row and row[0]:
          img = Image.open(io.BytesIO(row[0])).convert("RGBA")
  ```
* Performance: **$0.003\text{s}$**, completely safe read-only URI connection, zero disk extraction.
* Dependencies: **Zero** (standard library `sqlite3` + Pillow).

---

### 3.6. Krita Digital Painting (`.kra`)
* **Underlying Anatomy**:
  Krita files are structured under the OASIS OpenDocument standard packaged inside a ZIP file:
  - `mergedimage.png`: Full-resolution, 100% flattened composite of all visible layers.
  - `preview.png`: $256 \times 256$ thumbnail image.
* **Extraction Strategy**:
  ```python
  with zipfile.ZipFile(source_path, "r") as zf:
      # Prefer full-resolution flattened composite for high-res 4K marketplace exports
      member = "mergedimage.png" if "mergedimage.png" in zf.namelist() else "preview.png"
      with zf.open(member) as stream:
          img = Image.open(stream).convert("RGBA")
  ```
* Dependencies: **Zero** (standard library `zipfile` + Pillow).

---

### 3.7. Affinity Suite (`.afdesign`, `.afphoto`, `.afpub`)
* **Underlying Anatomy**:
  Serif Affinity 1 & 2 files store a serialized scene graph accompanied by an uncompressed, embedded full-resolution PNG preview chunk saved near the front of the document stream to support macOS QuickLook and Windows thumbnail handlers.
* **Extraction Strategy**:
  1. Open binary stream in read mode.
  2. Search for the standard PNG 8-byte signature: `\x89PNG\r\n\x1a\n`.
  3. Scan through PNG chunks (`IHDR`, `IDAT`, etc.) until reaching `IEND\xaeB`\x82`.
  4. Slice the extracted PNG byte buffer directly into Pillow.
  5. Dependencies: **Zero** (standard library binary slicing + Pillow).

---

### 3.8. Adobe InDesign (`.indd`)
* **Underlying Anatomy**:
  InDesign layout documents are compound binary files containing an embedded Adobe XMP metadata packet that holds an XML description of the layout and an encoded thumbnail of the first spread.
* **Extraction Strategy**:
  1. Open file and read in blocks (XMP packet is typically situated within the first $256\text{ KB}$ or at the file footer).
  2. Extract `<xmpGImg:image>` contents (Base64-encoded JPEG stream).
  3. Decode base64 bytes into `io.BytesIO` and open with Pillow.
  4. Dependencies: **Zero** (pure Python string/regex parsing + standard library `base64`).

---

### 3.9. Photoshop Brushes (`.abr`)
* **Underlying Anatomy**:
  Photoshop ABR files use big-endian binary tagged chunks:
  - Version 1 & 2: Legacy format containing brush count and a sequence of PackBits RLE-compressed 8-bit grayscale bitmaps.
  - Version 6+: Modern 8BIM container containing tagged blocks with `sampled_brushes`. Each brush record contains bounding box coordinates, depth (8-bit or 16-bit), and uncompressed or PackBits RLE bitmap bytes.
* **Extraction Strategy**:
  1. Parse ABR header and identify the largest brush tip mask in the brushset.
  2. Decompress the PackBits RLE grayscale byte stream into an 8-bit `L` image.
  3. Convert to RGBA where the grayscale brightness becomes the alpha channel (`mask = tip; img = Image.new("RGBA", tip.size, (50, 50, 50, 255)); img.putalpha(mask)`).
  4. Dependencies: **Zero** (pure Python binary parsing + Pillow).

---

### 3.10. Typography Fonts (`.ttf`, `.otf`, `.woff`, `.woff2`)
* **Underlying Anatomy**:
  Unlike image files which have existing pixel buffers, fonts are vector glyph definition tables (`glyf`, `CFF `, `cmap`).
* **Generation Strategy (The "Font Specimen Card")**:
  1. For `.ttf` and `.otf`: Pillow's `ImageFont.truetype(source_path, size=...)` loads and renders glyphs using Pillow's native FreeType engine.
  2. For `.woff2`: Use `brotli` to decompress the WOFF2 table directory into standard TTF/OTF bytes in memory.
  3. Render a clean **Typography Specimen Card** ($2400 \times 2400 \text{px}$):
     - **Header**: Font family name and format badge (`OTF` / `TTF`).
     - **Uppercase Alphabet**: `A B C D E F G H I J K L M N O P Q R S T U V W X Y Z`
     - **Lowercase Alphabet**: `a b c d e f g h i j k l m n o p q r s t u v w x y z`
     - **Numerals & Symbols**: `0 1 2 3 4 5 6 7 8 9 & ? ! @ # $ % *`
     - **Pangram Display**: *"The quick brown fox jumps over the lazy dog"* rendered at $96\text{pt}$.
  4. Composite the specimen card over the signature PreviewGen diagonal background.

---

### 3.11. Audio Packs & Music Loops (`.wav`, `.mp3`)
* **Underlying Anatomy**:
  Marketplace sound creators on AudioJungle, Envato, and Freepik sell sound effects, Foley packs, and ambient loops.
* **Generation Strategy (The "Waveform Visualizer Card")**:
  1. Read audio samples using standard library `wave` (for `.wav`) or lightweight stream header parsers.
  2. Calculate root-mean-square (RMS) energy or peak amplitudes across 120 discrete horizontal bins.
  3. Draw an aesthetic, modern sound wave bar graph (mirrored vertical bars with rounded caps) in the brand accent color with duration badge and audio metadata.
  4. Composite over the diagonal triangle background.

---

## 4. Architectural Integration & Pipeline Flow

```
                                [ Incoming File Stream ]
                                            │
               ┌────────────────────────────┼───────────────────────────┐
               ▼                            ▼                           ▼
     [ 0-Dependency Adapters ]   [ Stream Render Adapters ]   [ Specimen Generators ]
       • .procreate, .brush        • .ai (pypdfium2 PDFium)      • .ttf, .otf, .woff
       • .clip (SQLite3)           • .eps (Pillow EPS/TIFF)      • .abr (Brush Stamp)
       • .kra (Krita ZIP)                                        • .wav (Waveform Engine)
       • .afdesign, .afphoto                                                │
       • .indd (XMP Packet)                                                 │
               │                            │                               │
               └────────────────────────────┼───────────────────────────────┘
                                            ▼
                             [ Standardized PIL.Image (RGBA) ]
                                            │
                                            ▼
                              [ Diagonal Triangle Split ]
                             (Left Solid / Right Checkerboard)
                                            │
                                            ▼
                              [ Live Watermark & Branding ]
                               (Custom Logo, Font, Offset)
                                            │
                                            ▼
                              [ High-Resolution .jpg Output ]
```

---

## 5. Security & Resource Bounding Specifications

Every newly added format adapter must adhere to PreviewGen's hardened resource bounds:

1. **ZIP Bomb & Infinite Expansion Protection** (`.procreate`, `.brush`, `.kra`):
   - Check `zipfile.ZipInfo.file_size` before opening any member.
   - Restrict single member decompression to $\le 250\text{ MB}$.
   - Reject archives with compression ratios exceeding $100:1$.
2. **SQLite Connection Safety** (`.clip`):
   - Always open in read-only mode using URI parameters (`file:... ?mode=ro`).
   - Query exclusively from `CanvasPreview` table with `LIMIT 1`.
   - Never execute DDL or transaction commands.
3. **Buffer Slicing Safety** (`.afdesign`, `.indd`, `.eps`):
   - Cap header scan buffers to the first $2\text{ MB}$ of the file to prevent unbounded memory scanning on 10GB raw files.
4. **PDF Engine Sandboxing** (`.ai`):
   - Render page 1 only (`doc[0]`).
   - Set strict pixel dimension limits ($\le 10{,}000 \times 10{,}000\text{px}$).

---

## 6. Implementation Phasing & Roadmap

* **Phase 1: Zero-Dependency Instant Wins** (Estimated footprint: 0 new libraries):
  - `.procreate` (Procreate canvas composite)
  - `.brush` / `.brushset` (Procreate brush stamps)
  - `.clip` (Clip Studio Paint canvas preview)
  - `.kra` (Krita full-resolution composite)
  - `.afdesign`, `.afphoto`, `.afpub` (Affinity embedded PNG chunk)
* **Phase 2: Adobe Vector Giants** (Stock marketplace essentials):
  - `.ai` (Adobe Illustrator PDFium adapter)
  - `.eps` (DOS EPS 30-byte header TIFF slice & XMP thumbnail fallback)
* **Phase 3: Creator Presets & Typography**:
  - `.ttf`, `.otf`, `.woff` (Font specimen card generator)
  - `.indd` (InDesign spread thumbnail)
  - `.abr` (Photoshop brush tip stamp)

---

## 7. Approval & Sign-Off

This document constitutes the formal architectural baseline for PreviewGen's Phase 2 format expansion. Once approved, implementation will proceed without altering existing PNG, PSD, SVG, 3D, and CAD pipelines.
