import copy
import random
from typing import Any
from driftbench.operators.base import (
    BaseOperator,
    WORKLOAD_KINDS,
    get_pod_spec,
    get_containers,
)

REAL_OTHER_APP_SAS = [
    "redis-master",
    "postgresql",
    "rabbitmq",
    "kube-state-metrics",
    "prometheus-node-exporter",
]


class MutPodHostNs(BaseOperator):
    id = "MUT-POD-HOST-NS"
    area = "pod_spec"
    applicable_kinds = WORKLOAD_KINDS
    params = ["hostNetwork", "hostPID", "hostIPC"]

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
        if p_spec.get(param) is True:
            return None, [], {}
        p_spec[param] = True
        ctx = {"param": param, "value": True}
        return res, [f"{prefix}/{param}"], ctx


class MutPodHostPath(BaseOperator):
    id = "MUT-POD-HOSTPATH"
    area = "pod_spec"
    applicable_kinds = WORKLOAD_KINDS
    params = ["/var/run/docker.sock", "/proc", "/etc", "/tmp/cache"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        p_spec, _ = get_pod_spec(resource)
        containers = get_containers(resource)
        return p_spec is not None and len(containers) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        p_spec, prefix = get_pod_spec(res)
        containers = get_containers(res)
        if p_spec is None or not containers:
            return None, [], {}

        vol_name = "hostpath-volume"
        volumes = p_spec.setdefault("volumes", [])
        vol_idx = len(volumes)
        volumes.append({
            "name": vol_name,
            "hostPath": {"path": param},
        })

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in containers if c.get("name") == context["container"]]
            if matched:
                idx, c, c_path = matched[0]
            else:
                idx, c, c_path = containers[0]
        else:
            idx, c, c_path = rng.choice(containers)

        mounts = c.setdefault("volumeMounts", [])
        mount_idx = len(mounts)
        mount_path = f"/mnt/host-{param.strip('/').replace('/', '-')}"
        mounts.append({
            "name": vol_name,
            "mountPath": mount_path,
        })

        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "mountPath": mount_path}
        return res, [
            f"{prefix}/volumes/{vol_idx}",
            f"{c_path}/volumeMounts/{mount_idx}",
        ], ctx


class MutPodHostPort(BaseOperator):
    id = "MUT-POD-HOSTPORT"
    area = "pod_spec"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any("ports" in c and c["ports"] for _, c, _ in containers)

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
            for p_idx, port_item in enumerate(c.get("ports", [])):
                if isinstance(port_item, dict) and "containerPort" in port_item:
                    valid.append((idx, c, path, p_idx, port_item))
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [
                (idx, c, path, p_idx, port_item)
                for idx, c, path, p_idx, port_item in valid
                if c.get("name") == context["container"]
            ]
            if matched:
                idx, c, path, p_idx, port_item = matched[0]
            else:
                idx, c, path, p_idx, port_item = valid[0]
        else:
            idx, c, path, p_idx, port_item = rng.choice(valid)

        port_item["hostPort"] = 8088
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "portIndex": p_idx, "hostPort": 8088}
        return res, [f"{path}/ports/{p_idx}/hostPort"], ctx


class MutPodSaChange(BaseOperator):
    id = "MUT-POD-SA-CHANGE"
    area = "pod_spec"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default", "other_app"]

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

        cur_sa = p_spec.get("serviceAccountName", "")
        if context and "serviceAccountName" in context:
            new_sa = context["serviceAccountName"]
        else:
            if param == "default":
                if cur_sa == "default":
                    return None, [], {}
                new_sa = "default"
            else:
                res_name = res.get("metadata", {}).get("name", "")
                candidates = [sa for sa in REAL_OTHER_APP_SAS if sa not in res_name and sa != cur_sa]
                if not candidates:
                    return None, [], {}
                new_sa = rng.choice(candidates)

        p_spec["serviceAccountName"] = new_sa
        ctx = {"param": param, "value": new_sa, "serviceAccountName": new_sa}
        return res, [f"{prefix}/serviceAccountName"], ctx


class MutPodAutomount(BaseOperator):
    id = "MUT-POD-AUTOMOUNT"
    area = "pod_spec"
    applicable_kinds = WORKLOAD_KINDS
    params = ["true", "false"]

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

        target_val = (param == "true")
        if context and "automount" in context:
            val = context["automount"]
        else:
            cur = p_spec.get("automountServiceAccountToken")
            if cur == target_val:
                return None, [], {}
            val = target_val

        p_spec["automountServiceAccountToken"] = val
        ctx = {"param": param, "value": val, "automount": val}
        return res, [f"{prefix}/automountServiceAccountToken"], ctx
