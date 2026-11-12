import copy
import random
import re
from typing import Any
from driftbench.operators.base import (
    BaseOperator,
    WORKLOAD_KINDS,
    get_pod_spec,
    get_containers,
)


class MutWlReplicas(BaseOperator):
    id = "MUT-WL-REPLICAS"
    area = "workload"
    applicable_kinds = ["Deployment", "StatefulSet"]
    params = ["0", "1", "+1", "x3"]

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
        cur = res.get("spec", {}).get("replicas", 1)
        if cur is None:
            cur = 1

        if context and "value" in context:
            new_val = context["value"]
        else:
            if param == "0":
                if cur == 0:
                    return None, [], {}
                new_val = 0
            elif param == "1":
                if cur == 1:
                    return None, [], {}
                new_val = 1
            elif param == "+1":
                new_val = cur + 1
            elif param == "x3":
                new_val = max(cur * 3, 3)
                if new_val == cur:
                    return None, [], {}
            else:
                new_val = cur + 2

        res["spec"]["replicas"] = new_val
        ctx = {"param": param, "value": new_val}
        return res, ["/spec/replicas"], ctx


class MutWlImage(BaseOperator):
    id = "MUT-WL-IMAGE"
    area = "workload"
    applicable_kinds = WORKLOAD_KINDS
    params = ["latest", "next_patch", "registry", "remove_digest"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        if not containers:
            return False
        for _, c, _ in containers:
            img = c.get("image", "")
            if "@sha256:" in img:
                return True
            if re.search(r":(v?\d+\.\d+\.)(\d+)$", img):
                return True
            if ":" in img and not img.endswith(":latest"):
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
        valid = [(idx, c, path) for idx, c, path in containers if "image" in c]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
            new_img = context["value"]
            c["image"] = new_img
            return res, [f"{path}/image"], context

        if param == "remove_digest":
            with_digest = [(i, c, p) for i, c, p in valid if "@sha256:" in c["image"]]
            if not with_digest:
                return None, [], {}
            idx, c, path = rng.choice(with_digest)
            new_img = c["image"].split("@")[0]

        elif param == "next_patch":
            with_semver = [(i, c, p) for i, c, p in valid if re.search(r":(v?\d+\.\d+\.)(\d+)$", c["image"].split("@")[0])]
            if not with_semver:
                return None, [], {}
            idx, c, path = rng.choice(with_semver)
            base = c["image"].split("@")[0]
            repo, tag = base.rsplit(":", 1)
            match = re.search(r"(\d+)$", tag)
            patch_num = int(match.group(1)) + 1
            new_tag = tag[: match.start(1)] + str(patch_num)
            new_img = f"{repo}:{new_tag}"

        elif param == "latest":
            without_latest = [(i, c, p) for i, c, p in valid if not c["image"].split("@")[0].endswith(":latest")]
            if not without_latest:
                return None, [], {}
            idx, c, path = rng.choice(without_latest)
            base = c["image"].split("@")[0].split(":")[0]
            new_img = f"{base}:latest"

        elif param == "registry":
            idx, c, path = rng.choice(valid)
            base = c["image"].split("@")[0]
            img_no_reg = base.split("/")[-1]
            new_img = f"registry.example.local/{img_no_reg}"
        else:
            return None, [], {}

        c["image"] = new_img
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "value": new_img}
        return res, [f"{path}/image"], ctx


class MutWlPullPolicy(BaseOperator):
    id = "MUT-WL-PULLPOLICY"
    area = "workload"
    applicable_kinds = WORKLOAD_KINDS
    params = ["Always", "IfNotPresent", "Never"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return len(containers) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)
        if not containers:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in containers if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = containers[0]
            c["imagePullPolicy"] = param
            return res, [f"{path}/imagePullPolicy"], context

        valid = [(idx, c, path) for idx, c, path in containers if c.get("imagePullPolicy") != param]
        if not valid:
            return None, [], {}

        idx, c, path = rng.choice(valid)
        c["imagePullPolicy"] = param
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "value": param}
        return res, [f"{path}/imagePullPolicy"], ctx


class MutWlProbeRemove(BaseOperator):
    id = "MUT-WL-PROBE-REMOVE"
    area = "workload"
    applicable_kinds = WORKLOAD_KINDS
    params = ["liveness", "readiness", "startup"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        for _, c, _ in containers:
            if any(f"{p}Probe" in c for p in ("liveness", "readiness", "startup")):
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
        if not containers:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in containers if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
                probe_key = context["probe"]
                if probe_key in c:
                    del c[probe_key]
                    return res, [f"{path}/{probe_key}"], context
            return None, [], {}

        probe_key = f"{param}Probe"
        matched = [(idx, c, path) for idx, c, path in containers if probe_key in c]
        if not matched:
            return None, [], {}

        idx, c, path = rng.choice(matched)
        del c[probe_key]
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "probe": probe_key}
        return res, [f"{path}/{probe_key}"], ctx


class MutWlProbeModify(BaseOperator):
    id = "MUT-WL-PROBE-MODIFY"
    area = "workload"
    applicable_kinds = WORKLOAD_KINDS
    params = ["period_x5", "failure_30", "change_path", "change_port"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        for _, c, _ in containers:
            if any(f"{p}Probe" in c for p in ("liveness", "readiness", "startup")):
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

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in containers if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
                probe_key = context["probe"]
                if probe_key in c and isinstance(c[probe_key], dict):
                    probe = c[probe_key]
                    field = context["field"]
                    val = context["value"]
                    if "/" in field:
                        p1, p2 = field.split("/", 1)
                        probe.setdefault(p1, {})[p2] = val
                    else:
                        probe[field] = val
                    return res, [f"{path}/{probe_key}/{field}"], context
            return None, [], {}

        all_probes = []
        for idx, c, path in containers:
            for p in ("liveness", "readiness", "startup"):
                pk = f"{p}Probe"
                if pk in c and isinstance(c[pk], dict):
                    all_probes.append((idx, c, path, pk))
        if not all_probes:
            return None, [], {}

        idx, c, path, probe_key = rng.choice(all_probes)
        probe = c[probe_key]
        c_name = c.get("name", str(idx))

        if param == "period_x5":
            cur_period = probe.get("periodSeconds", 10)
            new_val = cur_period * 5
            probe["periodSeconds"] = new_val
            field = "periodSeconds"
        elif param == "failure_30":
            new_val = 30
            probe["failureThreshold"] = new_val
            field = "failureThreshold"
        elif param == "change_path":
            if "httpGet" in probe and isinstance(probe["httpGet"], dict):
                new_val = "/healthz"
                probe["httpGet"]["path"] = new_val
                field = "httpGet/path"
            else:
                new_val = 60
                probe["periodSeconds"] = new_val
                field = "periodSeconds"
        elif param == "change_port":
            if "httpGet" in probe and isinstance(probe["httpGet"], dict):
                new_val = 8085
                probe["httpGet"]["port"] = new_val
                field = "httpGet/port"
            elif "tcpSocket" in probe and isinstance(probe["tcpSocket"], dict):
                new_val = 8085
                probe["tcpSocket"]["port"] = new_val
                field = "tcpSocket/port"
            else:
                new_val = 15
                probe["timeoutSeconds"] = new_val
                field = "timeoutSeconds"
        else:
            return None, [], {}

        ctx = {"param": param, "container": c_name, "probe": probe_key, "field": field, "value": new_val}
        return res, [f"{path}/{probe_key}/{field}"], ctx


class MutWlStrategy(BaseOperator):
    id = "MUT-WL-STRATEGY"
    area = "workload"
    applicable_kinds = ["Deployment"]
    params = ["maxUnavailable_100", "maxSurge_0", "recreate"]

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

        if param == "recreate":
            spec["strategy"] = {"type": "Recreate"}
            ctx = {"param": param, "type": "Recreate"}
            return res, ["/spec/strategy"], ctx

        strat = spec.setdefault("strategy", {})
        strat["type"] = "RollingUpdate"
        ru = strat.setdefault("rollingUpdate", {})

        if param == "maxUnavailable_100":
            ru["maxUnavailable"] = "100%"
            ru["maxSurge"] = 1
            ctx = {"param": param, "maxUnavailable": "100%", "maxSurge": 1}
            return res, ["/spec/strategy"], ctx
        elif param == "maxSurge_0":
            ru["maxSurge"] = 0
            ru["maxUnavailable"] = "25%"
            ctx = {"param": param, "maxSurge": 0, "maxUnavailable": "25%"}
            return res, ["/spec/strategy"], ctx

        ctx = {"param": param}
        return res, ["/spec/strategy"], ctx


class MutWlScheduling(BaseOperator):
    id = "MUT-WL-SCHEDULING"
    area = "workload"
    applicable_kinds = WORKLOAD_KINDS
    params = ["node_selector", "toleration_noschedule", "remove_affinity"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        p_spec, _ = get_pod_spec(resource)
        return p_spec is not None

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        p_spec, prefix = get_pod_spec(res)
        if p_spec is None:
            return None, [], {}

        if param == "node_selector":
            ns = p_spec.setdefault("nodeSelector", {})
            ns["disktype"] = "ssd-dedicated"
            ctx = {"param": param, "nodeSelector": {"disktype": "ssd-dedicated"}}
            return res, [f"{prefix}/nodeSelector/disktype"], ctx
        elif param == "toleration_noschedule":
            tols = p_spec.setdefault("tolerations", [])
            item = {"operator": "Exists", "effect": "NoSchedule"}
            tols.append(item)
            idx = len(tols) - 1
            ctx = {"param": param, "index": idx, "toleration": item}
            return res, [f"{prefix}/tolerations/{idx}"], ctx
        elif param == "remove_affinity":
            if "affinity" in p_spec:
                del p_spec["affinity"]
                ctx = {"param": param, "removed": "affinity"}
                return res, [f"{prefix}/affinity"], ctx
            else:
                p_spec["nodeSelector"] = {"zone": "isolated-pool"}
                ctx = {"param": param, "nodeSelector": {"zone": "isolated-pool"}}
                return res, [f"{prefix}/nodeSelector/zone"], ctx
        return None, [], {}
