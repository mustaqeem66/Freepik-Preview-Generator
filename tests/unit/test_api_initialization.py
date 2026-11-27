"""Desktop API construction must roll back partially started services."""

from __future__ import annotations

import pytest

from previewgen import api as api_module

pytestmark = pytest.mark.core


def test_api_construction_failure_stops_the_preview_server(monkeypatch) -> None:
    servers: list[api_module.PreviewFileServer] = []

    class _TrackingPreviewServer(api_module.PreviewFileServer):
        def __init__(self, autostart: bool = True) -> None:
            super().__init__(autostart=autostart)
            servers.append(self)

    monkeypatch.setattr(api_module, "PreviewFileServer", _TrackingPreviewServer)

    def _fail_coordinator(*_args, **_kwargs):
        raise RuntimeError("later API initialization failed")

    monkeypatch.setattr(api_module, "PreviewCoordinator", _fail_coordinator)

    with pytest.raises(RuntimeError, match="later API initialization failed"):
        api_module.DesktopApi()

    assert len(servers) == 1
    server = servers[0]
    assert server.running is False
    assert server._root is None
