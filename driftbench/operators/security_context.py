import copy
import random
from typing import Any
from driftbench.operators.base import (
    BaseOperator,
    WORKLOAD_KINDS,
    get_containers,
)


class MutScPrivileged(BaseOperator):
    id = "MUT-SC-PRIVILEGED"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any((c.get("securityContext") or {}).get("privileged") is not True for _, c, _ in containers)

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)
        valid = [(idx, c, path) for idx, c, path in containers if (c.get("securityContext") or {}).get("privileged") is not True]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
        else:
            idx, c, path = rng.choice(valid)

        sc = c.setdefault("securityContext", {})
        sc["privileged"] = True
        intended_paths = [f"{path}/securityContext/privileged"]

        escalation_changed = False
        if sc.get("allowPrivilegeEscalation") is False:
            sc["allowPrivilegeEscalation"] = True
            intended_paths.append(f"{path}/securityContext/allowPrivilegeEscalation")
            escalation_changed = True

        c_name = c.get("name", str(idx))
        ctx = {"param": param, "value": True, "container": c_name, "privileged": True, "allowPrivilegeEscalation": escalation_changed}
        return res, intended_paths, ctx


class MutScAllowEsc(BaseOperator):
    id = "MUT-SC-ALLOW-ESC"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any((c.get("securityContext") or {}).get("allowPrivilegeEscalation") is not True for _, c, _ in containers)

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)
        valid = [(idx, c, path) for idx, c, path in containers if (c.get("securityContext") or {}).get("allowPrivilegeEscalation") is not True]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
        else:
            idx, c, path = rng.choice(valid)

        sc = c.setdefault("securityContext", {})
        sc["allowPrivilegeEscalation"] = True
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "value": True, "container": c_name, "allowPrivilegeEscalation": True}
        return res, [f"{path}/securityContext/allowPrivilegeEscalation"], ctx


class MutScRunAsRoot(BaseOperator):
    id = "MUT-SC-RUN-AS-ROOT"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["runAsNonRoot_false", "runAsUser_0"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any(
            (c.get("securityContext") or {}).get("runAsUser") != 0
            or (c.get("securityContext") or {}).get("runAsNonRoot") is not False
            for _, c, _ in containers
        )

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

        if param == "runAsNonRoot_false":
            valid = [(idx, c, path) for idx, c, path in containers if (c.get("securityContext") or {}).get("runAsNonRoot") is not False]
        else:
            valid = [(idx, c, path) for idx, c, path in containers if (c.get("securityContext") or {}).get("runAsUser") != 0]

        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
        else:
            idx, c, path = rng.choice(valid)

        sc = c.setdefault("securityContext", {})
        c_name = c.get("name", str(idx))

        if param == "runAsNonRoot_false":
            sc["runAsNonRoot"] = False
            ctx = {"param": param, "value": False, "container": c_name, "runAsNonRoot": False}
            return res, [f"{path}/securityContext/runAsNonRoot"], ctx
        else:
            sc["runAsUser"] = 0
            ctx = {"param": param, "value": 0, "container": c_name, "runAsUser": 0}
            return res, [f"{path}/securityContext/runAsUser"], ctx


class MutScCapsAdd(BaseOperator):
    id = "MUT-SC-CAPS-ADD"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["NET_ADMIN", "SYS_ADMIN", "SYS_MODULE", "NET_BIND_SERVICE"]

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

        valid = [
            (idx, c, path)
            for idx, c, path in containers
            if param not in (c.get("securityContext") or {}).get("capabilities", {}).get("add", [])
        ]
        if not valid:
            valid = containers

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
        else:
            idx, c, path = rng.choice(valid)

        sc = c.setdefault("securityContext", {})
        caps = sc.setdefault("capabilities", {})
        add_list = caps.setdefault("add", [])
        if param not in add_list:
            add_list.append(param)
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "capability": param}
        return res, [f"{path}/securityContext/capabilities/add"], ctx


class MutScCapsDropAll(BaseOperator):
    id = "MUT-SC-CAPS-DROP-ALL"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any(
            (c.get("securityContext") or {}).get("capabilities", {}).get("drop") != ["ALL"]
            for _, c, _ in containers
        )

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)
        valid = [
            (idx, c, path)
            for idx, c, path in containers
            if (c.get("securityContext") or {}).get("capabilities", {}).get("drop") != ["ALL"]
        ]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
        else:
            idx, c, path = rng.choice(valid)

        sc = c.setdefault("securityContext", {})
        caps = sc.setdefault("capabilities", {})
        caps["drop"] = ["ALL"]
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "drop": ["ALL"]}
        return res, [f"{path}/securityContext/capabilities/drop"], ctx


class MutScReadonlyRoot(BaseOperator):
    id = "MUT-SC-READONLY-ROOT"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["true", "false"]

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

        target_val = (param == "true")
        valid = [
            (idx, c, path) for idx, c, path in containers
            if (c.get("securityContext") or {}).get("readOnlyRootFilesystem") != target_val
        ]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
            val = context["readOnlyRootFilesystem"]
        else:
            idx, c, path = rng.choice(valid)
            val = target_val

        sc = c.setdefault("securityContext", {})
        sc["readOnlyRootFilesystem"] = val
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "value": val, "container": c_name, "readOnlyRootFilesystem": val}
        return res, [f"{path}/securityContext/readOnlyRootFilesystem"], ctx


class MutScNonRoot(BaseOperator):
    id = "MUT-SC-NONROOT"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any(
            (c.get("securityContext") or {}).get("runAsNonRoot") is not True
            or (c.get("securityContext") or {}).get("runAsUser") != 10001
            for _, c, _ in containers
        )

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)
        valid = [
            (idx, c, path)
            for idx, c, path in containers
            if (c.get("securityContext") or {}).get("runAsNonRoot") is not True
            or (c.get("securityContext") or {}).get("runAsUser") != 10001
        ]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
        else:
            idx, c, path = rng.choice(valid)

        sc = c.setdefault("securityContext", {})
        sc["runAsNonRoot"] = True
        sc["runAsUser"] = 10001
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "runAsNonRoot": True, "runAsUser": 10001}
        return res, [
            f"{path}/securityContext/runAsNonRoot",
            f"{path}/securityContext/runAsUser",
        ], ctx


class MutScRemove(BaseOperator):
    id = "MUT-SC-REMOVE"
    area = "security_context"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        return any("securityContext" in c and c["securityContext"] for _, c, _ in containers)

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        containers = get_containers(res)
        valid = [(idx, c, path) for idx, c, path in containers if "securityContext" in c and c["securityContext"]]
        if not valid:
            return None, [], {}

        if context and "container" in context:
            matched = [(idx, c, path) for idx, c, path in valid if c.get("name") == context["container"]]
            if matched:
                idx, c, path = matched[0]
            else:
                idx, c, path = valid[0]
        else:
            idx, c, path = rng.choice(valid)

        del c["securityContext"]
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name}
        return res, [f"{path}/securityContext"], ctx
