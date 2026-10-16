from pathlib import Path
import sys
import tempfile
import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from processor import PreviewConfig, process_folder, generate_file


def test_preview_config_from_mapping_strictness():
    """Verify PreviewConfig.from_mapping rejects dangerous inputs and clamps values safely."""
    # Boolean string handling: "false" must not evaluate to True
    cfg = PreviewConfig.from_mapping({"invertTriangles": "false"})
    assert cfg.invert_triangles is False

    cfg_true = PreviewConfig.from_mapping({"invertTriangles": "true"})
    assert cfg_true.invert_triangles is True

    # Non-finite floats: NaN and Inf must safely fall back to defaults
    cfg_nan = PreviewConfig.from_mapping({"opacity": float("nan"), "fontScale": float("inf")})
    assert 0.0 <= cfg_nan.opacity <= 1.0
    assert 0.2 <= cfg_nan.font_scale <= 3.0

    # Text length bounding (capped to 100 characters)
    huge_text = "A" * 500
    cfg_text = PreviewConfig.from_mapping({"text": huge_text})
    assert len(cfg_text.text) == 100

    # Overwrite policies
    assert PreviewConfig.from_mapping({"overwritePolicy": "skip"}).overwrite_policy == "skip"
    assert PreviewConfig.from_mapping({"overwritePolicy": "rename"}).overwrite_policy == "rename"
    assert PreviewConfig.from_mapping({"overwritePolicy": "invalid"}).overwrite_policy == "rename"

    # Strict-export mode vs preview mode
    # 1. Preview mode is forgiving
    cfg_prev = PreviewConfig.from_mapping({"textColor": "not-a-color"}, mode="preview")
    assert cfg_prev.text_color == (255, 255, 255)

    # 2. Strict export mode rejects invalid colors, out-of-range floats, and unknown keys
    with pytest.raises(ValueError, match="Unknown configuration key"):
        PreviewConfig.from_mapping({"bogusKey": 123}, mode="strict-export")

    with pytest.raises(ValueError, match="Invalid color specification"):
        PreviewConfig.from_mapping({"textColor": "not-a-color"}, mode="strict-export")

    with pytest.raises(ValueError, match="Value for opacity out of bounds"):
        PreviewConfig.from_mapping({"opacity": 150}, mode="strict-export")

def test_batch_collision_resolution_and_overwrite_policies():
    """Verify deterministic collision looping and overwrite policies (skip, rename, overwrite)."""
    with tempfile.TemporaryDirectory() as tmp_in, tempfile.TemporaryDirectory() as tmp_out:
        in_dir = Path(tmp_in)
        out_dir = Path(tmp_out)

        # Create 2 source images with identical stems in different subfolders
        sub1 = in_dir / "sub1"
        sub2 = in_dir / "sub2"
        sub1.mkdir()
        sub2.mkdir()

        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        img.save(sub1 / "asset.png")
        img.save(sub2 / "asset.png")

        # First run: default overwrite policy
        cfg = PreviewConfig.from_mapping({"overwritePolicy": "overwrite"})
        summary = process_folder(
            in_dir,
            out_dir,
            cfg,
            progress=lambda c, t, s: None,
            is_cancelled=lambda: False,
        )

        assert summary["success"] == 2
        assert summary["failed"] == 0
        assert summary["planned"] == 2
        assert summary["duration"] >= 0.0
        assert (out_dir / "sub1_asset.jpg").is_file()
        assert (out_dir / "sub2_asset.jpg").is_file()

        # Second run: "skip" policy
        cfg_skip = PreviewConfig.from_mapping({"overwritePolicy": "skip"})
        summary_skip = process_folder(
            in_dir,
            out_dir,
            cfg_skip,
            progress=lambda c, t, s: None,
            is_cancelled=lambda: False,
        )

        assert summary_skip["skipped"] == 2
        assert summary_skip["success"] == 0

        # Third run: "rename" policy
        cfg_rename = PreviewConfig.from_mapping({"overwritePolicy": "rename"})
        summary_rename = process_folder(
            in_dir,
            out_dir,
            cfg_rename,
            progress=lambda c, t, s: None,
            is_cancelled=lambda: False,
        )

        assert summary_rename["success"] == 2
        assert (out_dir / "sub1_asset_copy1.jpg").is_file()
        assert (out_dir / "sub2_asset_copy1.jpg").is_file()
        # Verify consistent batch accounting: processed = success + failed + skipped
        assert summary_rename["processed"] == summary_rename["success"] + summary_rename["failed"] + summary_rename["skipped"]
        assert summary_rename["remaining"] == 0


def test_cancellation_checkpoints_during_file_generation():
    """Verify cancellation checkpoint interrupts generate_file immediately."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        src = tmp / "test.png"
        out = tmp / "test.jpg"

        img = Image.new("RGBA", (100, 100), (0, 255, 0, 255))
        img.save(src)

        # Pre-cancelled checkpoint must stop immediately
        with pytest.raises(RuntimeError, match="Cancelled before rendering"):
            generate_file(src, out, is_cancelled=lambda: True)

        assert not out.exists()
