from abc import ABC, abstractmethod
import copy
import random
from typing import Any


WORKLOAD_KINDS = ["Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job"]


def get_pod_template(resource: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    kind = resource.get("kind", "")
    if kind in ("Deployment", "StatefulSet", "DaemonSet", "Job"):
        spec = resource.get("spec", {})
        if isinstance(spec, dict):
            tmpl = spec.get("template")
            if isinstance(tmpl, dict):
                return tmpl, "/spec/template"
    elif kind == "CronJob":
        spec = resource.get("spec", {})
        if isinstance(spec, dict):
            job_tmpl = spec.get("jobTemplate", {})
            if isinstance(job_tmpl, dict):
                j_spec = job_tmpl.get("spec", {})
                if isinstance(j_spec, dict):
                    tmpl = j_spec.get("template")
                    if isinstance(tmpl, dict):
                        return tmpl, "/spec/jobTemplate/spec/template"
    return None, ""


def get_pod_spec(resource: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    tmpl, prefix = get_pod_template(resource)
    if tmpl is not None:
        p_spec = tmpl.get("spec")
        if isinstance(p_spec, dict):
            return p_spec, f"{prefix}/spec"
    return None, ""


def get_containers(resource: dict[str, Any]) -> list[tuple[int, dict[str, Any], str]]:
    p_spec, prefix = get_pod_spec(resource)
    if p_spec is None:
        return []
    containers = p_spec.get("containers", [])
    if not isinstance(containers, list):
        return []
    res = []
    for idx, c in enumerate(containers):
        if isinstance(c, dict):
            res.append((idx, c, f"{prefix}/containers/{idx}"))
    return res


class BaseOperator(ABC):
    id: str
    area: str
    applicable_kinds: list[str]
    params: list[str]

    def is_applicable(self, resource: dict[str, Any]) -> bool:
        kind = resource.get("kind", "")
        if "*" not in self.applicable_kinds and kind not in self.applicable_kinds:
            return False
        return self._check_applicable(resource)

    @abstractmethod
    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        pass

    @abstractmethod
    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        pass
