import base64
import json
import re
from typing import Any


NAMED_LIST_KEYS = {"containers", "initContainers", "env", "volumes", "ports", "volumeMounts"}


def is_named_list(val_list: list[Any], key_name: str = "") -> bool:
    if not isinstance(val_list, list) or not val_list:
        return False
    if key_name in NAMED_LIST_KEYS:
        return True
    return all(isinstance(item, dict) and "name" in item for item in val_list)


def escape_pointer(segment: str) -> str:
    return str(segment).replace("~", "~0").replace("/", "~1")


def unescape_pointer(segment: str) -> str:
    return str(segment).replace("~1", "/").replace("~0", "~")


def compute_diff(desired: Any, live: Any, current_path: str = "") -> list[dict[str, Any]]:
    diff_ops: list[dict[str, Any]] = []

    if isinstance(desired, dict) and isinstance(live, dict):
        all_keys = list(dict.fromkeys(list(desired.keys()) + list(live.keys())))
        for k in all_keys:
            escaped_k = escape_pointer(k)
            child_path = f"{current_path}/{escaped_k}" if current_path else f"/{escaped_k}"

            val_des = desired.get(k)
            val_live = live.get(k)

            if (k not in desired or val_des is None) and (k in live and val_live is not None):
                diff_ops.append({"op": "add", "path": child_path, "old": None, "new": val_live})
            elif (k in desired and val_des is not None) and (k not in live or val_live is None):
                diff_ops.append({"op": "remove", "path": child_path, "old": val_des, "new": None})
            elif val_des is not None and val_live is not None:
                child_diff = compute_diff(val_des, val_live, child_path)
                diff_ops.extend(child_diff)

    elif isinstance(desired, list) and isinstance(live, list):
        parent_segment = current_path.split("/")[-1] if current_path else ""
        parent_segment = unescape_pointer(parent_segment)
        if is_named_list(desired, parent_segment) or is_named_list(live, parent_segment):
            des_by_name = {
                item["name"]: (idx, item)
                for idx, item in enumerate(desired)
                if isinstance(item, dict) and "name" in item
            }
            live_by_name = {
                item["name"]: (idx, item)
                for idx, item in enumerate(live)
                if isinstance(item, dict) and "name" in item
            }

            for name, (idx, item) in des_by_name.items():
                if name not in live_by_name:
                    diff_ops.append({"op": "remove", "path": f"{current_path}/{idx}", "old": item, "new": None})

            for name, (idx, item) in live_by_name.items():
                if name not in des_by_name:
                    diff_ops.append({"op": "add", "path": f"{current_path}/{idx}", "old": None, "new": item})

            for name in des_by_name:
                if name in live_by_name:
                    idx_des, item_des = des_by_name[name]
                    _, item_live = live_by_name[name]
                    child_diff = compute_diff(item_des, item_live, f"{current_path}/{idx_des}")
                    diff_ops.extend(child_diff)
        elif any(isinstance(x, dict) for x in desired) or any(isinstance(x, dict) for x in live):
            max_len = max(len(desired), len(live))
            for idx in range(max_len):
                sub_path = f"{current_path}/{idx}"
                if idx >= len(desired):
                    diff_ops.append({"op": "add", "path": sub_path, "old": None, "new": live[idx]})
                elif idx >= len(live):
                    diff_ops.append({"op": "remove", "path": sub_path, "old": desired[idx], "new": None})
                else:
                    child_diff = compute_diff(desired[idx], live[idx], sub_path)
                    diff_ops.extend(child_diff)
        else:
            if desired != live:
                diff_ops.append({"op": "replace", "path": current_path, "old": desired, "new": live})
    else:
        if desired != live:
            if desired is None and live is not None:
                diff_ops.append({"op": "add", "path": current_path, "old": None, "new": live})
            elif desired is not None and live is None:
                diff_ops.append({"op": "remove", "path": current_path, "old": desired, "new": None})
            else:
                diff_ops.append({"op": "replace", "path": current_path, "old": desired, "new": live})

    return diff_ops


def _get_container_name_by_index(doc: dict, segments: list[str]) -> str | None:
    try:
        cur = doc
        for i, seg in enumerate(segments):
            if seg in ("containers", "initContainers") and i + 1 < len(segments):
                idx = int(segments[i + 1])
                containers_list = cur.get(seg, [])
                if 0 <= idx < len(containers_list):
                    return str(containers_list[idx].get("name", ""))
            if isinstance(cur, dict):
                cur = cur.get(seg, {})
            elif isinstance(cur, list) and seg.isdigit():
                idx = int(seg)
                if 0 <= idx < len(cur):
                    cur = cur[idx]
                else:
                    return None
            else:
                return None
    except Exception:
        return None
    return None


def format_readable_diff(
    diff_ops: list[dict[str, Any]],
    desired: dict | None = None,
    live: dict | None = None,
    resource_kind: str = "",
) -> list[str]:
    lines = []

    for op_info in diff_ops:
        op = op_info["op"].upper()
        raw_path = op_info["path"]
        old_val = op_info.get("old")
        new_val = op_info.get("new")

        segments = [unescape_pointer(s) for s in raw_path.strip("/").split("/")]

        readable_path_parts = []
        i = 0
        while i < len(segments):
            seg = segments[i]
            if seg in ("containers", "initContainers") and i + 1 < len(segments) and segments[i + 1].isdigit():
                c_idx = int(segments[i + 1])
                c_name = None
                if desired:
                    c_name = _get_container_name_by_index(desired, segments[: i + 2])
                if not c_name and live:
                    c_name = _get_container_name_by_index(live, segments[: i + 2])
                if not c_name:
                    c_name = str(c_idx)
                readable_path_parts.append(f"{seg}[{c_name}]")
                i += 2
                continue
            if seg == "env" and i + 1 < len(segments) and segments[i + 1].isdigit():
                env_idx = int(segments[i + 1])
                readable_path_parts.append(f"env[{env_idx}]")
                i += 2
                continue
            if seg.isdigit() and readable_path_parts:
                readable_path_parts[-1] = f"{readable_path_parts[-1]}[{seg}]"
                i += 1
                continue
            readable_path_parts.append(seg)
            i += 1

        path_str = ".".join(readable_path_parts)

        is_secret_data = resource_kind == "Secret" and (
            raw_path.startswith("/data/") or raw_path.startswith("/stringData/")
        )

        def display_val(v: Any) -> str:
            if v is None:
                return "null"
            if isinstance(v, bool):
                return "true" if v else "false"
            if is_secret_data and isinstance(v, str):
                try:
                    decoded = base64.b64decode(v).decode("utf-8")
                    return json.dumps(decoded, ensure_ascii=False)
                except Exception:
                    pass
            return json.dumps(v, ensure_ascii=False)

        if op == "REPLACE":
            line = f"REPLACE {path_str}: {display_val(old_val)} \u2192 {display_val(new_val)}"
        elif op == "ADD":
            line = f"ADD {path_str}: {display_val(new_val)}"
        elif op == "REMOVE":
            line = f"REMOVE {path_str}: {display_val(old_val)}"
        else:
            line = f"{op} {path_str}"

        lines.append(line)

    return lines
