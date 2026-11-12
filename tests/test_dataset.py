import json
from pathlib import Path
import re
import pytest

from driftbench.generate import normalize_pair_diff


def get_dataset_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "dataset"


def test_paired_identity():
    raw_dir = get_dataset_dir() / "raw"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    pairs: dict[str, list[dict]] = {}
    for case_dir in raw_dir.glob("CASE_*"):
        meta_file = case_dir / "meta.json"
        diff_file = case_dir / "diff.json"
        if not meta_file.exists() or not diff_file.exists():
            continue
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("case_type") == "paired":
            pair_id = meta.get("pair_id")
            with open(diff_file, "r", encoding="utf-8") as f:
                diff = json.load(f)
            pairs.setdefault(pair_id, []).append({"meta": meta, "diff": diff})

    assert len(pairs) >= 40, f"Expected at least 40 pairs, got {len(pairs)}"

    for pair_id, cases in pairs.items():
        assert len(cases) == 2, f"Pair {pair_id} does not have exactly 2 cases"
        c1, c2 = cases[0], cases[1]
        dev_case = c1 if c1["meta"]["environment"] == "dev" else c2
        prod_case = c2 if c2["meta"]["environment"] == "prod" else c1

        assert dev_case["meta"]["environment"] == "dev"
        assert prod_case["meta"]["environment"] == "prod"
        assert dev_case["meta"]["mutation_operators"] == prod_case["meta"]["mutation_operators"], (
            f"Operators mismatch in {pair_id}: {dev_case['meta']['mutation_operators']} vs {prod_case['meta']['mutation_operators']}"
        )
        assert dev_case["meta"]["app"] == prod_case["meta"]["app"]
        assert dev_case["meta"]["resource_kind"] == prod_case["meta"]["resource_kind"]

        norm_dev = normalize_pair_diff(dev_case["diff"], "dev")
        norm_prod = normalize_pair_diff(prod_case["diff"], "prod")
        assert norm_dev == norm_prod, (
            f"Normalized diffs mismatch in {pair_id}:\nDev:  {norm_dev}\nProd: {norm_prod}"
        )


def test_no_replace_with_old_null():
    raw_dir = get_dataset_dir() / "raw"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    violations = []
    for case_dir in raw_dir.glob("CASE_*"):
        diff_file = case_dir / "diff.json"
        if not diff_file.exists():
            continue
        with open(diff_file, "r", encoding="utf-8") as f:
            diffs = json.load(f)
        for d in diffs:
            if d.get("op") == "replace" and d.get("old") is None:
                violations.append((case_dir.name, d))

    assert not violations, f"Found replace with old: null:\n{violations[:10]}"


def test_no_synthetic_tokens_in_live_and_annotations():
    dataset_dir = get_dataset_dir()
    raw_dir = dataset_dir / "raw"
    annot_dir = dataset_dir / "annotation"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    pattern = re.compile(r"\b(mutated|modified)\b", re.IGNORECASE)
    violations = []

    for case_dir in raw_dir.glob("CASE_*"):
        live_file = case_dir / "live.yaml"
        if live_file.exists():
            content = live_file.read_text(encoding="utf-8")
            matches = pattern.findall(content)
            if matches:
                violations.append(f"{live_file.name} in {case_dir.name}: {matches}")

    if annot_dir.exists():
        for csv_file in annot_dir.glob("*.csv"):
            content = csv_file.read_text(encoding="utf-8")
            matches = pattern.findall(content)
            if matches:
                violations.append(f"{csv_file.name}: {matches}")

    assert not violations, f"Found synthetic tokens 'mutated'/'modified':\n" + "\n".join(violations[:10])


def test_operator_acceptance_criteria():
    dataset_dir = get_dataset_dir()
    raw_dir = dataset_dir / "raw"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    op_counts: dict[str, int] = {}
    compound_count = 0
    total_count = 0
    replicas_0_count = 0
    res_limits_x025_count = 0
    cfg_env_remove_count = 0
    cfg_env_remove_single = 0

    for case_dir in raw_dir.glob("CASE_*"):
        meta_file = case_dir / "meta.json"
        if not meta_file.exists():
            continue
        total_count += 1
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        c_type = meta.get("case_type")
        if c_type == "compound":
            compound_count += 1

        ops = meta.get("mutation_operators", [])
        params = meta.get("operator_params", [])
        for op in ops:
            op_counts[op] = op_counts.get(op, 0) + 1
            if op == "MUT-CFG-ENV-REMOVE":
                cfg_env_remove_count += 1
                if c_type == "single":
                    cfg_env_remove_single += 1

        for op, param_info in zip(ops, params):
            p_val = param_info.get("param") if isinstance(param_info, dict) else str(param_info)
            if op == "MUT-WL-REPLICAS" and p_val == "0":
                replicas_0_count += 1
            if op == "MUT-RES-LIMITS" and p_val == "x0.25":
                res_limits_x025_count += 1

    assert total_count >= 280, f"Expected >= 280 accepted cases, got {total_count}"
    assert compound_count >= 50, f"Expected >= 50 compound cases, got {compound_count}"
    assert op_counts.get("MUT-SC-PRIVILEGED", 0) >= 3, f"MUT-SC-PRIVILEGED has {op_counts.get('MUT-SC-PRIVILEGED', 0)} < 3"
    assert op_counts.get("MUT-WL-STRATEGY", 0) >= 3, f"MUT-WL-STRATEGY has {op_counts.get('MUT-WL-STRATEGY', 0)} < 3"
    assert op_counts.get("MUT-SCALE-PDB", 0) >= 3, f"MUT-SCALE-PDB has {op_counts.get('MUT-SCALE-PDB', 0)} < 3"
    assert replicas_0_count >= 3, f"MUT-WL-REPLICAS with param 0 has {replicas_0_count} < 3"
    assert res_limits_x025_count >= 2, f"MUT-RES-LIMITS with param x0.25 has {res_limits_x025_count} < 2"
    assert cfg_env_remove_count >= 3, f"MUT-CFG-ENV-REMOVE has {cfg_env_remove_count} < 3"
    assert cfg_env_remove_single >= 1, f"MUT-CFG-ENV-REMOVE has {cfg_env_remove_single} single cases (< 1)"


def test_raw_and_rejected_isolation_and_version():
    dataset_dir = get_dataset_dir()
    raw_dir = dataset_dir / "raw"
    rejected_dir = dataset_dir / "rejected"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    raw_metas = []
    for cd in raw_dir.glob("CASE_*"):
        mf = cd / "meta.json"
        if mf.exists():
            with open(mf, "r", encoding="utf-8") as f:
                raw_metas.append(json.load(f))

    rejected_metas = []
    if rejected_dir.exists():
        for cd in rejected_dir.glob("CASE_*"):
            mf = cd / "meta.json"
            if mf.exists():
                with open(mf, "r", encoding="utf-8") as f:
                    rejected_metas.append(json.load(f))

    raw_ids = {m["case_id"] for m in raw_metas}
    rej_ids = {m["case_id"] for m in rejected_metas}
    overlap = raw_ids & rej_ids
    assert not overlap, f"raw and rejected case IDs overlap: {overlap}"

    all_metas = raw_metas + rejected_metas
    versions = {m.get("generator_version") for m in all_metas if m.get("generator_version")}
    assert len(versions) == 1, f"Multiple generator versions found across dataset: {versions}"


def test_probe_remove_param_matches_diff():
    raw_dir = get_dataset_dir() / "raw"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    for case_dir in raw_dir.glob("CASE_*"):
        meta_file = case_dir / "meta.json"
        diff_file = case_dir / "diff.json"
        if not meta_file.exists() or not diff_file.exists():
            continue
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        ops = meta.get("mutation_operators", [])
        params = meta.get("operator_params", [])
        if "MUT-WL-PROBE-REMOVE" in ops:
            idx = ops.index("MUT-WL-PROBE-REMOVE")
            p_info = params[idx]
            requested_param = p_info.get("param") if isinstance(p_info, dict) else str(p_info)
            expected_probe = f"{requested_param}Probe"

            with open(diff_file, "r", encoding="utf-8") as f:
                diffs = json.load(f)

            # Find diff items corresponding to probe removal
            probe_diffs = [d for d in diffs if "Probe" in d.get("path", "")]
            assert len(probe_diffs) > 0, f"{case_dir.name}: no probe path found in diff"
            for pd in probe_diffs:
                path = pd.get("path", "")
                assert path.endswith(f"/{expected_probe}"), (
                    f"{case_dir.name}: requested {requested_param}Probe but diff removed {path}"
                )


def _matches_target_val(target, obj) -> bool:
    if obj == target or (isinstance(obj, (int, str, bool)) and str(obj) == str(target)):
        return True
    if isinstance(obj, dict):
        if isinstance(target, dict) and all(obj.get(k) == v for k, v in target.items()):
            return True
        if obj.get("value") == target or target in obj.values():
            return True
        return any(_matches_target_val(target, v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        if isinstance(target, list) and obj == target:
            return True
        return any(_matches_target_val(target, item) for item in obj)
    return False


def test_operator_param_value_matches_diff_new():
    raw_dir = get_dataset_dir() / "raw"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    for case_dir in raw_dir.glob("CASE_*"):
        meta_file = case_dir / "meta.json"
        diff_file = case_dir / "diff.json"
        if not meta_file.exists() or not diff_file.exists():
            continue
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        with open(diff_file, "r", encoding="utf-8") as f:
            diffs = json.load(f)

        for p_info in meta.get("operator_params", []):
            if isinstance(p_info, dict) and "value" in p_info:
                target_val = p_info["value"]
                matched = any(_matches_target_val(target_val, d.get("new")) for d in diffs)
                assert matched, (
                    f"{case_dir.name}: operator param specifies value={target_val!r}, "
                    f"but no operation in diff has new={target_val!r}. Diff: {diffs}"
                )


def test_no_duplicate_cases():
    raw_dir = get_dataset_dir() / "raw"
    if not raw_dir.exists():
        pytest.skip("Dataset not yet generated")

    seen_signatures: dict[tuple, str] = {}
    for case_dir in sorted(raw_dir.glob("CASE_*")):
        meta_file = case_dir / "meta.json"
        diff_file = case_dir / "diff.json"
        if not meta_file.exists() or not diff_file.exists():
            continue
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
        with open(diff_file, "r", encoding="utf-8") as f:
            diff = json.load(f)

        sig = (
            meta.get("namespace"),
            meta.get("resource_name"),
            json.dumps(diff, sort_keys=True),
        )
        if sig in seen_signatures:
            prev_case = seen_signatures[sig]
            pytest.fail(f"Duplicate cases found: {case_dir.name} is identical to {prev_case} with signature {sig[:2]}")
        seen_signatures[sig] = case_dir.name


