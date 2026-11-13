"""Keep test scratch files inside the user-selected project directory."""
import tempfile
from pathlib import Path

scratch=Path(__file__).resolve().parents[1]/'data/test-scratch'
scratch.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(scratch)
