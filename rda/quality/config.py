"""Strict normalization and hashing for quality-mode configuration."""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

from rda.quality.contracts import FrozenDict, freeze_json, thaw_json


_TOP_LEVEL_FIELDS = {"contract_version", "robot", "quality", "training"}
_QUALITY_FIELDS = {"metrics", "reference_set", "sampling", "resource_budget"}
_METRIC_FIELDS = {"name", "role", "parameters", "rule"}
_RULE_FIELDS = {
    "rule_id", "version", "scope", "thresholds", "calibration_status",
    "provisional", "calibration",
}
_CALIBRATION_FIELDS = {"calibration_id", "calibration_hash"}
_SCOPE_FIELDS = {"all", "tasks", "cameras", "dimension_groups", "robot_profile_ids"}
_DIMENSION_GROUP_FIELDS = {"indices", "physical_quantity", "unit"}
_ROBOT_FIELDS = {
    "profile_id", "action_field", "state_field", "action_representation",
    "coordinate_frame", "dimension_groups", "periodic_dimensions",
    "discrete_dimensions", "cameras",
}
_TRAINING_FIELDS = {
    "policy_type", "observation_history", "horizon", "stride", "padding",
    "required_modalities", "delta_timestamps", "camera_tolerance",
}
_METRIC_ROLES = {"informational", "required_for_advice"}
_ACTION_REPRESENTATIONS = {
    "absolute_position", "delta_position", "velocity", "torque", "force", "discrete"
}
_PADDING_MODES = {"none", "left", "right", "both", "edge", "zero", "repeat_last"}
_CALIBRATION_STATUSES = {"uncalibrated", "calibrated"}
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _known_metric_names() -> frozenset[str]:
    from rda.metrics import ALL_METRICS

    return frozenset(metric.name for metric in ALL_METRICS)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unknown field at {path}: {', '.join(unknown)}")


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _string_list(value: Any, path: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{path} must be a list")
    result = [_nonempty_string(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if not allow_empty and not result:
        raise ValueError(f"{path} must not be empty")
    if len(result) != len(set(result)):
        raise ValueError(f"{path} must not contain duplicates")
    return result


def _validate_scope(scope: Mapping[str, Any], path: str) -> None:
    _reject_unknown(scope, _SCOPE_FIELDS, path)
    if not scope:
        raise ValueError(f"{path} must be non-empty")
    if "all" in scope:
        if scope["all"] is not True:
            raise ValueError(f"{path}.all must be true when present")
        if len(scope) != 1:
            raise ValueError(f"{path}.all cannot be combined with scoped selectors")
        return
    for field, members in scope.items():
        _string_list(members, f"{path}.{field}")


def canonical_json(value: Mapping[str, Any]) -> str:
    """Encode JSON deterministically after numeric/container normalization."""
    normalized = thaw_json(freeze_json(value))
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def config_hash(value: Mapping[str, Any]) -> str:
    payload = canonical_json(value).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class QualityConfig:
    contract_version: int
    robot: FrozenDict | None
    quality: FrozenDict
    training: FrozenDict | None
    requested_config: FrozenDict
    effective_config: FrozenDict
    requested_config_hash: str
    effective_config_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "QualityConfig":
        root = _mapping(value, "config")
        _reject_unknown(root, _TOP_LEVEL_FIELDS, "config")
        if "contract_version" not in root:
            raise ValueError("contract_version is required")
        version = root["contract_version"]
        if isinstance(version, bool) or not isinstance(version, int):
            raise ValueError("contract_version must be an integer")
        if version != 1:
            raise ValueError(f"unsupported contract_version: {version!r}; supported: 1")
        if "quality" not in root:
            raise ValueError("quality is required")

        quality = _mapping(root["quality"], "quality")
        _reject_unknown(quality, _QUALITY_FIELDS, "quality")
        for container_field in ("reference_set", "sampling", "resource_budget"):
            if container_field in quality:
                _mapping(quality[container_field], f"quality.{container_field}")
        metrics = quality.get("metrics")
        if not isinstance(metrics, (list, tuple)):
            raise ValueError("quality.metrics must be a list")
        seen: set[str] = set()
        normalized_metrics: list[dict[str, Any]] = []
        known_metrics = _known_metric_names()
        for index, raw_metric in enumerate(metrics):
            path = f"quality.metrics[{index}]"
            metric = _mapping(raw_metric, path)
            _reject_unknown(metric, _METRIC_FIELDS, path)
            name = metric.get("name")
            if name not in known_metrics:
                raise ValueError(f"unknown metric: {name!r}")
            if name in seen:
                raise ValueError(f"duplicate metric: {name}")
            seen.add(name)
            role = metric.get("role")
            if role not in _METRIC_ROLES:
                raise ValueError(f"{path}.role must be informational or required_for_advice")
            parameters = _mapping(metric.get("parameters", {}), f"{path}.parameters")
            normalized_metric: dict[str, Any] = {
                "name": name,
                "role": role,
                "parameters": dict(parameters),
            }
            if "rule" in metric:
                rule = _mapping(metric["rule"], f"{path}.rule")
                _reject_unknown(rule, _RULE_FIELDS, f"{path}.rule")
                scope = _mapping(rule.get("scope"), f"{path}.rule.scope")
                _validate_scope(scope, f"{path}.rule.scope")
                for required in ("rule_id", "version", "thresholds"):
                    if required not in rule:
                        raise ValueError(f"{path}.rule.{required} is required")
                _mapping(rule["thresholds"], f"{path}.rule.thresholds")
                _nonempty_string(rule["rule_id"], f"{path}.rule.rule_id")
                _nonempty_string(rule["version"], f"{path}.rule.version")
                calibration_status = rule.get("calibration_status", "uncalibrated")
                if calibration_status not in _CALIBRATION_STATUSES:
                    raise ValueError(
                        f"{path}.rule.calibration_status must be one of "
                        f"{sorted(_CALIBRATION_STATUSES)}"
                    )
                provisional = rule.get("provisional", False)
                if not isinstance(provisional, bool):
                    raise ValueError(f"{path}.rule.provisional must be boolean")
                if (
                    calibration_status == "calibrated" and provisional
                ):
                    raise ValueError(
                        f"{path}.rule cannot be both calibrated and provisional"
                    )
                normalized_rule = dict(rule)
                normalized_rule["calibration_status"] = calibration_status
                normalized_rule["provisional"] = provisional
                if calibration_status == "calibrated":
                    calibration = _mapping(
                        rule.get("calibration"), f"{path}.rule.calibration"
                    )
                    _reject_unknown(
                        calibration, _CALIBRATION_FIELDS, f"{path}.rule.calibration"
                    )
                    calibration_id = _nonempty_string(
                        calibration.get("calibration_id"),
                        f"{path}.rule.calibration.calibration_id",
                    )
                    calibration_hash = calibration.get("calibration_hash")
                    if (
                        not isinstance(calibration_hash, str)
                        or not _SHA256_PATTERN.fullmatch(calibration_hash)
                    ):
                        raise ValueError(
                            f"{path}.rule.calibration.calibration_hash must be a sha256 content hash"
                        )
                    normalized_rule["calibration"] = {
                        "calibration_id": calibration_id,
                        "calibration_hash": calibration_hash,
                    }
                elif "calibration" in rule:
                    raise ValueError(
                        f"{path}.rule.calibration requires calibration_status=calibrated"
                    )
                normalized_metric["rule"] = normalized_rule
            normalized_metrics.append(normalized_metric)

        normalized_quality = dict(quality)
        normalized_quality["metrics"] = normalized_metrics

        robot = None
        if "robot" in root:
            raw_robot = _mapping(root["robot"], "robot")
            _reject_unknown(raw_robot, _ROBOT_FIELDS, "robot")
            required_robot = {
                "profile_id", "action_field", "state_field", "action_representation",
                "coordinate_frame", "dimension_groups", "cameras",
            }
            missing_robot = sorted(required_robot - set(raw_robot))
            if missing_robot:
                raise ValueError(f"robot profile missing fields: {missing_robot}")
            for field in ("profile_id", "action_field", "state_field", "coordinate_frame"):
                _nonempty_string(raw_robot[field], f"robot.{field}")
            representation = raw_robot["action_representation"]
            if representation not in _ACTION_REPRESENTATIONS:
                raise ValueError(
                    "robot.action_representation must be one of "
                    f"{sorted(_ACTION_REPRESENTATIONS)}"
                )
            groups = _mapping(raw_robot["dimension_groups"], "robot.dimension_groups")
            for group_name, group in groups.items():
                _nonempty_string(group_name, "robot.dimension_groups key")
                group_path = f"robot.dimension_groups.{group_name}"
                group = _mapping(group, group_path)
                _reject_unknown(group, _DIMENSION_GROUP_FIELDS, group_path)
                missing_group = sorted(_DIMENSION_GROUP_FIELDS - set(group))
                if missing_group:
                    raise ValueError(f"{group_path} missing fields: {missing_group}")
                indices = group["indices"]
                if (
                    not isinstance(indices, (list, tuple))
                    or not indices
                    or any(
                        isinstance(index, bool) or not isinstance(index, int) or index < 0
                        for index in indices
                    )
                    or len(indices) != len(set(indices))
                ):
                    raise ValueError(
                        f"{group_path}.indices must be unique non-negative integers"
                    )
                _nonempty_string(group["physical_quantity"], f"{group_path}.physical_quantity")
                _nonempty_string(group["unit"], f"{group_path}.unit")
            _string_list(raw_robot["cameras"], "robot.cameras", allow_empty=True)
            for field in ("periodic_dimensions", "discrete_dimensions"):
                if field in raw_robot:
                    dimensions = raw_robot[field]
                    if not isinstance(dimensions, (list, tuple)) or any(
                        isinstance(item, bool) or not isinstance(item, int) or item < 0
                        for item in dimensions
                    ):
                        raise ValueError(f"robot.{field} must be a list of non-negative integers")
            periodic = set(raw_robot.get("periodic_dimensions", ()))
            discrete = set(raw_robot.get("discrete_dimensions", ()))
            if periodic & discrete:
                raise ValueError("robot periodic_dimensions and discrete_dimensions must not overlap")
            robot = freeze_json(raw_robot, path="robot")

        training = None
        if "training" in root:
            raw_training = _mapping(root["training"], "training")
            _reject_unknown(raw_training, _TRAINING_FIELDS, "training")
            for required in (
                "policy_type", "observation_history", "horizon", "stride",
                "padding", "required_modalities",
            ):
                if required not in raw_training:
                    raise ValueError(f"training.{required} is required")
            for positive in ("observation_history", "horizon", "stride"):
                number = raw_training[positive]
                if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                    raise ValueError(f"training.{positive} must be a positive integer")
            _nonempty_string(raw_training["policy_type"], "training.policy_type")
            padding = raw_training["padding"]
            if not isinstance(padding, str) or padding not in _PADDING_MODES:
                raise ValueError(f"training.padding must be one of {sorted(_PADDING_MODES)}")
            _string_list(raw_training["required_modalities"], "training.required_modalities")
            if "camera_tolerance" in raw_training:
                tolerance = raw_training["camera_tolerance"]
                if (
                    isinstance(tolerance, bool)
                    or not isinstance(tolerance, (int, float))
                    or not math.isfinite(tolerance)
                    or tolerance < 0
                ):
                    raise ValueError("training.camera_tolerance must be a non-negative finite number")
            if "delta_timestamps" in raw_training:
                delta_timestamps = _mapping(
                    raw_training["delta_timestamps"], "training.delta_timestamps"
                )
                for modality, offsets in delta_timestamps.items():
                    _nonempty_string(modality, "training.delta_timestamps key")
                    if not isinstance(offsets, (list, tuple)) or any(
                        isinstance(offset, bool)
                        or not isinstance(offset, (int, float))
                        or not math.isfinite(offset)
                        for offset in offsets
                    ):
                        raise ValueError(
                            f"training.delta_timestamps.{modality} must be a list of finite numbers"
                        )
            training = freeze_json(raw_training, path="training")

        requested = freeze_json(root, path="config")
        effective_dict: dict[str, Any] = {
            "contract_version": version,
            "quality": normalized_quality,
        }
        if robot is not None:
            effective_dict["robot"] = thaw_json(robot)
        if training is not None:
            effective_dict["training"] = thaw_json(training)
        effective = freeze_json(effective_dict, path="effective_config")
        assert isinstance(requested, FrozenDict)
        assert isinstance(effective, FrozenDict)
        assert isinstance(robot, (FrozenDict, type(None)))
        assert isinstance(training, (FrozenDict, type(None)))
        quality_frozen = effective["quality"]
        assert isinstance(quality_frozen, FrozenDict)
        return cls(
            contract_version=version,
            robot=robot,
            quality=quality_frozen,
            training=training,
            requested_config=requested,
            effective_config=effective,
            requested_config_hash=config_hash(requested),
            effective_config_hash=config_hash(effective),
        )
