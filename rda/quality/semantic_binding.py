"""Validate derived mappings against independent, producer-bound profile facts.

No config document can establish upstream provenance on its own. Callers must
obtain the second argument from the verified manifest/plan input boundary.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
import numpy as np
from typing import Any, Mapping
from rda.quality.contracts import freeze_json, thaw_json

_PROFILE_FIELDS = {"status", "raw_sha256", "schema_version", "profile_id", "revision", "robot_type", "signals"}
_SIGNAL_REQUIRED = {"name", "role", "source_field", "dtype", "shape", "unit", "quantity", "reference_frame"}
_BINDING_FIELDS = {"profile_revision", "profile_content_hash", "mapping_version", "mapping_hash", "source_profile"}
_GROUP_REQUIRED = {"indices", "physical_quantity", "unit", "reference_frame", "representation"}
_COMPATIBILITY = {
    "absolute_position": {"angle": {"rad", "deg"}, "position": {"m", "mm", "sim_unit"}, "position_command": {"sim_unit"}, "length": {"m", "mm"}},
    "delta_position": {"angle": {"rad", "deg"}, "position": {"m", "mm"}, "length": {"m", "mm"}},
    "velocity": {"angular_velocity": {"rad/s", "deg/s"}, "velocity": {"m/s", "mm/s"}, "linear_velocity": {"m/s", "mm/s"}},
    "torque": {"torque": {"N*m", "Nm"}}, "force": {"force": {"N"}},
    "discrete": {"discrete": {"1", "bool"}, "boolean": {"1", "bool"}},
}


def _object(value, path, required, optional=()):
    if not isinstance(value, Mapping) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f"{path} requires {sorted(required)} and supports only {sorted(set(required) | set(optional))}")
    return value


def _text(value, path):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be nonempty text")


def _indices(value, path, *, empty=False):
    if not isinstance(value, (list, tuple)) or (not value and not empty) or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in value) or len(value) != len(set(value)):
        raise ValueError(f"{path} must contain unique nonnegative indices")
    return list(value)


def normalize_producer_profile(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Preserve original ordered signal identities; never infer missing facts."""
    profile = _object(value, "robot_profile", _PROFILE_FIELDS)
    status = profile["status"]
    if status not in {"complete", "absent", "incomplete"}:
        raise ValueError("robot_profile.status is unsupported")
    digest = profile["raw_sha256"]
    if (status != "absent" and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest))) or (status == "absent" and digest is not None):
        raise ValueError("robot_profile.raw_sha256 must preserve producer bare SHA256")
    if not isinstance(profile["signals"], (list, tuple)):
        raise ValueError("robot_profile.signals must be an ordered list")
    if status != "complete":
        if any(profile[key] is not None for key in ("schema_version", "profile_id", "revision", "robot_type")) or profile["signals"]:
            raise ValueError("incomplete/absent robot_profile cannot declare signal authority")
        return freeze_json(profile)
    if type(profile["schema_version"]) is not int or profile["schema_version"] != 1:
        raise ValueError("robot_profile.schema_version must be 1")
    for key in ("profile_id", "revision", "robot_type"):
        _text(profile[key], f"robot_profile.{key}")
    names = set()
    for signal in profile["signals"]:
        signal = _object(signal, "robot_profile.signals[]", _SIGNAL_REQUIRED, {"joint_names", "min", "max"})
        for key in _SIGNAL_REQUIRED - {"shape"}:
            _text(signal[key], f"signal.{key}")
        if signal["name"] in names or signal["role"] not in {"action", "state", "gripper"}:
            raise ValueError("signal name must be unique and role supported")
        names.add(signal["name"])
        shape = signal["shape"]
        if not isinstance(shape, (list, tuple)) or not shape or any(type(x) is not int or x <= 0 for x in shape):
            raise ValueError("signal.shape must contain positive dimensions")
        width = math.prod(shape)
        if "joint_names" in signal:
            joints = signal["joint_names"]
            if not isinstance(joints, (list, tuple)) or len(joints) != width or any(not isinstance(x, str) or not x for x in joints) or len(set(joints)) != len(joints):
                raise ValueError("signal.joint_names must match flattened shape")
        for key in ("min", "max"):
            if key in signal:
                bounds = signal[key] if isinstance(signal[key], (list, tuple)) else [signal[key]]
                if len(bounds) not in {1, width} or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in bounds):
                    raise ValueError(f"signal.{key} must preserve finite scalar or dimension bounds")
    return freeze_json(profile)


def mapping_hash(robot: Mapping[str, Any]) -> str:
    """Hash noncircular v1 payload; source_profile has its own producer identity."""
    payload = {"mapping_version": robot["source_binding"]["mapping_version"],
               "robot": {key: value for key, value in robot.items() if key != "source_binding"}}
    encoded = json.dumps(thaw_json(freeze_json(payload)), sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_robot_mapping(robot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Check config consistency only, without claiming independent provenance."""
    if "source_binding" not in robot:
        if "signal_mappings" in robot:
            raise ValueError("signal_mappings require source_binding")
        return None
    binding = _object(robot["source_binding"], "robot.source_binding", _BINDING_FIELDS)
    if binding["mapping_version"] != "v1":
        raise ValueError("source_binding.mapping_version must be v1")
    profile = normalize_producer_profile(binding["source_profile"])
    if profile["status"] != "complete":
        raise ValueError("source_binding.source_profile must be complete")
    if robot["profile_id"] != profile["profile_id"] or binding["profile_revision"] != profile["revision"]:
        raise ValueError("source_binding profile_id/revision differs from original source_profile")
    if binding["profile_content_hash"] != "sha256:" + profile["raw_sha256"]:
        raise ValueError("source_binding.profile_content_hash differs from source_profile")
    if binding["mapping_hash"] != mapping_hash(robot):
        raise ValueError("source_binding.mapping_hash does not match canonical derived mapping")
    mappings = _object(robot.get("signal_mappings"), "robot.signal_mappings", {"action", "state"})
    # Old global semantic annotations are ambiguous for two independent sources.
    if robot.get("periodic_dimensions") or robot.get("discrete_dimensions"):
        raise ValueError("bound periodic/discrete dimensions must be source-specific")
    signals = {signal["name"]: signal for signal in profile["signals"]}
    sources = {}
    for kind, mapping in mappings.items():
        mapping = _object(mapping, f"signal_mappings.{kind}", {"signal_name", "groups"})
        _text(mapping["signal_name"], "mapping.signal_name")
        signal = signals.get(mapping["signal_name"])
        expected_field = robot[kind + "_field"]
        source_field = signal.get("source_field") if signal is not None else None
        field_matches = source_field == expected_field or source_field == f"observation.{expected_field}"
        if signal is None or signal["role"] != kind or not field_matches:
            raise ValueError(f"signal_mappings.{kind} source signal role/field mismatch")
        groups = mapping["groups"]
        if not isinstance(groups, Mapping) or not groups:
            raise ValueError(f"signal_mappings.{kind}.groups must be nonempty")
        dimensions = {}
        for name, group in groups.items():
            _text(name, "group name")
            group = _object(group, f"signal_mappings.{kind}.groups.{name}", _GROUP_REQUIRED, {"periodic_dimensions", "discrete_dimensions"})
            indices = _indices(group["indices"], "group.indices")
            if any(index >= math.prod(signal["shape"]) or str(index) in dimensions for index in indices):
                raise ValueError("group indices overlap or exceed source shape")
            for target, original in (("physical_quantity", "quantity"), ("unit", "unit"), ("reference_frame", "reference_frame")):
                if group[target] != signal[original]:
                    raise ValueError(f"group.{target} differs from source signal")
            representation = group["representation"]
            _text(representation, "group.representation")
            try:
                dtype = np.dtype(signal["dtype"])
            except TypeError as exc:
                raise ValueError("unsupported mapped signal dtype") from exc
            if dtype.kind not in ({"b", "i", "u"} if representation == "discrete" else {"f", "i", "u"}):
                raise ValueError("unsupported dtype for mapped representation")
            compatible = _COMPATIBILITY.get(representation, {})
            if group["unit"] not in compatible.get(group["physical_quantity"], set()):
                raise ValueError("unsupported group representation/quantity/unit combination")
            discrete = _indices(group.get("discrete_dimensions", []), "group.discrete_dimensions", empty=True)
            if discrete and (representation != "discrete" or set(discrete) != set(indices)):
                raise ValueError("discrete group requires discrete representation for every dimension")
            periods = {}
            periodic = group.get("periodic_dimensions", [])
            if not isinstance(periodic, (list, tuple)):
                raise ValueError("periodic_dimensions must be an ordered list")
            for item in periodic:
                item = _object(item, "periodic_dimensions[]", {"index", "period"})
                index = _indices([item["index"]], "periodic index")[0]
                period = item["period"]
                if index not in indices or index in periods or representation not in {"absolute_position", "delta_position"} or group["physical_quantity"] != "angle" or isinstance(period, bool) or not isinstance(period, (int, float)) or not math.isfinite(period) or period <= 0:
                    raise ValueError("periodic dimension requires unique member index and finite positive angular period")
                periods[index] = period
            for index in indices:
                dimensions[str(index)] = {"group": name, "index": index, "representation": representation,
                    "physical_quantity": group["physical_quantity"], "unit": group["unit"], "reference_frame": group["reference_frame"],
                    "discrete": representation == "discrete", "period": periods.get(index)}
        sources[kind] = {"signal": signal, "source_field": signal["source_field"], "dimensions": dimensions}
    return freeze_json({"sources": sources, "source_binding": binding})


def validate_semantic_binding(robot: Mapping[str, Any] | None, producer_profile: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
    """Return semantic views only when independent producer facts agree exactly."""
    if robot is None:
        return None
    derived = validate_robot_mapping(robot)
    if derived is None or producer_profile is None:
        return None
    original = normalize_producer_profile(producer_profile)
    if original["status"] != "complete":
        return None
    if original != robot["source_binding"]["source_profile"]:
        raise ValueError("source_binding.source_profile differs from independently bound producer facts")
    return derived
