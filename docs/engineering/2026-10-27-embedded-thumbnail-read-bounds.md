# Oversized embedded thumbnail reads: 3ds Max OLE and DWG

Date: 27 October 2026. This targeted follow-up was identified in live source review after the nine issues from the user's older audit had been remediated.

## Finding

- The 3ds Max OLE thumbnail reader called `ole.openstream(...).read()` on user-controlled OLE streams, even though the project defines `MAX_EMBEDDED_THUMBNAIL_BYTES = 64 MiB`. `olefile.openstream` may materialize the stream in memory before `read()` is called, so a post-read size check is not sufficient.
- The DWG directory parser used untrusted signed `img_size` when reading embedded BMP or PNG payloads. A file with a very large, valid-looking extent could cause a large allocation before the image decoder enforced pixel limits.

## Fix

- Query OLE directory `get_size` **before** opening a candidate stream, skip over-limit streams, and also use `read(limit+1)` as a second boundary.
- Reject nonpositive/oversized DWG image sizes before seeking/reading or constructing image buffers. Preserve permitted small PNG/BMP thumbnails.
- Add unit tests for oversized OLE stream not opened, bounded OLE read requests, sparse oversized DWG directory rejection, and successful small DWG PNG extraction.

## Remaining validation and limits

These checks are source-level defenses, not a guarantee that arbitrary OLE/AutoCAD files are safe. The wider `MAX_SOURCE_FILE_BYTES`, Pillow image-pixel caps, child-process resource ceilings, native source read grants, cancellation and actual packaged Windows/Linux/macOS security tests are still required. Source inputs from non-native pickers must not bypass `DesktopApi` authorization.

```bash
python -m pytest tests/unit/test_embedded_thumbnail_read_bounds.py -q
python scripts/check_release_locally.py --mode full
```

No GitHub Actions were manually dispatched and no native packaged runtime evidence was collected in this PR. Keep release acceptance issues #22 and #59 open.
