"""Single-export renderers must participate in lifecycle shutdown."""

from __future__ import annotations

import pytest
from PIL import Image

from previewgen import api as api_module
from previewgen.api import DesktopApi

pytestmark = pytest.mark.core


def test_single_export_registers_and_retires_its_renderer_pid(tmp_path, monkeypatch):
    source = tmp_path / "asset.png"
    Image.new("RGB", (16, 16), "red").save(source)
    api = DesktopApi()
    api._add_authorized_input_folder(tmp_path)
    observed: dict[str, object] = {}

    def _fake_render(source_path, output_path, config, timeout_seconds=60.0, **kwargs):
        observed["started"] = kwargs.get("on_process_started")
        observed["finished"] = kwargs.get("on_process_finished")
        kwargs["on_process_started"](4321)
        Image.new("RGB", (16, 16), "blue").save(output_path)
        kwargs["on_process_finished"](4321, set())

    monkeypatch.setattr(api_module, "render_file_isolated", _fake_render)

    result = api.export_preview(str(source), {"outputFolder": str(tmp_path)})

    assert result["ok"] is True
    assert callable(observed["started"])
    assert callable(observed["finished"])


def test_single_probe_registers_and_retires_its_worker_pid(tmp_path, monkeypatch):
    source = tmp_path / "asset.png"
    Image.new("RGB", (16, 16), "red").save(source)
    api = DesktopApi()
    api._add_authorized_input_folder(tmp_path)
    observed: dict[str, object] = {}

    def _fake_probe(source_path, timeout_seconds=15.0, **kwargs):
        observed["started"] = kwargs.get("on_process_started")
        observed["finished"] = kwargs.get("on_process_finished")
        kwargs["on_process_started"](6789)
        kwargs["on_process_finished"](6789, set())
        return {"width": 16, "height": 16}

    monkeypatch.setattr(api_module, "probe_asset_isolated", _fake_probe)

    result = api.probe_asset(str(source))

    assert result["ok"] is True
    assert callable(observed["started"])
    assert callable(observed["finished"])
