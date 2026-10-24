import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from previewgen.probe_process import probe_asset_isolated

pytestmark = pytest.mark.core


def test_probe_asset_isolated_reports_native_raster_size(tmp_path):
    src = tmp_path / "art.png"
    Image.new("RGB", (321, 123), (1, 2, 3)).save(src)

    result = probe_asset_isolated(src)

    assert result["kind"] == "raster"
    assert result["nativeWidth"] == 321
    assert result["nativeHeight"] == 123


def test_probe_asset_isolated_fails_closed_on_uninspectable_asset(tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"this is not a real png")

    with pytest.raises(RuntimeError):
        probe_asset_isolated(bad)


def test_probe_asset_isolated_closes_queue_when_start_fails(monkeypatch):
    """A failed spawn must not leak the probe result queue."""
    closed: list[str] = []

    class FakeQueue:
        def close(self) -> None:
            closed.append("close")

        def join_thread(self) -> None:
            closed.append("join_thread")

    class FailingProcess:
        pid = None

        def start(self) -> None:
            raise OSError("cannot start process")

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float | None = None) -> None:
            pass

    import previewgen.probe_process as probe_process

    monkeypatch.setattr(probe_process.mp, "Queue", FakeQueue)
    monkeypatch.setattr(probe_process.mp, "Process", lambda **_kwargs: FailingProcess())

    with pytest.raises(OSError, match="cannot start process"):
        probe_asset_isolated(Path("artwork.png"))

    assert "close" in closed
    assert "join_thread" in closed
