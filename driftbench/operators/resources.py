import copy
import random
import re
from typing import Any
from driftbench.operators.base import (
    BaseOperator,
    WORKLOAD_KINDS,
    get_containers,
)


def _parse_cpu_to_millis(val: str) -> int:
    val = str(val).strip()
    if val.endswith("m"):
        return int(float(val[:-1]))
    return int(float(val) * 1000)


def _format_cpu_from_millis(millis: int) -> str:
    millis = max(1, millis)
    if millis % 1000 == 0:
        return str(millis // 1000)
    return f"{millis}m"


def _parse_mem_to_bytes(val: str) -> int:
    val = str(val).strip()
    match = re.match(r"^(\d+)([A-Za-z]+)?$", val)
    if not match:
        return 256 * 1024 * 1024
    num = int(match.group(1))
    unit = match.group(2) or "Mi"
    multipliers = {
        "Ki": 1024,
        "Mi": 1024 * 1024,
        "Gi": 1024 * 1024 * 1024,
        "K": 1000,
        "M": 1000 * 1000,
        "G": 1000 * 1000 * 1000,
    }
    return num * multipliers.get(unit, 1024 * 1024)


def _format_mem(num_bytes: int) -> str:
    mb = max(16, num_bytes // (1024 * 1024))
    if mb % 1024 == 0:
        return f"{mb // 1024}Gi"
    return f"{mb}Mi"


def _scale_cpu(val: str, factor: float) -> str:
    millis = _parse_cpu_to_millis(val)
    new_millis = max(10, int(millis * factor))
    return _format_cpu_from_millis(new_millis)


def _scale_memory(val: str, factor: float) -> str:
    b = _parse_mem_to_bytes(val)
    new_b = max(16 * 1024 * 1024, int(b * factor))
    return _format_mem(new_b)


class MutResLimits(BaseOperator):
    id = "MUT-RES-LIMITS"
    area = "resources"
    applicable_kinds = WORKLOAD_KINDS
    params = ["x0.25", "x4"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        for _, c, _ in containers:
            limits = c.get("resources", {}).get("limits", {})
            if isinstance(limits, dict) and ("cpu" in limits or "memory" in limits):
                return True
        return False

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)

        valid = []
        for idx, c, path in containers:
            limits = c.get("resources", {}).get("limits", {})
            if isinstance(limits, dict) and ("cpu" in limits or "memory" in limits):
                valid.append((idx, c, path))

        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
            c["resources"]["limits"] = copy.deepcopy(context["limits"])
            intended = [f"{path}/resources/limits"]
            if "requests" in context:
                c.setdefault("resources", {})["requests"] = copy.deepcopy(context["requests"])
                intended.append(f"{path}/resources/requests")
            return res, intended, context

        idx, c, path = rng.choice(valid)
        res_block = c.setdefault("resources", {})
        limits = res_block.setdefault("limits", {})
        factor = 0.25 if param == "x0.25" else 4.0

        if "cpu" in limits:
            limits["cpu"] = _scale_cpu(limits["cpu"], factor)
        if "memory" in limits:
            limits["memory"] = _scale_memory(limits["memory"], factor)

        intended = [f"{path}/resources/limits"]
        requests = res_block.get("requests")
        reqs_adjusted = False
        if isinstance(requests, dict):
            if "cpu" in limits and "cpu" in requests:
                lim_m = _parse_cpu_to_millis(limits["cpu"])
                req_m = _parse_cpu_to_millis(requests["cpu"])
                if req_m > lim_m:
                    requests["cpu"] = limits["cpu"]
                    reqs_adjusted = True
            if "memory" in limits and "memory" in requests:
                lim_b = _parse_mem_to_bytes(limits["memory"])
                req_b = _parse_mem_to_bytes(requests["memory"])
                if req_b > lim_b:
                    requests["memory"] = limits["memory"]
                    reqs_adjusted = True

        c_name = c.get("name", str(idx))
        ctx: dict[str, Any] = {"param": param, "container": c_name, "limits": copy.deepcopy(limits)}
        if reqs_adjusted:
            intended.append(f"{path}/resources/requests")
            ctx["requests"] = copy.deepcopy(requests)

        return res, intended, ctx


class MutResRequests(BaseOperator):
    id = "MUT-RES-REQUESTS"
    area = "resources"
    applicable_kinds = WORKLOAD_KINDS
    params = ["x0.25", "x4"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        for _, c, _ in containers:
            reqs = c.get("resources", {}).get("requests", {})
            if isinstance(reqs, dict) and ("cpu" in reqs or "memory" in reqs):
                return True
        return False

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)

        valid = []
        for idx, c, path in containers:
            reqs = c.get("resources", {}).get("requests", {})
            if isinstance(reqs, dict) and ("cpu" in reqs or "memory" in reqs):
                valid.append((idx, c, path))

        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
            c["resources"]["requests"] = copy.deepcopy(context["requests"])
            return res, [f"{path}/resources/requests"], context

        idx, c, path = rng.choice(valid)
        res_block = c.setdefault("resources", {})
        reqs = res_block.setdefault("requests", {})
        limits = res_block.get("limits", {})
        factor = 0.25 if param == "x0.25" else 4.0

        if "cpu" in reqs:
            new_cpu_m = max(10, int(_parse_cpu_to_millis(reqs["cpu"]) * factor))
            if factor > 1.0 and "cpu" in limits:
                limit_cpu_m = _parse_cpu_to_millis(limits["cpu"])
                new_cpu_m = min(new_cpu_m, limit_cpu_m)
            reqs["cpu"] = _format_cpu_from_millis(new_cpu_m)

        if "memory" in reqs:
            new_mem_b = max(16 * 1024 * 1024, int(_parse_mem_to_bytes(reqs["memory"]) * factor))
            if factor > 1.0 and "memory" in limits:
                limit_mem_b = _parse_mem_to_bytes(limits["memory"])
                new_mem_b = min(new_mem_b, limit_mem_b)
            reqs["memory"] = _format_mem(new_mem_b)

        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "requests": copy.deepcopy(reqs)}
        return res, [f"{path}/resources/requests"], ctx


class MutResRemove(BaseOperator):
    id = "MUT-RES-REMOVE"
    area = "resources"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any("resources" in c and c["resources"] for _, c, _ in containers)

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)
        valid = [(idx, c, path) for idx, c, path in containers if "resources" in c and c["resources"]]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
            del c["resources"]
            return res, [f"{path}/resources"], context

        idx, c, path = rng.choice(valid)
        del c["resources"]
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name}
        return res, [f"{path}/resources"], ctx
