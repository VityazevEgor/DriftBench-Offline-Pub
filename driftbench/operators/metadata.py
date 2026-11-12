import copy
import random
import re
from typing import Any
from driftbench.diff import escape_pointer
from driftbench.operators.base import BaseOperator, WORKLOAD_KINDS, get_pod_template

PROTECTED_LABELS = {
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "app.kubernetes.io/managed-by",
    "app.kubernetes.io/component",
    "app.kubernetes.io/part-of",
    "environment",
}


class MutMetaLabelAdd(BaseOperator):
    id = "MUT-META-LABEL-ADD"
    area = "metadata"
    applicable_kinds = ["*"]
    params = ["pipeline.run/id", "build-number", "owner", "env-ticket"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        return True

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        meta = res.setdefault("metadata", {})
        if not isinstance(meta, dict):
            meta = res["metadata"] = {}
        labels = meta.get("labels")
        if not isinstance(labels, dict):
            labels = meta["labels"] = {}

        if context and "value" in context:
            val = context["value"]
        else:
            val_map = {
                "pipeline.run/id": f"pipe-{rng.randint(1000, 9999)}",
                "build-number": str(rng.randint(10, 500)),
                "owner": f"team-{rng.choice(['alpha', 'beta', 'platform', 'infrastructure'])}",
                "env-ticket": f"TICKET-{rng.randint(100, 999)}",
            }
            val = val_map.get(param, f"val-{rng.randint(1, 100)}")

        labels[param] = val
        ctx = {"param": param, "key": param, "value": val}
        return res, [f"/metadata/labels/{escape_pointer(param)}"], ctx


class MutMetaLabelChange(BaseOperator):
    id = "MUT-META-LABEL-CHANGE"
    area = "metadata"
    applicable_kinds = ["*"]
    params = ["change_val"]

    def _get_candidate_keys(self, resource: dict[str, Any]) -> list[str]:
        labels = resource.get("metadata", {}).get("labels", {})
        if not isinstance(labels, dict) or not labels:
            return []
        candidates = [
            k for k in sorted(labels.keys())
            if k not in PROTECTED_LABELS and not k.startswith("app.kubernetes.io/name")
        ]
        return candidates

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        return len(self._get_candidate_keys(resource)) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        candidates = self._get_candidate_keys(res)
        if not candidates:
            return None, [], {}

        if context and context.get("key") in res.get("metadata", {}).get("labels", {}):
            chosen_key = context["key"]
            new_val = context["value"]
        else:
            chosen_key = rng.choice(candidates)
            cur_val = str(res["metadata"]["labels"][chosen_key])
            if chosen_key == "app.kubernetes.io/version":
                match = re.search(r"(\d+)$", cur_val)
                if match:
                    new_val = cur_val[: match.start(1)] + str(int(match.group(1)) + 1)
                else:
                    new_val = f"{cur_val}.1"
            elif chosen_key == "helm.sh/chart":
                match = re.search(r"(\d+)$", cur_val)
                if match:
                    new_val = cur_val[: match.start(1)] + str(int(match.group(1)) + 1)
                else:
                    new_val = f"{cur_val}-v2"
            else:
                pool = ["frontend", "backend", "worker", "primary", "secondary", "v2", "stable", "canary"]
                alts = [x for x in pool if x != cur_val]
                new_val = rng.choice(alts) if alts else f"{cur_val}2"

        res["metadata"]["labels"][chosen_key] = new_val
        ctx = {"param": param, "key": chosen_key, "value": new_val}
        return res, [f"/metadata/labels/{escape_pointer(chosen_key)}"], ctx


class MutMetaAnnotAdd(BaseOperator):
    id = "MUT-META-ANNOT-ADD"
    area = "metadata"
    applicable_kinds = ["*"]
    params = [
        "prometheus.io/scrape",
        "prometheus.io/port",
        "fluentbit.io/exclude",
        "backup.velero.io/backup-volumes",
        "deployment.timestamp",
        "ci.git/commit-author",
    ]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        return True

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        meta = res.setdefault("metadata", {})
        if not isinstance(meta, dict):
            meta = res["metadata"] = {}
        annots = meta.get("annotations")
        if not isinstance(annots, dict):
            annots = meta["annotations"] = {}

        if context and "value" in context:
            val = context["value"]
        else:
            val_map = {
                "prometheus.io/scrape": "true",
                "prometheus.io/port": "9100",
                "fluentbit.io/exclude": "true",
                "backup.velero.io/backup-volumes": "data",
                "deployment.timestamp": f"2026-10-{rng.randint(10, 28)}T10:00:00Z",
                "ci.git/commit-author": "devops-engineer",
            }
            val = val_map.get(param, "custom-value")

        annots[param] = val
        ctx = {"param": param, "key": param, "value": val}
        return res, [f"/metadata/annotations/{escape_pointer(param)}"], ctx


class MutMetaAnnotRemove(BaseOperator):
    id = "MUT-META-ANNOT-REMOVE"
    area = "metadata"
    applicable_kinds = ["*"]
    params = ["remove_first"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        annots = resource.get("metadata", {}).get("annotations", {})
        return isinstance(annots, dict) and len(annots) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        annots = res.get("metadata", {}).get("annotations", {})
        if not annots:
            return None, [], {}

        if context and context.get("key") in annots:
            chosen_key = context["key"]
        else:
            keys = sorted(annots.keys())
            chosen_key = rng.choice(keys)

        del res["metadata"]["annotations"][chosen_key]
        if not res["metadata"]["annotations"]:
            del res["metadata"]["annotations"]
        ctx = {"param": param, "key": chosen_key}
        return res, [f"/metadata/annotations/{escape_pointer(chosen_key)}"], ctx


class MutMetaPodAnnotAdd(BaseOperator):
    id = "MUT-META-PODANNOT-ADD"
    area = "metadata"
    applicable_kinds = WORKLOAD_KINDS
    params = [
        "sidecar.istio.io/inject",
        "linkerd.io/inject",
        "checksum/config",
    ]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        tmpl, _ = get_pod_template(resource)
        return tmpl is not None

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        tmpl, prefix = get_pod_template(res)
        if tmpl is None:
            return None, [], {}
        t_meta = tmpl.setdefault("metadata", {})
        if not isinstance(t_meta, dict):
            t_meta = tmpl["metadata"] = {}
        annots = t_meta.get("annotations")
        if not isinstance(annots, dict):
            annots = t_meta["annotations"] = {}

        if context and "value" in context:
            val = context["value"]
        else:
            val_map = {
                "sidecar.istio.io/inject": "true",
                "linkerd.io/inject": "enabled",
                "checksum/config": f"hash-{rng.randint(10000, 99999)}",
            }
            val = val_map.get(param, "val")

        annots[param] = val
        ctx = {"param": param, "key": param, "value": val}
        return res, [f"{prefix}/metadata/annotations/{escape_pointer(param)}"], ctx
