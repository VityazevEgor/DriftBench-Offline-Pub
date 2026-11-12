import copy
import random
from typing import Any
from driftbench.diff import escape_pointer
from driftbench.operators.base import BaseOperator


class MutSvcPort(BaseOperator):
    id = "MUT-SVC-PORT"
    area = "network"
    applicable_kinds = ["Service"]
    params = ["port", "targetPort"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        ports = resource.get("spec", {}).get("ports", [])
        return isinstance(ports, list) and len(ports) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        ports = res.get("spec", {}).get("ports", [])
        if not ports:
            return None, [], {}
        port_item = ports[0]

        if context and "value" in context:
            new_val = context["value"]
            if param == "port":
                port_item["port"] = new_val
                return res, ["/spec/ports/0/port"], context
            else:
                port_item["targetPort"] = new_val
                return res, ["/spec/ports/0/targetPort"], context

        if param == "port":
            cur = port_item.get("port", 80)
            new_val = cur + 1000
            port_item["port"] = new_val
            ctx = {"param": param, "field": "port", "value": new_val}
            return res, ["/spec/ports/0/port"], ctx
        else:
            cur = port_item.get("targetPort", 8080)
            if isinstance(cur, int):
                new_val = cur + 1000
            else:
                new_val = 9099
            port_item["targetPort"] = new_val
            ctx = {"param": param, "field": "targetPort", "value": new_val}
            return res, ["/spec/ports/0/targetPort"], ctx


class MutSvcType(BaseOperator):
    id = "MUT-SVC-TYPE"
    area = "network"
    applicable_kinds = ["Service"]
    params = ["NodePort", "LoadBalancer"]

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
        cur = spec.get("type", "ClusterIP")
        if cur == param:
            return None, [], {}
        new_type = param

        if context and "type" in context:
            new_type = context["type"]

        spec["type"] = new_type
        if spec.get("clusterIP") == "None":
            del spec["clusterIP"]
        if "clusterIPs" in spec:
            del spec["clusterIPs"]

        ctx = {"param": param, "value": new_type, "type": new_type}
        return res, ["/spec/type"], ctx


class MutSvcSelector(BaseOperator):
    id = "MUT-SVC-SELECTOR"
    area = "network"
    applicable_kinds = ["Service"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        sel = resource.get("spec", {}).get("selector", {})
        return isinstance(sel, dict) and len(sel) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        sel = res.get("spec", {}).get("selector", {})
        if not sel:
            return None, [], {}

        if context and context.get("key") in sel:
            chosen_key = context["key"]
            new_val = context["value"]
        else:
            keys = sorted(sel.keys())
            chosen_key = rng.choice(keys)
            cur_val = str(sel[chosen_key])
            if "master" in cur_val:
                new_val = cur_val.replace("master", "replicas")
            elif "redis" in cur_val:
                new_val = "redis-replicas"
            elif "nginx" in cur_val:
                new_val = "nginx-backend"
            else:
                new_val = f"{cur_val}-v2"

        sel[chosen_key] = new_val
        ctx = {"param": param, "key": chosen_key, "value": new_val}
        return res, [f"/spec/selector/{escape_pointer(chosen_key)}"], ctx


class MutIngHost(BaseOperator):
    id = "MUT-ING-HOST"
    area = "network"
    applicable_kinds = ["Ingress"]
    params = ["modify_host", "add_rule"]

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
        rules = spec.setdefault("rules", [])

        if param == "modify_host" and rules:
            rule = rules[0]
            if context and "host" in context:
                new_host = context["host"]
            else:
                cur = rule.get("host", "example.com")
                new_host = f"api.{cur}" if not cur.startswith("api.") else f"ext.{cur}"
            rule["host"] = new_host
            ctx = {"param": param, "host": new_host}
            return res, ["/spec/rules/0/host"], ctx
        else:
            new_idx = len(rules)
            if context and "host" in context:
                new_host = context["host"]
            else:
                new_host = f"gateway-{rng.randint(10, 99)}.internal.domain"
            rule_entry = {
                "host": new_host,
                "http": {
                    "paths": [
                        {
                            "path": "/api",
                            "pathType": "Prefix",
                            "backend": {
                                "service": {
                                    "name": "nginx",
                                    "port": {"number": 80},
                                }
                            },
                        }
                    ]
                },
            }
            rules.append(rule_entry)
            ctx = {"param": param, "index": new_idx, "host": new_host}
            return res, [f"/spec/rules/{new_idx}"], ctx


class MutIngPath(BaseOperator):
    id = "MUT-ING-PATH"
    area = "network"
    applicable_kinds = ["Ingress"]
    params = ["change_path", "change_path_type"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        rules = resource.get("spec", {}).get("rules", [])
        for r in rules:
            paths = r.get("http", {}).get("paths", [])
            if paths:
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
        rules = res.get("spec", {}).get("rules", [])
        for r_idx, r in enumerate(rules):
            paths = r.get("http", {}).get("paths", [])
            if paths:
                p_item = paths[0]
                if param == "change_path":
                    new_path = context["path"] if (context and "path" in context) else "/api/v1"
                    p_item["path"] = new_path
                    ctx = {"param": param, "path": new_path}
                    return res, [f"/spec/rules/{r_idx}/http/paths/0/path"], ctx
                else:
                    cur = p_item.get("pathType", "Prefix")
                    new_pt = "Exact" if cur == "Prefix" else "Prefix"
                    if context and "pathType" in context:
                        new_pt = context["pathType"]
                    p_item["pathType"] = new_pt
                    ctx = {"param": param, "pathType": new_pt}
                    return res, [f"/spec/rules/{r_idx}/http/paths/0/pathType"], ctx
        return None, [], {}


class MutIngAnnot(BaseOperator):
    id = "MUT-ING-ANNOT"
    area = "network"
    applicable_kinds = ["Ingress"]
    params = ["ssl_redirect", "whitelist", "proxy_body_size"]

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
        annots = meta.setdefault("annotations", {})

        annot_map = {
            "ssl_redirect": ("nginx.ingress.kubernetes.io/ssl-redirect", "false"),
            "whitelist": ("nginx.ingress.kubernetes.io/whitelist-source-range", "0.0.0.0/0"),
            "proxy_body_size": ("nginx.ingress.kubernetes.io/proxy-body-size", "100m"),
        }
        k, v = annot_map.get(param, ("nginx.ingress.kubernetes.io/ssl-redirect", "false"))
        annots[k] = v
        ctx = {"param": param, "key": k, "value": v}
        return res, [f"/metadata/annotations/{escape_pointer(k)}"], ctx


class MutNpAllowAll(BaseOperator):
    id = "MUT-NP-ALLOW-ALL"
    area = "network"
    applicable_kinds = ["NetworkPolicy"]
    params = ["ingress", "egress"]

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
        if param == "ingress":
            spec["ingress"] = [{}]
            ctx = {"param": param, "direction": "ingress"}
            return res, ["/spec/ingress"], ctx
        else:
            spec["egress"] = [{}]
            ctx = {"param": param, "direction": "egress"}
            return res, ["/spec/egress"], ctx


class MutNpRuleRemove(BaseOperator):
    id = "MUT-NP-RULE-REMOVE"
    area = "network"
    applicable_kinds = ["NetworkPolicy"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        spec = resource.get("spec", {})
        ing = spec.get("ingress", [])
        egr = spec.get("egress", [])
        return (isinstance(ing, list) and len(ing) > 0) or (isinstance(egr, list) and len(egr) > 0)

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        spec = res.get("spec", {})
        ing = spec.get("ingress", [])
        egr = spec.get("egress", [])

        if context and "direction" in context:
            d = context["direction"]
            idx = context["index"]
            target = spec.get(d, [])
            if 0 <= idx < len(target):
                del target[idx]
                return res, [f"/spec/{d}"], context

        if isinstance(ing, list) and len(ing) > 0:
            idx = rng.randint(0, len(ing) - 1)
            del ing[idx]
            ctx = {"param": param, "direction": "ingress", "index": idx}
            return res, ["/spec/ingress"], ctx
        elif isinstance(egr, list) and len(egr) > 0:
            idx = rng.randint(0, len(egr) - 1)
            del egr[idx]
            ctx = {"param": param, "direction": "egress", "index": idx}
            return res, ["/spec/egress"], ctx
        return None, [], {}


class MutNpRuleAdd(BaseOperator):
    id = "MUT-NP-RULE-ADD"
    area = "network"
    applicable_kinds = ["NetworkPolicy"]
    params = ["default"]

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
        ing = spec.setdefault("ingress", [])

        if context and "label_value" in context:
            l_val = context["label_value"]
        else:
            pool = ["ingress-nginx", "monitoring", "api-gateway", "frontend-proxy"]
            l_val = rng.choice(pool)

        new_rule = {
            "from": [
                {
                    "podSelector": {
                        "matchLabels": {"app.kubernetes.io/name": l_val}
                    }
                }
            ]
        }
        new_idx = len(ing)
        ing.append(new_rule)
        ctx = {"param": param, "index": new_idx, "label_value": l_val}
        return res, [f"/spec/ingress/{new_idx}"], ctx
