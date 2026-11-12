from pathlib import Path
import re
import pytest

FORBIDDEN_WORDS = ["severity", "risk", "critical", "danger"]


def test_static_hygiene_driftbench_and_annotations():
    root_dir = Path(__file__).resolve().parent.parent
    driftbench_dir = root_dir / "driftbench"
    annot_dir = root_dir / "dataset" / "annotation"

    checked_files = []
    if driftbench_dir.exists():
        checked_files.extend(list(driftbench_dir.rglob("*.py")))
        checked_files.extend(list(driftbench_dir.rglob("*.yaml")))
        checked_files.extend(list(driftbench_dir.rglob("*.json")))

    if annot_dir.exists():
        checked_files.extend(list(annot_dir.rglob("*.csv")))
        checked_files.extend(list(annot_dir.rglob("*.html")))

    assert len(checked_files) > 0, "No files found to check for static hygiene"

    violations = []
    pattern = re.compile(r"\b(" + "|".join(FORBIDDEN_WORDS) + r")\b", re.IGNORECASE)

    for f in checked_files:
        text = f.read_text(encoding="utf-8")
        matches = pattern.findall(text)
        if matches:
            violations.append(f"{f.relative_to(root_dir)}: found {matches}")

    assert not violations, f"Forbidden words found:\n" + "\n".join(violations)
