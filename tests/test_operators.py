import copy
from pathlib import Path
import random
import yaml
import pytest

from driftbench.diff import compute_diff
from driftbench.operators import get_all_operators


def _path_matches_intended(diff_path: str, intended_paths: list[str]) -> bool:
    for ip in intended_paths:
        p_clean = ip.rstrip("/")
        d_clean = diff_path.rstrip("/")
        if d_clean == p_clean or d_clean.startswith(p_clean + "/") or p_clean.startswith(d_clean + "/"):
            return True
    return False


def test_operators_applicable_and_intended_paths():
    base_dir = Path(__file__).resolve().parent.parent / "baseline"
    yaml_files = list(base_dir.glob("*/*.yaml"))
    assert len(yaml_files) > 0, "No baseline files found"

    resources = []
    for yf in yaml_files:
        with open(yf, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
            if doc and isinstance(doc, dict):
                resources.append(doc)

    operators = get_all_operators()
    rng = random.Random(42)

    tested_ops = set()
    for op in operators:
        suitable = [r for r in resources if op.is_applicable(r)]
        if not suitable:
            continue
        tested_ops.add(op.id)

        mutated, intended, ctx, chosen_res = None, [], {}, None
        for res in suitable:
            for param in op.params:
                orig_copy = copy.deepcopy(res)
                m, intend, c = op.apply(res, param, rng)
                assert res == orig_copy, f"Operator {op.id} mutated input in-place"
                if m is not None:
                    mutated, intended, ctx, chosen_res = m, intend, c, res
                    break
            if mutated is not None:
                break

        assert mutated is not None, f"Operator {op.id} returned None on all applicable resources and params"
        assert len(intended) > 0, f"Operator {op.id} returned empty intended_paths"
        assert isinstance(ctx, dict), f"Operator {op.id} returned invalid context dict"

        diffs = compute_diff(chosen_res, mutated)
        assert len(diffs) > 0, f"Operator {op.id} produced empty diff"

        for d in diffs:
            d_path = d["path"]
            assert _path_matches_intended(d_path, intended), (
                f"Operator {op.id} diff path {d_path} not in intended {intended}"
            )

    assert len(tested_ops) >= 50, f"Only {len(tested_ops)} operators were tested out of {len(operators)}"


def test_probe_remove_strict_param():
    from driftbench.operators.workload import MutWlProbeRemove
    op = MutWlProbeRemove()
    rng = random.Random(42)

    sample_workload = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": "app",
                            "image": "nginx:1.31.7",
                            "livenessProbe": {"httpGet": {"path": "/healthz", "port": 80}},
                            "readinessProbe": {"httpGet": {"path": "/ready", "port": 80}},
                        }
                    ]
                }
            }
        },
    }

    # Requesting startupProbe when it is not present must return None
    mut, intended, ctx = op.apply(sample_workload, "startup", rng)
    assert mut is None, "MUT-WL-PROBE-REMOVE must return None when requested probe is missing"

    # Requesting livenessProbe must only remove livenessProbe
    mut, intended, ctx = op.apply(sample_workload, "liveness", rng)
    assert mut is not None
    assert intended == ["/spec/template/spec/containers/0/livenessProbe"]
    assert "livenessProbe" not in mut["spec"]["template"]["spec"]["containers"][0]
    assert "readinessProbe" in mut["spec"]["template"]["spec"]["containers"][0]

