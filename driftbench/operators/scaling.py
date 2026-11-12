import copy
import random
from typing import Any
from driftbench.operators.base import BaseOperator


class MutScaleHpa(BaseOperator):
    id = "MUT-SCALE-HPA"
    area = "scaling"
    applicable_kinds = ["HorizontalPodAutoscaler"]
    params = ["min_max_1", "max_x5", "target_cpu_95"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        return "spec" in resource

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        spec = res.setdefault("spec", {})

        if param == "min_max_1":
            if spec.get("minReplicas") == 1 and spec.get("maxReplicas") == 1:
                return None, [], {}
            spec["minReplicas"] = 1
            spec["maxReplicas"] = 1
            ctx = {"param": param, "value": 1, "minReplicas": 1, "maxReplicas": 1}
            return res, ["/spec/minReplicas", "/spec/maxReplicas"], ctx
        elif param == "max_x5":
            if context and "maxReplicas" in context:
                new_max = context["maxReplicas"]
            else:
                cur_max = spec.get("maxReplicas", 2)
                new_max = cur_max * 5
            spec["maxReplicas"] = new_max
            ctx = {"param": param, "maxReplicas": new_max}
            return res, ["/spec/maxReplicas"], ctx
        elif param == "target_cpu_95":
            if "targetCPUUtilizationPercentage" in spec:
                spec["targetCPUUtilizationPercentage"] = 95
                ctx = {"param": param, "targetCPUUtilizationPercentage": 95}
                return res, ["/spec/targetCPUUtilizationPercentage"], ctx
            elif "metrics" in spec and isinstance(spec["metrics"], list):
                for idx, m in enumerate(spec["metrics"]):
                    if m.get("type") == "Resource":
                        r_target = m.get("resource", {}).get("target", {})
                        if "averageUtilization" in r_target:
                            r_target["averageUtilization"] = 95
                            ctx = {"param": param, "metricIndex": idx, "averageUtilization": 95}
                            return res, [f"/spec/metrics/{idx}/resource/target/averageUtilization"], ctx
                spec["targetCPUUtilizationPercentage"] = 95
                ctx = {"param": param, "targetCPUUtilizationPercentage": 95}
                return res, ["/spec/targetCPUUtilizationPercentage"], ctx
            else:
                spec["targetCPUUtilizationPercentage"] = 95
                ctx = {"param": param, "targetCPUUtilizationPercentage": 95}
                return res, ["/spec/targetCPUUtilizationPercentage"], ctx
        return None, [], {}


class MutScalePdb(BaseOperator):
    id = "MUT-SCALE-PDB"
    area = "scaling"
    applicable_kinds = ["PodDisruptionBudget"]
    params = ["minAvailable_0", "maxUnavailable_100"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        return "spec" in resource

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        spec = res.setdefault("spec", {})

        if param == "minAvailable_0":
            if spec.get("minAvailable") == 0 and "maxUnavailable" not in spec:
                return None, [], {}
            spec["minAvailable"] = 0
            if "maxUnavailable" in spec:
                del spec["maxUnavailable"]
                ctx = {"param": param, "value": 0, "minAvailable": 0}
                return res, ["/spec/minAvailable", "/spec/maxUnavailable"], ctx
            ctx = {"param": param, "value": 0, "minAvailable": 0}
            return res, ["/spec/minAvailable"], ctx
        else:
            if spec.get("maxUnavailable") in ("100%", 100) and "minAvailable" not in spec:
                return None, [], {}
            spec["maxUnavailable"] = "100%"
            if "minAvailable" in spec:
                del spec["minAvailable"]
                ctx = {"param": param, "value": "100%", "maxUnavailable": "100%"}
                return res, ["/spec/maxUnavailable", "/spec/minAvailable"], ctx
            ctx = {"param": param, "value": "100%", "maxUnavailable": "100%"}
            return res, ["/spec/maxUnavailable"], ctx
