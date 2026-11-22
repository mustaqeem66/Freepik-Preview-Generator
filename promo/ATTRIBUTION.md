# Promo asset attribution

The promotional video in this folder is rendered from `src/promo.html`. Every
visual is computed from a single time value `t`, so the same source always
produces the same frames.

## Fonts

| File | Family | Source | License |
| --- | --- | --- | --- |
| `public/fonts/bricolage.woff2` | Bricolage Grotesque | [Google Fonts](https://fonts.google.com/specimen/Bricolage+Grotesque) | SIL Open Font License 1.1 |
| `public/fonts/instrument-serif.woff2` | Instrument Serif | [Google Fonts](https://fonts.google.com/specimen/Instrument+Serif) | SIL Open Font License 1.1 |
| `public/fonts/dm-sans.woff2` | DM Sans | [Google Fonts](https://fonts.google.com/specimen/DM+Sans) | SIL Open Font License 1.1 |

## Preview images

`public/assets/` holds real exports produced by PreviewGen itself from the
synthetic 3D forms rendered in `tests/fixtures/`. Each pair is a transparent
WebP source and the JPG that PreviewGen exported from it, which is what the
promo shows in the card cluster and in the diagonal-split product shot.

The artwork is original to this repository and carries the same license as the
rest of the project.

## Rendering

```bash
cd promo
npm ci
npm run build
```

`render.mjs` drives headless Chromium through Playwright and writes one PNG per
frame into `out/frames/`. `encode.mjs` turns those frames into the MP4, the
animated WebP that the README plays, and the poster still.

Set `FRAMES` to render a subset, for example `FRAMES=0,150,300 npm run render`.
Set `CHROME_PATH` if Playwright's bundled Chromium is not at the default path.
