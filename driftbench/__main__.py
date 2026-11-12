import argparse
from pathlib import Path
import sys

from driftbench.render import render_all
from driftbench.generate import generate_dataset
from driftbench.validate import setup_cluster_and_baseline, validate_all_cases
from driftbench.export import export_dataset
from driftbench.report import generate_report


def main():
    parser = argparse.ArgumentParser(prog="driftbench", description="DriftBench-Offline generator and toolkit")
    parser.add_argument(
        "command",
        choices=["all", "render", "generate", "validate", "export", "report"],
        help="Subcommand to execute",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--keep-cluster", action="store_true", help="Keep kind cluster after validation")
    parser.add_argument("--cluster-name", type=str, default="driftbench", help="Kind cluster name")
    parser.add_argument("--target-count", type=int, default=330, help="Target generated case count")

    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    charts_cfg = Path(__file__).resolve().parent / "charts.yaml"
    baseline_dir = root_dir / "baseline"
    dataset_dir = root_dir / "dataset"

    cmd = args.command

    if cmd in ("all", "render"):
        print("=== Step 1: Render Baseline Manifests ===")
        render_all(charts_cfg, baseline_dir)

    if cmd in ("all", "generate"):
        print("=== Step 2: Generate Candidate Cases ===")
        generate_dataset(baseline_dir, dataset_dir, seed=args.seed, target_count=args.target_count)

    if cmd in ("all", "validate"):
        print("=== Step 3: Validate on kind Cluster ===")
        setup_cluster_and_baseline(baseline_dir, cluster_name=args.cluster_name)
        validate_all_cases(dataset_dir, cluster_name=args.cluster_name, keep_cluster=args.keep_cluster)

    if cmd in ("all", "export"):
        print("=== Step 4: Export Blind Annotation Tables and Splits ===")
        export_dataset(dataset_dir, seed=args.seed)

    if cmd in ("all", "report"):
        print("=== Step 5: Generate REPORT.md ===")
        generate_report(dataset_dir, baseline_dir, seed=args.seed)

    print("Done!")


if __name__ == "__main__":
    main()
