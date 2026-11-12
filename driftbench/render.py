import driftbench
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import yaml

CLUSTER_SCOPED_KINDS = {
    "ClusterRole",
    "ClusterRoleBinding",
    "IngressClass",
    "CustomResourceDefinition",
    "Node",
    "PersistentVolume",
    "StorageClass",
}


def compute_chart_sha256(chart_name: str, version: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = ["helm", "pull", chart_name, "--version", version, "-d", tmpdir]
        subprocess.run(cmd, check=True, capture_output=True)
        files = list(Path(tmpdir).glob("*.tgz"))
        if not files:
            raise FileNotFoundError(f"Failed to pull chart archive for {chart_name}")
        content = files[0].read_bytes()
        return hashlib.sha256(content).hexdigest()


def is_helm_hook(doc: dict) -> bool:
    if not isinstance(doc, dict):
        return True
    meta = doc.get("metadata", {})
    if not isinstance(meta, dict):
        return False
    annotations = meta.get("annotations", {})
    if isinstance(annotations, dict) and "helm.sh/hook" in annotations:
        return True
    return False


def postprocess_manifest(doc: dict, app: str, env: str, original_cluster_roles: set[str]) -> dict:
    if not isinstance(doc, dict):
        return doc

    kind = doc.get("kind", "")
    meta = doc.setdefault("metadata", {})
    labels = meta.setdefault("labels", {})
    labels["environment"] = env

    if kind == "PodDisruptionBudget":
        spec = doc.get("spec", {})
        if isinstance(spec, dict) and "enabled" in spec:
            del spec["enabled"]

    is_cluster_scoped = kind in CLUSTER_SCOPED_KINDS

    if is_cluster_scoped:
        orig_name = meta.get("name", "")
        if orig_name and not orig_name.endswith(f"-{env}"):
            meta["name"] = f"{orig_name}-{env}"
        if "namespace" in meta:
            del meta["namespace"]

        if kind == "ClusterRoleBinding":
            role_ref = doc.get("roleRef", {})
            if isinstance(role_ref, dict):
                ref_name = role_ref.get("name", "")
                if ref_name in original_cluster_roles or (orig_name and ref_name in orig_name):
                    if not ref_name.endswith(f"-{env}"):
                        role_ref["name"] = f"{ref_name}-{env}"
            subjects = doc.get("subjects", [])
            if isinstance(subjects, list):
                for subj in subjects:
                    if isinstance(subj, dict) and subj.get("kind") == "ServiceAccount":
                        subj["namespace"] = f"{app}-{env}"
    else:
        meta["namespace"] = f"{app}-{env}"

    return doc


def render_all(config_path: Path, output_dir: Path) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    charts = config.get("charts", [])
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_data = {}

    for c in charts:
        repo_name = c["repo_name"]
        repo_url = c["repo_url"]
        chart_name = c["chart"]
        version = c["version"]
        app = c["name"]
        values = c.get("values", {})

        print(f"Adding/updating helm repo {repo_name} -> {repo_url}...")
        subprocess.run(["helm", "repo", "add", repo_name, repo_url], check=True, capture_output=True)

    subprocess.run(["helm", "repo", "update"], check=True, capture_output=True)

    for c in charts:
        chart_name = c["chart"]
        version = c["version"]
        app = c["name"]
        values = c.get("values", {})

        print(f"Processing chart {chart_name} (version {version})...")
        sha256_hash = compute_chart_sha256(chart_name, version)
        lock_data[app] = {
            "name": app,
            "chart": chart_name,
            "version": version,
            "repo_url": c["repo_url"],
            "sha256": sha256_hash,
        }

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as vf:
            yaml.safe_dump(values, vf)
            val_file = vf.name

        try:
            for env in ["dev", "prod"]:
                ns = f"{app}-{env}"
                env_dir = output_dir / ns
                env_dir.mkdir(parents=True, exist_ok=True)

                cmd = [
                    "helm",
                    "template",
                    f"{app}-{env}",
                    chart_name,
                    "--version",
                    version,
                    "--namespace",
                    ns,
                    "--values",
                    val_file,
                ]
                res = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
                raw_yaml = res.stdout

                docs = list(yaml.safe_load_all(raw_yaml))

                valid_docs = []
                for d in docs:
                    if not d or not isinstance(d, dict):
                        continue
                    if is_helm_hook(d):
                        continue
                    valid_docs.append(d)

                cluster_roles = {
                    d["metadata"]["name"]
                    for d in valid_docs
                    if d.get("kind") == "ClusterRole" and "metadata" in d and "name" in d["metadata"]
                }

                for d in valid_docs:
                    processed = postprocess_manifest(d, app, env, cluster_roles)
                    kind = processed.get("kind", "Unknown")
                    name = processed.get("metadata", {}).get("name", "unnamed")
                    safe_name = name.replace(":", "_").replace("/", "_")
                    filename = f"{kind}__{safe_name}.yaml"
                    target_file = env_dir / filename
                    with open(target_file, "w", encoding="utf-8") as out_f:
                        yaml.safe_dump(processed, out_f, sort_keys=False)

        finally:
            if os.path.exists(val_file):
                os.remove(val_file)

    lock_file = output_dir / "charts.lock.json"
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump(lock_data, f, indent=2)

    print(f"Saved charts lock to {lock_file}")
    return lock_data


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    cfg = Path(__file__).resolve().parent / "charts.yaml"
    out = base_dir / "baseline"
    render_all(cfg, out)
