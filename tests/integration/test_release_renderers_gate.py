import pytest

def test_release_all_mandatory_renderers():
    """Release Gate: Guarantee that all core multi-format engines are installed and importable."""
    import resvg_py
    assert resvg_py is not None

    import psd_tools
    assert psd_tools is not None

    import trimesh
    assert trimesh is not None

    import ezdxf
    assert ezdxf is not None

    import cascadio
    assert cascadio is not None

    import matplotlib
    assert matplotlib is not None
