"""Declarative task-profile overrides for quality-mode configuration."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from rda.quality.registry import METRICS


_OVERRIDE_FIELDS = {"task_id", "profile_revision", "metrics", "training"}
_METRIC_OVERRIDE_FIELDS = {"parameters", "rule"}


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be a mapping")
    return value


def _nonempty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value


def merge_task_profile(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Merge task-specific quality parameters into a complete base config.

    Only metric ``parameters``/``rule`` and training fields may be overridden.
    The returned mapping is independent from both inputs and is subsequently
    validated by :class:`QualityConfig`.
    """
    root = _mapping(base, "base config")
    task = _mapping(override, "task profile")
    unknown = sorted(set(task) - _OVERRIDE_FIELDS)
    if unknown:
        raise ValueError(f"unknown task profile field(s): {', '.join(unknown)}")
    task_id = _nonempty_text(task.get("task_id"), "task profile.task_id")

    merged = deepcopy(dict(root))
    quality = _mapping(merged.get("quality"), "base config.quality")
    metrics = quality.get("metrics")
    if not isinstance(metrics, list):
        raise ValueError("base config.quality.metrics must be a list")
    by_name: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        metric_map = _mapping(metric, "base config.quality.metrics[]")
        name = _nonempty_text(metric_map.get("name"), "base metric.name")
        if name in by_name:
            raise ValueError(f"duplicate metric: {name}")
        by_name[name] = metric_map  # type: ignore[assignment]

    raw_overrides = task.get("metrics", {})
    raw_overrides = _mapping(raw_overrides, "task profile.metrics")
    for name, raw in raw_overrides.items():
        if name not in METRICS or name not in by_name:
            raise ValueError(f"unknown metric: {name!r}")
        override_metric = _mapping(raw, f"task profile.metrics.{name}")
        unknown_metric = sorted(set(override_metric) - _METRIC_OVERRIDE_FIELDS)
        if unknown_metric:
            raise ValueError(
                f"unknown task metric field(s) for {name}: {', '.join(unknown_metric)}"
            )
        target = by_name[name]
        if "parameters" in override_metric:
            params = _mapping(override_metric["parameters"], f"task profile.metrics.{name}.parameters")
            target["parameters"] = {**dict(target.get("parameters", {})), **dict(params)}
        if "rule" in override_metric:
            rule = _mapping(override_metric["rule"], f"task profile.metrics.{name}.rule")
            current_rule = _mapping(target.get("rule", {}), f"base metric {name}.rule")
            merged_rule = {**dict(current_rule), **dict(rule)}
            if "thresholds" in rule:
                current_thresholds = _mapping(current_rule.get("thresholds", {}), f"base metric {name}.rule.thresholds")
                thresholds = _mapping(rule["thresholds"], f"task profile.metrics.{name}.rule.thresholds")
                merged_rule["thresholds"] = {**dict(current_thresholds), **dict(thresholds)}
            target["rule"] = merged_rule

    quality_copy = dict(quality)
    quality_copy["metrics"] = list(by_name.values())
    reference_set = dict(_mapping(quality_copy.get("reference_set", {}), "base config.quality.reference_set"))
    reference_set["task_profile_id"] = task_id
    if "profile_revision" in task:
        reference_set["task_profile_revision"] = _nonempty_text(task["profile_revision"], "task profile.profile_revision")
    quality_copy["reference_set"] = reference_set
    merged["quality"] = quality_copy

    if "training" in task:
        training = _mapping(task["training"], "task profile.training")
        base_training = _mapping(merged.get("training", {}), "base config.training")
        merged["training"] = {**dict(base_training), **dict(training)}
    return merged
