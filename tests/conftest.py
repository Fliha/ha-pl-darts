"""Laad model.py en const.py zonder Home Assistant te importeren."""
import sys
import types
from pathlib import Path

PKG_DIR = Path(__file__).parent.parent / "custom_components" / "pl_darts"
pkg = types.ModuleType("pl_darts")
pkg.__path__ = [str(PKG_DIR)]
sys.modules.setdefault("pl_darts", pkg)
