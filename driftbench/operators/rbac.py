import copy
import random
from typing import Any
from driftbench.operators.base import BaseOperator


class MutRbacVerbWildcard(BaseOperator):
    id = "MUT-RBAC-VERB-WILDCARD"
    area = "rbac"
    applicable_kinds = ["Role", "ClusterRole"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        rules = resource.get("rules", [])
        return isinstance(rules, list) and len(rules) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        rules = res.get("rules", [])
        if not rules:
            return None, [], {}

        if context and "index" in context and 0 <= context["index"] < len(rules):
            idx = context["index"]
        else:
            idx = rng.randint(0, len(rules) - 1)

        rules[idx]["verbs"] = ["*"]
        ctx = {"param": param, "index": idx, "verbs": ["*"]}
        return res, [f"/rules/{idx}/verbs"], ctx


class MutRbacResWildcard(BaseOperator):
    id = "MUT-RBAC-RES-WILDCARD"
    area = "rbac"
    applicable_kinds = ["Role", "ClusterRole"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        rules = resource.get("rules", [])
        return isinstance(rules, list) and len(rules) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        rules = res.get("rules", [])
        if not rules:
            return None, [], {}

        if context and "index" in context and 0 <= context["index"] < len(rules):
            idx = context["index"]
        else:
            idx = rng.randint(0, len(rules) - 1)

        rules[idx]["resources"] = ["*"]
        ctx = {"param": param, "index": idx, "resources": ["*"]}
        return res, [f"/rules/{idx}/resources"], ctx


class MutRbacAddRule(BaseOperator):
    id = "MUT-RBAC-ADD-RULE"
    area = "rbac"
    applicable_kinds = ["Role", "ClusterRole"]
    params = ["secrets", "pods_exec", "configmaps"]

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
        rules = res.setdefault("rules", [])

        rule_map = {
            "secrets": {
                "apiGroups": [""],
                "resources": ["secrets"],
                "verbs": ["get", "list", "watch"],
            },
            "pods_exec": {
                "apiGroups": [""],
                "resources": ["pods/exec"],
                "verbs": ["create"],
            },
            "configmaps": {
                "apiGroups": [""],
                "resources": ["configmaps"],
                "verbs": ["get", "list"],
            },
        }
        new_rule = rule_map.get(
            param,
            {
                "apiGroups": [""],
                "resources": ["configmaps"],
                "verbs": ["get"],
            },
        )
        idx = len(rules)
        rules.append(copy.deepcopy(new_rule))
        ctx = {"param": param, "index": idx, "rule": new_rule}
        return res, [f"/rules/{idx}"], ctx


class MutRbacRuleRemove(BaseOperator):
    id = "MUT-RBAC-RULE-REMOVE"
    area = "rbac"
    applicable_kinds = ["Role", "ClusterRole"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        rules = resource.get("rules", [])
        return isinstance(rules, list) and len(rules) >= 2

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        rules = res.get("rules", [])
        if not rules or len(rules) < 2:
            return None, [], {}

        if context and "index" in context and 0 <= context["index"] < len(rules):
            idx = context["index"]
        else:
            idx = rng.randint(0, len(rules) - 1)

        del rules[idx]
        ctx = {"param": param, "index": idx}
        return res, [f"/rules/{idx}"], ctx


class MutRbacSubjectAdd(BaseOperator):
    id = "MUT-RBAC-SUBJECT-ADD"
    area = "rbac"
    applicable_kinds = ["RoleBinding", "ClusterRoleBinding"]
    params = ["default_sa", "system_auth"]

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
        subjects = res.setdefault("subjects", [])
        ns = res.get("metadata", {}).get("namespace", "default")

        if param == "default_sa":
            new_subj = {
                "kind": "ServiceAccount",
                "name": "default",
                "namespace": ns,
            }
        else:
            new_subj = {
                "kind": "Group",
                "name": "system:authenticated",
                "apiGroup": "rbac.authorization.k8s.io",
            }

        idx = len(subjects)
        subjects.append(new_subj)
        ctx = {"param": param, "index": idx, "subject": new_subj}
        return res, [f"/subjects/{idx}"], ctx


class MutRbacRoleRefAdmin(BaseOperator):
    id = "MUT-RBAC-ROLEREF-ADMIN"
    area = "rbac"
    applicable_kinds = ["RoleBinding", "ClusterRoleBinding"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        return "roleRef" in resource

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        role_ref = res.setdefault("roleRef", {})
        role_ref["name"] = "cluster-admin"
        ctx = {"param": param, "roleRef": "cluster-admin"}
        return res, ["/roleRef/name"], ctx
