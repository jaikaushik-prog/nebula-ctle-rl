"""pytest configuration — put python_models on the import path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python_models"))
