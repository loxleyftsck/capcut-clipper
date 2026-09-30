"""capcut-clipper: turn long talking-head videos into 9:16 CapCut projects."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Make the vendored MCP package importable without installing it.
_MCP_SRC = REPO / "mcp" / "capcut-mcp" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

# Let every ffmpeg call (ours and capcut_mcp's) find the repo copy in bin/.
_BIN = REPO / "bin"
if (_BIN / "ffmpeg.exe").is_file() and str(_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_BIN}{os.pathsep}{os.environ.get('PATH', '')}"

__version__ = "0.1.0"
