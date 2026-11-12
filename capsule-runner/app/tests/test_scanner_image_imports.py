"""The 5S scanner image copies a few modules of the worker (fives-scanner/Containerfile): each of them may only import
modules the image copies too, or the scanner fails at its first WinRM session (ModuleNotFoundError)."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
CONTAINERFILE = ROOT / "fives-scanner" / "Containerfile"


def test_the_modules_copied_into_the_scanner_import_only_copied_modules():
    if not CONTAINERFILE.exists():
        pytest.skip("5S module not in this checkout")
    copied = {path for line in CONTAINERFILE.read_text().splitlines() if line.startswith("COPY capsule-runner/app/")
              for path in re.findall(r"capsule-runner/(app/\S+\.py)", line)}
    modules = {path[:-3].replace("/", ".").removesuffix(".__init__") for path in copied}
    missing = []
    for path in sorted(copied):
        for name in re.findall(r"^\s*(?:from|import)\s+(app(?:\.\w+)+)", (ROOT / "capsule-runner" / path).read_text(), re.M):
            if name not in modules and not any(name.startswith(m + ".") for m in modules if m.count(".") >= 2):
                missing.append(f"{path} imports {name}")
    assert not missing, missing
