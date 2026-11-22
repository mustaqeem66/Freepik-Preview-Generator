# Format logo attribution

The marks in this folder identify the applications whose file formats
PreviewGen reads. They are used nominatively — to show which software authored
a supported format — and do not imply sponsorship or endorsement by any of
these vendors. Each mark remains the property of its respective owner.

## Sources

| File | Application | Source | Terms |
| --- | --- | --- | --- |
| `adobe-photoshop.svg` | Photoshop | [Devicon — photoshop-original](https://github.com/devicons/devicon/blob/master/icons/photoshop/photoshop-original.svg) | MIT (collection), vendor trademark |
| `adobe-illustrator.svg` | Illustrator | [Devicon — illustrator-original](https://github.com/devicons/devicon/blob/master/icons/illustrator/illustrator-original.svg) | MIT (collection), vendor trademark |
| `adobe-indesign.svg` | InDesign | [gilbarbara/logos — adobe-indesign](https://github.com/gilbarbara/logos/blob/master/logos/adobe-indesign.svg) | Original mark belongs to Adobe; refer to the upstream asset for terms |
| `blender.svg` | Blender | [Devicon — blender-original](https://github.com/devicons/devicon/blob/master/icons/blender/blender-original.svg) | MIT (collection), vendor trademark |
| `autodesk-maya.svg` | Maya | [Devicon — maya-original](https://github.com/devicons/devicon/blob/master/icons/maya/maya-original.svg) | MIT (collection), vendor trademark |
| `autodesk-3ds-max.svg` | 3ds Max | [Wikimedia Commons — Autodesk 3ds Max Logo](https://commons.wikimedia.org/wiki/File:Autodesk_3ds_Max_Logo.svg) | Public domain, Autodesk Inc. |
| `autodesk-fusion-360.svg` | Fusion 360 | [Devicon — fusion-original](https://github.com/devicons/devicon/blob/master/icons/fusion/fusion-original.svg) | MIT (collection), vendor trademark |
| `autodesk-autocad.svg` | AutoCAD | [Wikimedia Commons — Autodesk AutoCAD Logo](https://commons.wikimedia.org/wiki/File:Autodesk_AutoCAD_Logo.svg) | Public domain, Autodesk Inc. |
| `krita.svg` | Krita | [Wikimedia Commons — Calligrakrita-base](https://commons.wikimedia.org/wiki/File:Calligrakrita-base.svg) | CC BY-SA 4.0, Wolthera van Hövell tot Westerflier and Timothée Giet for KDE |
| `inkscape.svg` | Inkscape | [Devicon — inkscape-original](https://github.com/devicons/devicon/blob/master/icons/inkscape/inkscape-original.svg) | MIT (collection), vendor trademark |
| `clip-studio-paint.png` | Clip Studio Paint | [Wikimedia Commons — Clip Studio Paint app logo](https://commons.wikimedia.org/wiki/File:Clipstudiopaint_app_logo.png) | Public domain, Celsys, Inc. |
| `procreate.webp` | Procreate | [Apple App Store listing](https://apps.apple.com/us/app/procreate/id425073498?uo=4) | Publisher-provided artwork; trademark and icon artwork remain the property of the owner |
| `affinity-designer.svg` | Affinity Designer | [Wikimedia Commons — Affinity Designer V2 icon](https://commons.wikimedia.org/wiki/File:Affinity_Designer_V2_icon.svg) | Public domain, Serif Europe — classic standalone Affinity V2 product icon |
| `affinity-photo.svg` | Affinity Photo | [Wikimedia Commons — Affinity Photo V2 icon](https://commons.wikimedia.org/wiki/File:Affinity_Photo_V2_icon.svg) | Public domain, Serif Europe — classic standalone Affinity V2 product icon |
| `affinity-publisher.svg` | Affinity Publisher | [Wikimedia Commons — Affinity Publisher V2 icon](https://commons.wikimedia.org/wiki/File:Affinity_Publisher_V2_icon.svg) | Public domain, Serif Europe — classic standalone Affinity V2 product icon |
| `gltf.svg` | glTF | [Simple Icons](https://simpleicons.org/) via [Iconify `simple-icons`](https://icon-sets.iconify.design/simple-icons/) | CC0-1.0 |
| `google-fonts.svg` | Google Fonts | [Simple Icons](https://simpleicons.org/) via [Iconify `simple-icons`](https://icon-sets.iconify.design/simple-icons/) | CC0-1.0 |
| `google.svg` | Google | [Iconify `logos`](https://icon-sets.iconify.design/logos/) (`google-icon`) | CC0-1.0 |
| `microsoft-windows.svg` | Windows | [Iconify `logos`](https://icon-sets.iconify.design/logos/) (`microsoft-windows`) | CC0-1.0 |
| `zip.svg` | ZIP archive | [Iconify `solar`](https://icon-sets.iconify.design/solar/) (`file-zip-bold`) | MIT (collection) |

Simple Icons, Devicon and Iconify are collections of third-party vendor marks.
Their own licenses cover the collections; the individual marks remain the
property of their respective owners and are used here for identification only.

## Notes

- The application marks are the real product icons, not stand-ins or
  re-drawn approximations.
- Every SVG is normalised to `width="24" height="24"` so the marks scale
  consistently in the README tables. Source `viewBox` values are preserved.
- `krita.svg` had no `viewBox` in its source; a `0 0 1024 1024` viewBox was
  added to match its declared 1024×1024 user-space geometry. This is a
  rendering fix only — the artwork is unmodified.
- The two raster marks are rendered at `width="24" height="24"` in the README
  with HTML `<img>` tags, because Markdown image syntax cannot size an image
  and the SVGs above size themselves from their own `width` and `height`.
- `procreate.webp` had its flat `#242424` backing plate removed by a border
  flood fill, so only the brush mark carries pixels. The removal was verified
  pixel-by-pixel: every pixel of the mark itself is byte-identical to the
  source. The result was then cropped to the mark's bounding box so it fills
  its cell like the other marks.
- Marks sourced from Iconify and Simple Icons use `fill="currentColor"`, which
  renders in the reader's text colour and stays legible on both the light and
  dark GitHub README themes.
