"""
PreviewGen - Main Entry Point
This file now acts as a thin wrapper importing from the previewgen package.
"""
from __future__ import annotations

import sys

# The previewgen package provides all modules. Importing the entrypoint does
# NOT import pywebview; the GUI runtime is loaded lazily only when needed.
from previewgen.entrypoint import main

if __name__ == "__main__":
    sys.exit(main())
