import filecmp
from pathlib import Path
import shutil
import tempfile
import pytest

from driftbench.generate import generate_dataset


def test_generation_determinism():
    base_dir = Path(__file__).resolve().parent.parent / "baseline"

    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        dir1 = Path(tmp1)
        dir2 = Path(tmp2)

        generate_dataset(base_dir, dir1, seed=42, target_count=30)
        generate_dataset(base_dir, dir2, seed=42, target_count=30)

        raw1 = dir1 / "raw"
        raw2 = dir2 / "raw"

        cases1 = sorted([c.name for c in raw1.glob("CASE_*")])
        cases2 = sorted([c.name for c in raw2.glob("CASE_*")])

        assert cases1 == cases2, "Case IDs do not match between identical runs"

        for cid in cases1:
            c_dir1 = raw1 / cid
            c_dir2 = raw2 / cid

            for fname in ["desired.yaml", "live.yaml", "diff.json", "meta.json"]:
                f1 = (c_dir1 / fname).read_text(encoding="utf-8")
                f2 = (c_dir2 / fname).read_text(encoding="utf-8")
                assert f1 == f2, f"File {fname} differs in {cid} between runs"
