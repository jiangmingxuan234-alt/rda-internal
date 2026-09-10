"""Strict normalization and hashing for quality-mode configuration."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from rda.quality.contracts import FrozenDict, freeze_json, thaw_json


_TOP_LEVEL_FIELDS = {"contract_version", "robot", "quality", "training"}
_QUALITY_FIELDS = {"metrics", "reference_set", "sampling", "resource_budget"}
_METRIC_FIELDS = {"name", "role", "parameters", "rule"}
_RULE_FIELDS = {"rule_id", "version", "scope", "thresholds", "calibration_status", "provisional"}
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
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("contract_version must be a positive integer")
        if "quality" not in root:
            raise ValueError("quality is required")

        quality = _mapping(root["quality"], "quality")
        _reject_unknown(quality, _QUALITY_FIELDS, "quality")
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
                if not scope:
                    raise ValueError(f"{path}.rule.scope must be non-empty")
                for required in ("rule_id", "version", "thresholds"):
                    if required not in rule:
                        raise ValueError(f"{path}.rule.{required} is required")
                _mapping(rule["thresholds"], f"{path}.rule.thresholds")
                if (
                    rule.get("calibration_status") == "calibrated"
                    and rule.get("provisional") is True
                ):
                    raise ValueError(
                        f"{path}.rule cannot be both calibrated and provisional"
                    )
                normalized_metric["rule"] = dict(rule)
            normalized_metrics.append(normalized_metric)

        normalized_quality = dict(quality)
        normalized_quality["metrics"] = normalized_metrics

        robot = None
        if "robot" in root:
            raw_robot = _mapping(root["robot"], "robot")
            _reject_unknown(raw_robot, _ROBOT_FIELDS, "robot")
            if not raw_robot:
                raise ValueError("robot profile must not be empty when declared")
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
            if not isinstance(raw_training["required_modalities"], (list, tuple)):
                raise ValueError("training.required_modalities must be a list")
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
