"""The scanner reuses the WinRM code of capsule-runner (copied into its image): the tests find it in the repository."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "fives-scanner", ROOT / "capsule-runner"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
