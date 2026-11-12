import copy
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import yaml
from typing import Any

from driftbench.diff import compute_diff, escape_pointer
from driftbench.operators import get_all_operators
from driftbench.operators.base import BaseOperator


def get_git_commit(cwd: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "initial-commit"


def split_operators(operators: list[BaseOperator], rng: random.Random) -> tuple[set[str], set[str]]:
    by_area: dict[str, list[BaseOperator]] = {}
    for op in operators:
        by_area.setdefault(op.area, []).append(op)

    seen: set[str] = set()
    held_out: set[str] = set()

    for area in sorted(by_area.keys()):
        ops = sorted(by_area[area], key=lambda x: x.id)
        shuffled = list(ops)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_held = max(1 if n >= 2 else 0, round(0.25 * n))
        for op in shuffled[:n_held]:
            held_out.add(op.id)
        for op in shuffled[n_held:]:
            seen.add(op.id)

    return seen, held_out


def paths_intersect(paths1: list[str], paths2: list[str]) -> bool:
    for p1 in paths1:
        c1 = p1.rstrip("/")
        for p2 in paths2:
            c2 = p2.rstrip("/")
            if c1 == c2 or c1.startswith(c2 + "/") or c2.startswith(c1 + "/"):
                return True
    return False


def validate_self_check(
    desired: dict, live: dict, intended_paths: list[str]
) -> tuple[bool, str, list[dict]]:
    try:
        yaml_str = yaml.safe_dump(live, sort_keys=False)
        reloaded = yaml.safe_load(yaml_str)
        if not isinstance(reloaded, dict):
            return False, "Live resource failed YAML round-trip", []
    except Exception as e:
        return False, f"Live resource is invalid YAML: {e}", []

    diffs = compute_diff(desired, live)
    if not diffs:
        return False, "Diff is empty", []

    for d in diffs:
        d_path = d["path"].rstrip("/")
        matched = False
        for ip in intended_paths:
            c_ip = ip.rstrip("/")
            if d_path == c_ip or d_path.startswith(c_ip + "/") or c_ip.startswith(d_path + "/"):
                matched = True
                break
        if not matched:
            return False, f"Diff touches unintended path {d_path} not in {intended_paths}", diffs

    return True, "", diffs


def normalize_pair_diff(diff_list: list[dict], env: str) -> str:
    s = json.dumps(diff_list, sort_keys=True)
    if env == "dev":
        s = re.sub(r'([_-])dev\b', r'\1ENV', s)
        s = re.sub(r'\bdev\b', 'ENV', s)
    elif env == "prod":
        s = re.sub(r'([_-])prod\b', r'\1ENV', s)
        s = re.sub(r'\bprod\b', 'ENV', s)
    return s


class ManifestIndex:
    def __init__(self, baseline_dir: Path, lock_data: dict[str, Any]):
        self.baseline_dir = baseline_dir
        self.lock_data = lock_data
        self.items: list[dict[str, Any]] = []
        self._load()

    def _load(self):
        yaml_files = sorted(list(self.baseline_dir.glob("*/*.yaml")))
        for yf in yaml_files:
            rel = yf.relative_to(self.baseline_dir)
            ns_dir = rel.parts[0]
            if "-" not in ns_dir:
                continue
            app, env = ns_dir.rsplit("-", 1)
            with open(yf, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f)
            if not doc or not isinstance(doc, dict):
                continue
            kind = doc.get("kind", "")
            name = doc.get("metadata", {}).get("name", "")
            chart_info = self.lock_data.get(app, {})
            norm_name = re.sub(rf"-{env}\b", "", name)
            self.items.append({
                "file_path": yf,
                "app": app,
                "env": env,
                "kind": kind,
                "name": name,
                "norm_name": norm_name,
                "chart": chart_info.get("chart", f"bitnami/{app}"),
                "chart_version": chart_info.get("version", "1.0.0"),
                "doc": doc,
            })


def clean_dataset_artifacts(dataset_dir: Path):
    subdirs_to_clean = ["raw", "rejected", "annotation", "splits"]
    for s in subdirs_to_clean:
        d = dataset_dir / s
        if d.exists():
            for item in d.glob("*"):
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    try:
                        item.unlink()
                    except Exception:
                        pass
    for f in ["rejected.jsonl", "baseline_status.json", "index.csv", "REPORT.md"]:
        p = dataset_dir / f
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


def generate_dataset(
    baseline_dir: Path,
    dataset_dir: Path,
    seed: int = 42,
    target_count: int = 330,
) -> dict[str, Any]:
    clean_dataset_artifacts(dataset_dir)

    rng = random.Random(seed)
    operators = get_all_operators()
    op_map = {op.id: op for op in operators}

    lock_file = baseline_dir / "charts.lock.json"
    lock_data = {}
    if lock_file.exists():
        with open(lock_file, "r", encoding="utf-8") as f:
            lock_data = json.load(f)

    manifest_idx = ManifestIndex(baseline_dir, lock_data)
    commit_hash = get_git_commit(baseline_dir.parent)

    splits_dir = dataset_dir / "splits"
    raw_dir = dataset_dir / "raw"
    rejected_dir = dataset_dir / "rejected"
    splits_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    seen_ops, held_out_ops = split_operators(operators, random.Random(seed))
    with open(splits_dir / "operators.json", "w", encoding="utf-8") as f:
        json.dump(
            {"seen": sorted(list(seen_ops)), "held_out": sorted(list(held_out_ops))},
            f,
            indent=2,
        )

    rejected_file = dataset_dir / "rejected.jsonl"
    rejected_log = open(rejected_file, "w", encoding="utf-8")

    def log_rejected(case_id: str, reason: str, meta: dict):
        entry = {"case_id": case_id, "reason": reason, "meta": meta}
        rejected_log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        rejected_log.flush()

    used_combinations = set()
    operator_counts = {op.id: 0 for op in operators}
    op_param_counts = {(op.id, param): 0 for op in operators for param in op.params}
    candidate_cases: list[dict[str, Any]] = []

    try:
        target_pairs = 50
        dev_by_key = {}
        prod_by_key = {}
        for item in manifest_idx.items:
            key = (item["app"], item["kind"], item["norm_name"])
            if item["env"] == "dev":
                dev_by_key[key] = item
            elif item["env"] == "prod":
                prod_by_key[key] = item

        common_keys = sorted(list(set(dev_by_key.keys()) & set(prod_by_key.keys())))
        rng.shuffle(common_keys)

        pair_counter = 1
        for key in common_keys:
            if pair_counter > target_pairs:
                break
            dev_item = dev_by_key[key]
            prod_item = prod_by_key[key]

            applicable_ops = [
                op for op in operators
                if op.is_applicable(dev_item["doc"]) and op.is_applicable(prod_item["doc"])
            ]
            if not applicable_ops:
                continue

            applicable_ops.sort(key=lambda o: (operator_counts[o.id], rng.random()))

            chosen_op = None
            chosen_param = None
            mut_dev, intended_dev, ctx_dev = None, [], {}
            mut_prod, intended_prod, ctx_prod = None, [], {}
            sig_dev_chosen, sig_prod_chosen = None, None

            for op in applicable_ops:
                cand_params = list(op.params)
                cand_params.sort(key=lambda p: (op_param_counts.get((op.id, p), 0), rng.random()))
                for p in cand_params:
                    sig_dev = (str(dev_item["file_path"]), op.id, p)
                    sig_prod = (str(prod_item["file_path"]), op.id, p)
                    if sig_dev in used_combinations or sig_prod in used_combinations:
                        continue

                    m_dev, int_dev, c_dev = op.apply(dev_item["doc"], p, rng)
                    if not m_dev:
                        continue
                    m_prod, int_prod, c_prod = op.apply(prod_item["doc"], p, rng, context=c_dev)
                    if not m_prod:
                        continue

                    chosen_op = op
                    chosen_param = p
                    mut_dev, intended_dev, ctx_dev = m_dev, int_dev, c_dev
                    mut_prod, intended_prod, ctx_prod = m_prod, int_prod, c_prod
                    sig_dev_chosen, sig_prod_chosen = sig_dev, sig_prod
                    break
                if chosen_op:
                    break

            if not chosen_op:
                continue

            ok_dev, r_dev, diffs_dev = validate_self_check(dev_item["doc"], mut_dev, intended_dev)
            ok_prod, r_prod, diffs_prod = validate_self_check(prod_item["doc"], mut_prod, intended_prod)

            pair_id = f"PAIR_{pair_counter:03d}"
            if not ok_dev:
                log_rejected(f"{pair_id}_dev", r_dev, {"op": chosen_op.id, "param": chosen_param})
                continue
            if not ok_prod:
                log_rejected(f"{pair_id}_prod", r_prod, {"op": chosen_op.id, "param": chosen_param})
                continue

            norm_dev = normalize_pair_diff(diffs_dev, "dev")
            norm_prod = normalize_pair_diff(diffs_prod, "prod")
            if norm_dev != norm_prod:
                log_rejected(f"{pair_id}_diff_mismatch", "Pair diff mismatch after env normalization", {"op": chosen_op.id})
                continue

            used_combinations.add(sig_dev_chosen)
            used_combinations.add(sig_prod_chosen)
            operator_counts[chosen_op.id] += 2
            op_param_counts[(chosen_op.id, chosen_param)] = op_param_counts.get((chosen_op.id, chosen_param), 0) + 2

            split_label = "held_out" if chosen_op.id in held_out_ops else "seen"

            case_dev = {
                "case_type": "paired",
                "pair_id": pair_id,
                "app": dev_item["app"],
                "chart": dev_item["chart"],
                "chart_version": dev_item["chart_version"],
                "resource_kind": dev_item["kind"],
                "resource_name": dev_item["name"],
                "namespace": dev_item["doc"].get("metadata", {}).get("namespace", f"{dev_item['app']}-dev"),
                "environment": "dev",
                "mutation_operators": [chosen_op.id],
                "operator_params": [ctx_dev],
                "operator_split": split_label,
                "desired": dev_item["doc"],
                "live": mut_dev,
                "diff": diffs_dev,
            }
            case_prod = {
                "case_type": "paired",
                "pair_id": pair_id,
                "app": prod_item["app"],
                "chart": prod_item["chart"],
                "chart_version": prod_item["chart_version"],
                "resource_kind": prod_item["kind"],
                "resource_name": prod_item["name"],
                "namespace": prod_item["doc"].get("metadata", {}).get("namespace", f"{prod_item['app']}-prod"),
                "environment": "prod",
                "mutation_operators": [chosen_op.id],
                "operator_params": [ctx_prod],
                "operator_split": split_label,
                "desired": prod_item["doc"],
                "live": mut_prod,
                "diff": diffs_prod,
            }

            candidate_cases.append(case_dev)
            candidate_cases.append(case_prod)
            pair_counter += 1

        target_compound = 66
        compound_count = 0
        compound_env_counts = {"dev": 0, "prod": 0}
        shuffled_items = list(manifest_idx.items)
        rng.shuffle(shuffled_items)

        attempts = 0
        while compound_count < target_compound and attempts < 2500:
            attempts += 1
            target_env = "dev" if compound_env_counts["dev"] <= compound_env_counts["prod"] else "prod"
            env_candidates = [m for m in shuffled_items if m["env"] == target_env]
            if not env_candidates:
                env_candidates = shuffled_items
            item = rng.choice(env_candidates)
            doc = item["doc"]
            applicable_ops = [op for op in operators if op.is_applicable(doc)]
            if len(applicable_ops) < 2:
                continue

            num_ops = rng.choice([2, 3])
            by_area = {}
            for op in applicable_ops:
                by_area.setdefault(op.area, []).append(op)
            if len(by_area) < num_ops:
                continue

            chosen_areas = rng.sample(list(by_area.keys()), num_ops)
            chosen_ops = []
            for a in chosen_areas:
                area_ops = by_area[a]
                area_ops.sort(key=lambda o: (operator_counts[o.id], rng.random()))
                chosen_ops.append(area_ops[0])

            chosen_params = [rng.choice(op.params) for op in chosen_ops]
            sig = (str(item["file_path"]), tuple(op.id for op in chosen_ops), tuple(chosen_params))
            if sig in used_combinations:
                continue

            cur_doc = doc
            all_intended: list[str] = []
            chosen_contexts: list[dict[str, Any]] = []
            chosen_params: list[str] = []
            intersected = False
            valid_compound = True

            for op in chosen_ops:
                cand_p = list(op.params)
                cand_p.sort(key=lambda p: (op_param_counts.get((op.id, p), 0), rng.random()))
                applied_p = None
                for p in cand_p:
                    if not op.is_applicable(cur_doc):
                        break
                    mutated, intended, ctx = op.apply(cur_doc, p, rng)
                    if mutated and not paths_intersect(all_intended, intended):
                        all_intended.extend(intended)
                        chosen_contexts.append(ctx)
                        chosen_params.append(p)
                        cur_doc = mutated
                        applied_p = p
                        break
                if not applied_p:
                    valid_compound = False
                    break

            if not valid_compound:
                continue

            sig = (str(item["file_path"]), tuple(op.id for op in chosen_ops), tuple(chosen_params))
            if sig in used_combinations:
                continue

            ok, reason, diffs = validate_self_check(doc, cur_doc, all_intended)
            if not ok:
                log_rejected(f"compound_cand_{attempts}", reason, {"ops": [o.id for o in chosen_ops]})
                continue

            used_combinations.add(sig)
            for op, p in zip(chosen_ops, chosen_params):
                operator_counts[op.id] += 1
                op_param_counts[(op.id, p)] = op_param_counts.get((op.id, p), 0) + 1
            compound_env_counts[item["env"]] += 1

            op_ids = [op.id for op in chosen_ops]
            has_held_out = any(op_id in held_out_ops for op_id in op_ids)
            split_label = "held_out" if has_held_out else "seen"

            case = {
                "case_type": "compound",
                "pair_id": None,
                "app": item["app"],
                "chart": item["chart"],
                "chart_version": item["chart_version"],
                "resource_kind": item["kind"],
                "resource_name": item["name"],
                "namespace": doc.get("metadata", {}).get("namespace", f"{item['app']}-{item['env']}"),
                "environment": item["env"],
                "mutation_operators": op_ids,
                "operator_params": chosen_contexts,
                "operator_split": split_label,
                "desired": doc,
                "live": cur_doc,
                "diff": diffs,
            }
            candidate_cases.append(case)
            compound_count += 1

        single_env_counts = {"dev": 0, "prod": 0}

        def get_target_param_count(op_id: str, param: str) -> int:
            if op_id == "MUT-WL-REPLICAS" and param == "0":
                return 4
            if op_id == "MUT-RES-LIMITS" and param == "x0.25":
                return 4
            if op_id == "MUT-CFG-ENV-REMOVE":
                return 5
            return 2

        for op in operators:
            for param in op.params:
                target_cnt = get_target_param_count(op.id, param)
                while op_param_counts.get((op.id, param), 0) < target_cnt:
                    target_env = "dev" if single_env_counts["dev"] <= single_env_counts["prod"] else "prod"
                    applicable_manifests = [m for m in manifest_idx.items if op.is_applicable(m["doc"]) and m["env"] == target_env]
                    if not applicable_manifests:
                        applicable_manifests = [m for m in manifest_idx.items if op.is_applicable(m["doc"])]
                    rng.shuffle(applicable_manifests)

                    found = False
                    for item in applicable_manifests:
                        sig = (str(item["file_path"]), op.id, param)
                        if sig in used_combinations:
                            continue
                        mutated, intended, ctx = op.apply(item["doc"], param, rng)
                        if not mutated:
                            continue
                        ok, reason, diffs = validate_self_check(item["doc"], mutated, intended)
                        if not ok:
                            log_rejected(f"boost_{op.id}_{param}", reason, {"op": op.id, "param": param})
                            continue
                        used_combinations.add(sig)
                        operator_counts[op.id] += 1
                        op_param_counts[(op.id, param)] = op_param_counts.get((op.id, param), 0) + 1
                        single_env_counts[item["env"]] += 1
                        split_label = "held_out" if op.id in held_out_ops else "seen"
                        candidate_cases.append({
                            "case_type": "single",
                            "pair_id": None,
                            "app": item["app"],
                            "chart": item["chart"],
                            "chart_version": item["chart_version"],
                            "resource_kind": item["kind"],
                            "resource_name": item["name"],
                            "namespace": item["doc"].get("metadata", {}).get("namespace", f"{item['app']}-{item['env']}"),
                            "environment": item["env"],
                            "mutation_operators": [op.id],
                            "operator_params": [ctx],
                            "operator_split": split_label,
                            "desired": item["doc"],
                            "live": mutated,
                            "diff": diffs,
                        })
                        found = True
                        break

                    if not found:
                        break

        while len(candidate_cases) < target_count:
            target_env = "dev" if single_env_counts["dev"] <= single_env_counts["prod"] else "prod"
            candidates = []
            for item in manifest_idx.items:
                if item["env"] != target_env:
                    continue
                for op in operators:
                    if op.is_applicable(item["doc"]):
                        for param in op.params:
                            sig = (str(item["file_path"]), op.id, param)
                            if sig not in used_combinations:
                                candidates.append((item, op, param, sig))

            if not candidates:
                for item in manifest_idx.items:
                    for op in operators:
                        if op.is_applicable(item["doc"]):
                            for param in op.params:
                                sig = (str(item["file_path"]), op.id, param)
                                if sig not in used_combinations:
                                    candidates.append((item, op, param, sig))

            if not candidates:
                break

            candidates.sort(key=lambda x: (
                op_param_counts.get((x[1].id, x[2]), 0),
                operator_counts[x[1].id],
                rng.random(),
            ))
            item, op, param, sig = candidates[0]

            mutated, intended, ctx = op.apply(item["doc"], param, rng)
            if not mutated:
                used_combinations.add(sig)
                continue

            ok, reason, diffs = validate_self_check(item["doc"], mutated, intended)
            if not ok:
                log_rejected(f"single_fill_{op.id}", reason, {"op": op.id, "param": param})
                used_combinations.add(sig)
                continue

            used_combinations.add(sig)
            operator_counts[op.id] += 1
            op_param_counts[(op.id, param)] = op_param_counts.get((op.id, param), 0) + 1
            single_env_counts[item["env"]] += 1
            split_label = "held_out" if op.id in held_out_ops else "seen"

            candidate_cases.append({
                "case_type": "single",
                "pair_id": None,
                "app": item["app"],
                "chart": item["chart"],
                "chart_version": item["chart_version"],
                "resource_kind": item["kind"],
                "resource_name": item["name"],
                "namespace": item["doc"].get("metadata", {}).get("namespace", f"{item['app']}-{item['env']}"),
                "environment": item["env"],
                "mutation_operators": [op.id],
                "operator_params": [ctx],
                "operator_split": split_label,
                "desired": item["doc"],
                "live": mutated,
                "diff": diffs,
            })

    finally:
        rejected_log.close()

    rng.shuffle(candidate_cases)

    for existing_c in raw_dir.glob("CASE_*"):
        if existing_c.is_dir():
            for f in existing_c.glob("*"):
                f.unlink()
            existing_c.rmdir()

    for idx, case in enumerate(candidate_cases, 1):
        case_id = f"CASE_{idx:04d}"
        case["case_id"] = case_id
        case["seed"] = seed
        case["generator_version"] = commit_hash
        case["validation"] = {"status": "pending", "message": ""}

        case_dir = raw_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        with open(case_dir / "desired.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(case["desired"], f, sort_keys=False)
        with open(case_dir / "live.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(case["live"], f, sort_keys=False)
        with open(case_dir / "diff.json", "w", encoding="utf-8") as f:
            json.dump(case["diff"], f, indent=2, ensure_ascii=False)

        meta = {
            "case_id": case["case_id"],
            "case_type": case["case_type"],
            "pair_id": case["pair_id"],
            "app": case["app"],
            "chart": case["chart"],
            "chart_version": case["chart_version"],
            "resource_kind": case["resource_kind"],
            "resource_name": case["resource_name"],
            "namespace": case["namespace"],
            "environment": case["environment"],
            "mutation_operators": case["mutation_operators"],
            "operator_params": case["operator_params"],
            "operator_split": case["operator_split"],
            "seed": case["seed"],
            "generator_version": case["generator_version"],
            "validation": case["validation"],
        }
        with open(case_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    print(f"Successfully generated {len(candidate_cases)} cases in {raw_dir}")
    return {"total": len(candidate_cases), "operator_counts": operator_counts}


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent / "baseline"
    ds_dir = Path(__file__).resolve().parent.parent / "dataset"
    generate_dataset(base_dir, ds_dir, seed=42, target_count=330)
