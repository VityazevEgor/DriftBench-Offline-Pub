import base64
import copy
import random
import re
from typing import Any
from driftbench.diff import escape_pointer
from driftbench.operators.base import (
    BaseOperator,
    WORKLOAD_KINDS,
    get_containers,
)


def _mutate_realistic_value(cur_val: str, rng: random.Random) -> str:
    cur = str(cur_val).strip()
    if cur.lower() in ("true", "yes", "on", "1"):
        return "false"
    if cur.lower() in ("false", "no", "off", "0"):
        return "true"

    if cur.isdigit():
        num = int(cur)
        if num in (80, 8080):
            return "8085"
        if num == 0:
            return "1"
        return str(num * 2 if num < 500 else num + 100)

    if cur.lower() in ("debug", "info", "warn", "warning", "error"):
        pool = ["debug", "info", "warn", "error"]
        alts = [x for x in pool if x != cur.lower()]
        return rng.choice(alts)

    if ":" in cur and not cur.startswith("http"):
        parts = cur.split(":")
        if parts[-1].isdigit():
            return f"{parts[0]}:8085"

    if cur.startswith("/"):
        if cur.startswith("/tmp"):
            return "/var/log"
        return "/etc/custom"

    pool = ["production", "staging", "internal", "primary", "secondary", "disabled", "enabled"]
    alts = [x for x in pool if x.lower() != cur.lower()]
    return rng.choice(alts) if alts else f"{cur}-alt"


class MutCfgEnvChange(BaseOperator):
    id = "MUT-CFG-ENV-CHANGE"
    area = "config"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        for _, c, _ in containers:
            env_list = c.get("env") or []
            if any(isinstance(e, dict) and "value" in e for e in env_list):
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
            env_list = c.get("env") or []
            for e_idx, e in enumerate(env_list):
                if isinstance(e, dict) and "value" in e:
                    valid.append((idx, c, path, e_idx, e))
        if not valid:
            return None, [], {}

        if context and "container" in context and "env_name" in context:
            matched = [
                (idx, c, path, e_idx, e)
                for idx, c, path, e_idx, e in valid
                if c.get("name") == context["container"] and e.get("name") == context["env_name"]
            ]
            if matched:
                idx, c, path, e_idx, env_item = matched[0]
                env_item["value"] = context["value"]
                return res, [f"{path}/env/{e_idx}/value"], context

        idx, c, path, e_idx, env_item = rng.choice(valid)
        orig_val = str(env_item["value"])
        new_val = _mutate_realistic_value(orig_val, rng)
        env_item["value"] = new_val
        c_name = c.get("name", str(idx))
        e_name = env_item.get("name", str(e_idx))
        ctx = {"param": param, "container": c_name, "env_name": e_name, "value": new_val}
        return res, [f"{path}/env/{e_idx}/value"], ctx


class MutCfgEnvAdd(BaseOperator):
    id = "MUT-CFG-ENV-ADD"
    area = "config"
    applicable_kinds = WORKLOAD_KINDS
    params = ["LOG_LEVEL", "FEATURE_FLAG_X", "DB_PASSWORD", "API_TOKEN"]

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
            var_name = context["var_name"]
            val = context["value"]
            env_list = c.setdefault("env", [])
            new_idx = len(env_list)
            env_list.append({"name": var_name, "value": val})
            return res, [f"{path}/env/{new_idx}"], context

        idx, c, path = rng.choice(containers)
        env_list = c.setdefault("env", [])
        if not isinstance(env_list, list):
            env_list = c["env"] = []

        val_map = {
            "LOG_LEVEL": "debug",
            "FEATURE_FLAG_X": "true",
            "DB_PASSWORD": f"pass-{rng.randint(1000, 9999)}",
            "API_TOKEN": f"tok-{rng.randint(1000, 9999)}",
        }
        val = val_map.get(param, "custom-val")

        existing_names = {e.get("name") for e in env_list if isinstance(e, dict)}
        var_name = param if param not in existing_names else f"{param}_CUSTOM"

        new_idx = len(env_list)
        env_list.append({"name": var_name, "value": val})
        c_name = c.get("name", str(idx))
        ctx = {"param": param, "container": c_name, "var_name": var_name, "value": val}
        return res, [f"{path}/env/{new_idx}"], ctx


class MutCfgEnvRemove(BaseOperator):
    id = "MUT-CFG-ENV-REMOVE"
    area = "config"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        for _, c, _ in containers:
            env_list = c.get("env") or []
            if isinstance(env_list, list) and len(env_list) > 0:
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
            env_list = c.get("env") or []
            for e_idx, e in enumerate(env_list):
                if isinstance(e, dict):
                    valid.append((idx, c, path, e_idx, e))
        if not valid:
            return None, [], {}

        if context and "container" in context and "env_name" in context:
            matched = [
                (idx, c, path, e_idx, e)
                for idx, c, path, e_idx, e in valid
                if c.get("name") == context["container"] and e.get("name") == context["env_name"]
            ]
            if matched:
                idx, c, path, e_idx, env_item = matched[0]
                del c["env"][e_idx]
                return res, [f"{path}/env/{e_idx}"], context

        idx, c, path, e_idx, env_item = rng.choice(valid)
        c_name = c.get("name", str(idx))
        e_name = env_item.get("name", str(e_idx))
        del c["env"][e_idx]
        ctx = {"param": param, "container": c_name, "env_name": e_name}
        return res, [f"{path}/env/{e_idx}"], ctx


class MutCfgSecretRefChange(BaseOperator):
    id = "MUT-CFG-SECRETREF-CHANGE"
    area = "config"
    applicable_kinds = WORKLOAD_KINDS
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        containers = get_containers(resource)
        for _, c, _ in containers:
            for e in (c.get("env") or []):
                if isinstance(e, dict) and "valueFrom" in e and isinstance(e["valueFrom"], dict) and "secretKeyRef" in e["valueFrom"]:
                    return True
            for ef in (c.get("envFrom") or []):
                if isinstance(ef, dict) and "secretRef" in ef:
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
        refs = []
        for idx, c, path in containers:
            for e_idx, e in enumerate(c.get("env") or []):
                if isinstance(e, dict) and "valueFrom" in e and isinstance(e["valueFrom"], dict) and "secretKeyRef" in e["valueFrom"]:
                    refs.append(("env", idx, c, path, e_idx, e["valueFrom"]["secretKeyRef"]))
            for ef_idx, ef in enumerate(c.get("envFrom") or []):
                if isinstance(ef, dict) and "secretRef" in ef:
                    refs.append(("envFrom", idx, c, path, ef_idx, ef["secretRef"]))
        if not refs:
            return None, [], {}

        if context and "target_secret" in context:
            ref_type, idx, c, path, item_idx, sref = refs[0]
            sref["name"] = context["target_secret"]
            ret_path = f"{path}/env/{item_idx}/valueFrom/secretKeyRef/name" if ref_type == "env" else f"{path}/envFrom/{item_idx}/secretRef/name"
            return res, [ret_path], context

        ref_type, idx, c, path, item_idx, sref = rng.choice(refs)
        old_name = sref.get("name", "app-secret")
        new_name = "app-credentials-secret" if old_name != "app-credentials-secret" else "system-auth-secret"
        sref["name"] = new_name
        ctx = {"param": param, "target_secret": new_name}
        if ref_type == "env":
            return res, [f"{path}/env/{item_idx}/valueFrom/secretKeyRef/name"], ctx
        else:
            return res, [f"{path}/envFrom/{item_idx}/secretRef/name"], ctx


class MutCfgCmChange(BaseOperator):
    id = "MUT-CFG-CM-CHANGE"
    area = "config"
    applicable_kinds = ["ConfigMap"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        data = resource.get("data", {})
        return isinstance(data, dict) and len(data) > 0

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        data = res.get("data", {})
        if not data:
            return None, [], {}

        if context and context.get("key") in data:
            chosen_key = context["key"]
            new_val = context["value"]
        else:
            keys = sorted(data.keys())
            chosen_key = rng.choice(keys)
            cur_val = str(data[chosen_key])

            if "\n" in cur_val:
                lines = cur_val.split("\n")
                changed = False
                new_lines = []
                for line in lines:
                    if not changed and any(re.search(rf"\b{kw}\b", line, re.I) for kw in ("max_connections", "listen", "timeout", "workers", "port")):
                        if re.search(r"\d+", line):
                            line = re.sub(r"(\d+)", lambda m: str(int(m.group(1)) + 10), line, count=1)
                            changed = True
                    new_lines.append(line)
                if not changed:
                    new_lines.append("# configuration updated")
                new_val = "\n".join(new_lines)
            else:
                new_val = _mutate_realistic_value(cur_val, rng)

            if new_val == cur_val:
                new_val = cur_val + "\n# configuration updated"

        data[chosen_key] = new_val
        ctx = {"param": param, "key": chosen_key, "value": new_val}
        return res, [f"/data/{escape_pointer(chosen_key)}"], ctx


class MutCfgCmAdd(BaseOperator):
    id = "MUT-CFG-CM-ADD"
    area = "config"
    applicable_kinds = ["ConfigMap"]
    params = ["log.level", "password", "aws_secret_access_key"]

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
        data = res.get("data")
        if not isinstance(data, dict):
            data = res["data"] = {}

        if context and "value" in context:
            val = context["value"]
        else:
            val_map = {
                "log.level": "debug",
                "password": f"plain-pass-{rng.randint(100, 999)}",
                "aws_secret_access_key": f"AKIA{rng.randint(100000, 999999)}EXAMPLE",
            }
            val = val_map.get(param, "custom_val")

        data[param] = val
        ctx = {"param": param, "key": param, "value": val}
        return res, [f"/data/{escape_pointer(param)}"], ctx


class MutCfgSecretChange(BaseOperator):
    id = "MUT-CFG-SECRET-CHANGE"
    area = "config"
    applicable_kinds = ["Secret"]
    params = ["default"]

    def _check_applicable(self, resource: dict[str, Any]) -> bool:
        data = resource.get("data", {})
        str_data = resource.get("stringData", {})
        return (isinstance(data, dict) and len(data) > 0) or (
            isinstance(str_data, dict) and len(str_data) > 0
        )

    def apply(
        self,
        resource: dict[str, Any],
        param: str,
        rng: random.Random,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str], dict[str, Any]]:
        res = copy.deepcopy(resource)
        if "data" in res and isinstance(res["data"], dict) and res["data"]:
            if context and context.get("key") in res["data"]:
                chosen_key = context["key"]
                new_encoded = context["value"]
            else:
                keys = sorted(res["data"].keys())
                non_crt = [k for k in keys if not k.endswith(".crt")]
                chosen_key = rng.choice(non_crt) if non_crt else rng.choice(keys)
                secret_options = [b"P@ssw0rd2026!Secur3", b"Sup3rK8sAdm1n#99", b"DbAcc3ssT0k3n_42"]
                new_encoded = base64.b64encode(rng.choice(secret_options)).decode("ascii")

            res["data"][chosen_key] = new_encoded
            ctx = {"param": param, "key": chosen_key, "value": new_encoded}
            return res, [f"/data/{escape_pointer(chosen_key)}"], ctx

        elif "stringData" in res and isinstance(res["stringData"], dict) and res["stringData"]:
            keys = sorted(res["stringData"].keys())
            chosen_key = rng.choice(keys)
            new_val = "P@ssw0rd2026!Secur3"
            res["stringData"][chosen_key] = new_val
            ctx = {"param": param, "key": chosen_key, "value": new_val}
            return res, [f"/stringData/{escape_pointer(chosen_key)}"], ctx
        return None, [], {}
