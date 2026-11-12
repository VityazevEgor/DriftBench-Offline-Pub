import csv
import json
from pathlib import Path
import random
import yaml
from typing import Any

from driftbench.diff import format_readable_diff


def export_dataset(dataset_dir: Path, seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    raw_dir = dataset_dir / "raw"
    splits_dir = dataset_dir / "splits"
    annot_dir = dataset_dir / "annotation"
    splits_dir.mkdir(parents=True, exist_ok=True)
    annot_dir.mkdir(parents=True, exist_ok=True)

    with open(splits_dir / "operators.json", "r", encoding="utf-8") as f:
        op_splits = json.load(f)
    held_out_ops = set(op_splits.get("held_out", []))

    accepted_cases = []
    case_dirs = sorted([d for d in raw_dir.iterdir() if d.is_dir() and d.name.startswith("CASE_")])

    for c_dir in case_dirs:
        meta_file = c_dir / "meta.json"
        desired_file = c_dir / "desired.yaml"
        live_file = c_dir / "live.yaml"
        diff_file = c_dir / "diff.json"

        if not (meta_file.exists() and desired_file.exists() and live_file.exists() and diff_file.exists()):
            continue

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        if meta.get("validation", {}).get("status") == "rejected":
            continue

        with open(desired_file, "r", encoding="utf-8") as f:
            desired = yaml.safe_load(f)
        with open(live_file, "r", encoding="utf-8") as f:
            live = yaml.safe_load(f)
        with open(diff_file, "r", encoding="utf-8") as f:
            diff_ops = json.load(f)

        diff_readable_lines = format_readable_diff(
            diff_ops, desired=desired, live=live, resource_kind=meta.get("resource_kind", "")
        )
        diff_readable = "\n".join(diff_readable_lines)

        desired_text = desired_file.read_text(encoding="utf-8")
        live_text = live_file.read_text(encoding="utf-8")

        accepted_cases.append({
            "meta": meta,
            "desired": desired,
            "live": live,
            "desired_text": desired_text,
            "live_text": live_text,
            "diff_ops": diff_ops,
            "diff_readable": diff_readable,
        })

    print(f"Exporting {len(accepted_cases)} accepted cases...")

    dev_case_ids: list[str] = []
    test_case_ids: list[str] = []

    units = []
    pair_groups: dict[str, list[dict]] = {}
    for c in accepted_cases:
        p_id = c["meta"].get("pair_id")
        if p_id:
            pair_groups.setdefault(p_id, []).append(c)
        else:
            units.append([c])

    for p_id, p_cases in sorted(pair_groups.items()):
        units.append(p_cases)

    rng.shuffle(units)

    remaining_units = []
    for u in units:
        has_held_out = False
        for c in u:
            for op in c["meta"].get("mutation_operators", []):
                if op in held_out_ops:
                    has_held_out = True
                    break
        if has_held_out:
            for c in u:
                test_case_ids.append(c["meta"]["case_id"])
        else:
            remaining_units.append(u)

    by_strat = {}
    for u in remaining_units:
        env = u[0]["meta"].get("environment", "dev")
        by_strat.setdefault(env, []).append(u)

    for env_key, u_list in by_strat.items():
        rng.shuffle(u_list)
        n_dev = round(len(u_list) * 0.3)
        for u in u_list[:n_dev]:
            for c in u:
                dev_case_ids.append(c["meta"]["case_id"])
        for u in u_list[n_dev:]:
            for c in u:
                test_case_ids.append(c["meta"]["case_id"])

    dev_case_ids.sort()
    test_case_ids.sort()

    cases_split_file = splits_dir / "cases.json"
    with open(cases_split_file, "w", encoding="utf-8") as f:
        json.dump({"dev": dev_case_ids, "test": test_case_ids}, f, indent=2)

    split_lookup = {}
    for cid in dev_case_ids:
        split_lookup[cid] = "dev"
    for cid in test_case_ids:
        split_lookup[cid] = "test"

    shuffled_main = list(accepted_cases)
    rng.shuffle(shuffled_main)

    main_csv_file = annot_dir / "annotation_main.csv"
    with open(main_csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "case_id",
            "resource_kind",
            "resource_name",
            "environment",
            "diff_readable",
            "label",
            "comment",
        ])
        for c in shuffled_main:
            m = c["meta"]
            writer.writerow([
                m["case_id"],
                m["resource_kind"],
                m["resource_name"],
                m["environment"],
                c["diff_readable"],
                "",
                "",
            ])

    compound_cases = [c for c in accepted_cases if c["meta"].get("case_type") == "compound"]
    non_compound_cases = [c for c in accepted_cases if c["meta"].get("case_type") != "compound"]

    rng.shuffle(compound_cases)
    rng.shuffle(non_compound_cases)

    second_set = []
    second_set.extend(compound_cases[:12])

    by_kind_env = {}
    for c in non_compound_cases:
        key = (c["meta"].get("resource_kind"), c["meta"].get("environment"))
        by_kind_env.setdefault(key, []).append(c)

    needed = 50 - len(second_set)
    while len(second_set) < 50:
        added_in_round = 0
        for k_env in sorted(by_kind_env.keys()):
            if by_kind_env[k_env] and len(second_set) < 50:
                second_set.append(by_kind_env[k_env].pop(0))
                added_in_round += 1
        if added_in_round == 0:
            break

    rng.shuffle(second_set)

    second_csv_file = annot_dir / "annotation_second.csv"
    with open(second_csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "case_id",
            "resource_kind",
            "resource_name",
            "environment",
            "diff_readable",
            "label",
            "comment",
        ])
        for c in second_set:
            m = c["meta"]
            writer.writerow([
                m["case_id"],
                m["resource_kind"],
                m["resource_name"],
                m["environment"],
                c["diff_readable"],
                "",
                "",
            ])

    index_csv_file = dataset_dir / "index.csv"
    with open(index_csv_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "case_id",
            "case_type",
            "pair_id",
            "app",
            "chart",
            "chart_version",
            "resource_kind",
            "resource_name",
            "namespace",
            "environment",
            "mutation_operators",
            "operator_params",
            "operator_split",
            "seed",
            "generator_version",
            "validation_status",
            "validation_message",
            "n_diff_ops",
            "split",
        ])
        for c in accepted_cases:
            m = c["meta"]
            cid = m["case_id"]
            writer.writerow([
                cid,
                m.get("case_type", ""),
                m.get("pair_id") or "",
                m.get("app", ""),
                m.get("chart", ""),
                m.get("chart_version", ""),
                m.get("resource_kind", ""),
                m.get("resource_name", ""),
                m.get("namespace", ""),
                m.get("environment", ""),
                json.dumps(m.get("mutation_operators", [])),
                json.dumps(m.get("operator_params", [])),
                m.get("operator_split", ""),
                m.get("seed", 42),
                m.get("generator_version", ""),
                m.get("validation", {}).get("status", "accepted"),
                m.get("validation", {}).get("message", ""),
                len(c["diff_ops"]),
                split_lookup.get(cid, "test"),
            ])

    viewer_file = annot_dir / "viewer.html"
    viewer_cases_data = []
    for c in shuffled_main:
        m = c["meta"]
        viewer_cases_data.append({
            "id": m["case_id"],
            "kind": m["resource_kind"],
            "name": m["resource_name"],
            "env": m["environment"],
            "diff": c["diff_readable"],
            "desired": c["desired_text"],
            "live": c["live_text"],
        })

    viewer_html_content = _build_viewer_html(viewer_cases_data)
    viewer_file.write_text(viewer_html_content, encoding="utf-8")

    print(f"Exported annotation tables, index.csv, cases.json, and viewer.html successfully.")
    return {
        "accepted": len(accepted_cases),
        "dev_cases": len(dev_case_ids),
        "test_cases": len(test_case_ids),
        "second_annotator_cases": len(second_set),
    }


def _build_viewer_html(cases: list[dict]) -> str:
    cases_json = json.dumps(cases, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>DriftBench Annotation Viewer</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; margin: 0; padding: 0; display: flex; height: 100vh; background: #f4f6f8; color: #24292f; }}
  #sidebar {{ width: 340px; background: #ffffff; border-right: 1px solid #d0d7de; display: flex; flex-direction: column; }}
  #search-box {{ padding: 12px; border-bottom: 1px solid #d0d7de; }}
  #search-box input {{ width: 100%; padding: 8px 12px; border: 1px solid #d0d7de; border-radius: 6px; font-size: 14px; }}
  #case-list {{ flex: 1; overflow-y: auto; }}
  .case-item {{ padding: 10px 14px; border-bottom: 1px solid #eaeef2; cursor: pointer; transition: background 0.15s; }}
  .case-item:hover {{ background: #f6f8fa; }}
  .case-item.active {{ background: #ddf4ff; border-left: 4px solid #0969da; }}
  .case-item-title {{ font-weight: 600; font-size: 14px; display: flex; justify-content: space-between; }}
  .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
  .badge-dev {{ background: #dafbe1; color: #1a7f37; }}
  .badge-prod {{ background: #ffebe9; color: #cf222e; }}
  .case-item-sub {{ font-size: 12px; color: #57606a; margin-top: 4px; }}
  #main {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 20px; }}
  .card {{ background: #ffffff; border: 1px solid #d0d7de; border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
  .diff-box {{ background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 13px; white-space: pre-wrap; line-height: 1.5; color: #0550ae; }}
  .manifests-container {{ display: flex; gap: 16px; flex: 1; min-height: 0; }}
  .manifest-col {{ flex: 1; display: flex; flex-direction: column; background: #ffffff; border: 1px solid #d0d7de; border-radius: 6px; overflow: hidden; }}
  .col-header {{ background: #f6f8fa; padding: 8px 14px; font-weight: 600; font-size: 13px; border-bottom: 1px solid #d0d7de; }}
  .code-view {{ flex: 1; margin: 0; padding: 12px; overflow: auto; font-family: monospace; font-size: 12px; background: #ffffff; line-height: 1.4; }}
</style>
</head>
<body>
<div id="sidebar">
  <div id="search-box">
    <input type="text" id="filter" placeholder="Filter by case, kind, name, env..." oninput="filterCases()">
  </div>
  <div id="case-list"></div>
</div>
<div id="main">
  <div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
      <h2 id="view-title" style="margin: 0; font-size: 18px;">Select a Case</h2>
      <div id="view-env-badge"></div>
    </div>
    <div id="view-meta" style="font-size: 13px; color: #57606a; margin-bottom: 12px;"></div>
    <div style="font-weight: 600; font-size: 13px; margin-bottom: 4px;">Diff Summary:</div>
    <div id="view-diff" class="diff-box">No case selected</div>
  </div>
  <div class="manifests-container">
    <div class="manifest-col">
      <div class="col-header">desired.yaml</div>
      <pre id="view-desired" class="code-view"></pre>
    </div>
    <div class="manifest-col">
      <div class="col-header">live.yaml</div>
      <pre id="view-live" class="code-view"></pre>
    </div>
  </div>
</div>
<script>
  const cases = {cases_json};
  let filtered = [...cases];
  let currentIdx = 0;

  function renderList() {{
    const container = document.getElementById('case-list');
    container.innerHTML = '';
    filtered.forEach((c, idx) => {{
      const div = document.createElement('div');
      div.className = 'case-item' + (idx === currentIdx ? ' active' : '');
      const badgeCls = c.env === 'prod' ? 'badge-prod' : 'badge-dev';
      div.innerHTML = `
        <div class="case-item-title">
          <span>${{c.id}}</span>
          <span class="badge ${{badgeCls}}">${{c.env}}</span>
        </div>
        <div class="case-item-sub">${{c.kind}} / ${{c.name}}</div>
      `;
      div.onclick = () => selectCase(idx);
      container.appendChild(div);
    }});
  }}

  function selectCase(idx) {{
    currentIdx = idx;
    renderList();
    if (!filtered[idx]) return;
    const c = filtered[idx];
    document.getElementById('view-title').innerText = `${{c.id}} — ${{c.kind}} / ${{c.name}}`;
    document.getElementById('view-env-badge').innerHTML = `<span class="badge ${{c.env === 'prod' ? 'badge-prod' : 'badge-dev'}}">${{c.env}}</span>`;
    document.getElementById('view-meta').innerText = `Resource: ${{c.kind}} | Name: ${{c.name}} | Environment: ${{c.env}}`;
    document.getElementById('view-diff').innerText = c.diff;
    document.getElementById('view-desired').innerText = c.desired;
    document.getElementById('view-live').innerText = c.live;
  }}

  function filterCases() {{
    const q = document.getElementById('filter').value.toLowerCase();
    filtered = cases.filter(c => 
      c.id.toLowerCase().includes(q) ||
      c.kind.toLowerCase().includes(q) ||
      c.name.toLowerCase().includes(q) ||
      c.env.toLowerCase().includes(q)
    );
    currentIdx = 0;
    renderList();
    if (filtered.length > 0) selectCase(0);
  }}

  if (filtered.length > 0) selectCase(0);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    ds_dir = Path(__file__).resolve().parent.parent / "dataset"
    export_dataset(ds_dir, seed=42)
