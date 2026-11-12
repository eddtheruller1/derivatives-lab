"""Make the volsurf package importable when pytest runs from this folder or the repo root."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
