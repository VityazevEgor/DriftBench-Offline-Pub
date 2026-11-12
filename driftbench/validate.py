import driftbench
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import yaml
from typing import Any


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check,
    )


def cluster_exists(name: str = "driftbench") -> bool:
    res = run_cmd(["kind", "get", "clusters"], check=False)
    clusters = [c.strip() for c in res.stdout.splitlines() if c.strip()]
    return name in clusters


def create_kind_cluster(name: str = "driftbench"):
    if cluster_exists(name):
        print(f"Cluster '{name}' already exists.")
        return
    print(f"Creating kind cluster '{name}'...")
    run_cmd(["kind", "create", "cluster", "--name", name], check=True)


def delete_kind_cluster(name: str = "driftbench"):
    if cluster_exists(name):
        print(f"Deleting kind cluster '{name}'...")
        run_cmd(["kind", "delete", "cluster", "--name", name], check=False)


def setup_cluster_and_baseline(baseline_dir: Path, cluster_name: str = "driftbench"):
    create_kind_cluster(cluster_name)

    run_cmd(["kubectl", "config", "use-context", f"kind-{cluster_name}"], check=True)

    ns_dirs = [d.name for d in baseline_dir.iterdir() if d.is_dir() and "-" in d.name]
    for ns in sorted(ns_dirs):
        print(f"Ensuring namespace: {ns}")
        res = run_cmd(["kubectl", "create", "namespace", ns, "--dry-run=client", "-o", "yaml"], check=False)
        if res.returncode == 0:
            subprocess.run(["kubectl", "apply", "-f", "-"], input=res.stdout, text=True, check=False)

    print("Applying all baseline manifests to kind cluster...")
    baseline_errors = []
    total_manifests = 0
    for ns_dir in sorted(baseline_dir.iterdir()):
        if not ns_dir.is_dir():
            continue
        yaml_files = sorted(list(ns_dir.glob("*.yaml")))
        for yf in yaml_files:
            total_manifests += 1
            res = run_cmd(
                [
                    "kubectl",
                    "apply",
                    "--server-side",
                    "--field-manager=driftbench",
                    "--force-conflicts",
                    "-f",
                    str(yf),
                ],
                check=False,
            )
            if res.returncode != 0:
                baseline_errors.append({"file": str(yf.name), "error": res.stderr.strip()})

    status_file = baseline_dir.parent / "dataset" / "baseline_status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_manifests": total_manifests,
            "errors": baseline_errors,
            "success": len(baseline_errors) == 0,
        }, f, indent=2)

    if baseline_errors:
        print(f"WARNING: {len(baseline_errors)} errors during baseline application:")
        for err in baseline_errors:
            print(f"  {err['file']}: {err['error']}")
    else:
        print(f"All {total_manifests} baseline manifests applied successfully with 0 errors.")

    for ns in sorted(ns_dirs):
        run_cmd(["kubectl", "scale", "deployments", "--all", "--replicas=0", "-n", ns], check=False)
        run_cmd(["kubectl", "scale", "statefulsets", "--all", "--replicas=0", "-n", ns], check=False)


def validate_all_cases(
    dataset_dir: Path,
    cluster_name: str = "driftbench",
    keep_cluster: bool = False,
) -> dict[str, int]:
    raw_dir = dataset_dir / "raw"
    rejected_dir = dataset_dir / "rejected"
    if rejected_dir.exists():
        shutil.rmtree(rejected_dir, ignore_errors=True)
    rejected_dir.mkdir(parents=True, exist_ok=True)

    case_dirs = sorted([d for d in raw_dir.iterdir() if d.is_dir() and d.name.startswith("CASE_")])
    print(f"Validating {len(case_dirs)} cases via server dry-run...")

    accepted_count = 0
    rejected_count = 0

    for case_dir in case_dirs:
        case_id = case_dir.name
        live_file = case_dir / "live.yaml"
        meta_file = case_dir / "meta.json"

        if not live_file.exists() or not meta_file.exists():
            continue

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        cmd = [
            "kubectl",
            "apply",
            "--server-side",
            "--field-manager=driftbench",
            "--force-conflicts",
            "--dry-run=server",
            "-f",
            str(live_file),
        ]
        res = run_cmd(cmd, check=False)

        if res.returncode == 0:
            meta["validation"] = {"status": "accepted", "message": ""}
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            accepted_count += 1
        else:
            err_msg = res.stderr.strip() or res.stdout.strip()
            meta["validation"] = {"status": "rejected", "message": err_msg}
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)

            dest_dir = rejected_dir / case_id
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.move(str(case_dir), str(dest_dir))
            rejected_count += 1

    print(f"Validation complete: {accepted_count} accepted, {rejected_count} rejected.")

    if not keep_cluster:
        delete_kind_cluster(cluster_name)
    else:
        print(f"Keeping kind cluster '{cluster_name}' as requested.")

    return {"accepted": accepted_count, "rejected": rejected_count}


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent / "baseline"
    ds_dir = Path(__file__).resolve().parent.parent / "dataset"
    setup_cluster_and_baseline(base_dir)
    validate_all_cases(ds_dir, keep_cluster=False)
