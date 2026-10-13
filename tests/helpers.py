"""Load repository scripts as modules; several have no .py suffix."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent


def load(relative, name):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / relative))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class Exec(Exception):
    """Raised by patched os.exec* so tests can inspect the final argv."""
