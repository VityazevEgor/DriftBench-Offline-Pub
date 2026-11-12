import pytest
from driftbench.diff import compute_diff, format_readable_diff


def test_empty_diff():
    obj = {"metadata": {"name": "test", "labels": {"app": "demo"}}}
    assert compute_diff(obj, obj) == []


def test_add_remove_replace_dict():
    desired = {"a": 1, "b": "old", "c": 3, "null_key": None}
    live = {"a": 1, "b": "new", "d": 4, "null_key": {"nested": "value"}}

    diffs = compute_diff(desired, live)
    ops = {d["path"]: (d["op"], d["old"], d["new"]) for d in diffs}

    assert "/b" in ops and ops["/b"] == ("replace", "old", "new")
    assert "/c" in ops and ops["/c"] == ("remove", 3, None)
    assert "/d" in ops and ops["/d"] == ("add", None, 4)
    # A5: Field with None/null in desired turning into a dict must be an ADD, not replace
    assert "/null_key" in ops and ops["/null_key"] == ("add", None, {"nested": "value"})


def test_no_replace_with_null_old():
    # Never generate replace with old: null
    desired = {"metadata": {"annotations": None}}
    live = {"metadata": {"annotations": {"backup": "true"}}}
    diffs = compute_diff(desired, live)
    assert len(diffs) == 1
    assert diffs[0]["op"] == "add"
    assert diffs[0]["old"] is None


def test_named_list_matching():
    desired = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {"name": "app", "image": "nginx:1.20"},
                        {"name": "sidecar", "image": "envoy:1.0"},
                    ]
                }
            }
        }
    }
    live = {
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {"name": "sidecar", "image": "envoy:1.1"},
                        {"name": "app", "image": "nginx:1.20"},
                    ]
                }
            }
        }
    }

    diffs = compute_diff(desired, live)
    assert len(diffs) == 1
    assert diffs[0]["op"] == "replace"
    assert diffs[0]["path"] == "/spec/template/spec/containers/1/image"
    assert diffs[0]["old"] == "envoy:1.0"
    assert diffs[0]["new"] == "envoy:1.1"

    readable = format_readable_diff(diffs, desired, live)
    assert len(readable) == 1
    assert "containers[sidecar].image" in readable[0]
    assert '"envoy:1.0" \u2192 "envoy:1.1"' in readable[0]


def test_unnamed_object_list_element_diff():
    # C1: lists of objects without 'name' (e.g. RBAC rules) compared element-by-element
    desired = {
        "rules": [
            {"verbs": ["get", "list"], "resources": ["pods"]},
            {"verbs": ["get"], "resources": ["services"]},
        ]
    }
    live = {
        "rules": [
            {"verbs": ["*"], "resources": ["pods"]},
            {"verbs": ["get"], "resources": ["services"]},
        ]
    }

    diffs = compute_diff(desired, live)
    assert len(diffs) == 1
    assert diffs[0]["op"] == "replace"
    assert diffs[0]["path"] == "/rules/0/verbs"

    readable = format_readable_diff(diffs, desired, live)
    assert len(readable) == 1
    assert readable[0] == 'REPLACE rules[0].verbs: ["get", "list"] \u2192 ["*"]'


def test_readable_diff_json_boolean_and_null():
    # C2: JSON booleans and null in diff_readable, never True/False/None
    diffs = [
        {"op": "replace", "path": "/spec/privileged", "old": False, "new": True},
        {"op": "add", "path": "/metadata/annotations/owner", "old": None, "new": None},
    ]
    readable = format_readable_diff(diffs)
    assert "false \u2192 true" in readable[0]
    assert "ADD metadata.annotations.owner: null" in readable[1]
