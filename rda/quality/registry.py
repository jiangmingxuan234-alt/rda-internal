"""Single versioned quality disposition and implemented-parameter registry."""
from __future__ import annotations
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any, Mapping

REGISTRY_VERSION = "quality-registry-v1"


@dataclass(frozen=True)
class MetricSpec:
    disposition: str
    parameters: frozenset[str]


_SPECS = {
    "action_discontinuity": MetricSpec("measurement", frozenset({"mad_tolerance"})),
    "idle_ratio": MetricSpec("measurement", frozenset({"activity_epsilon"})),
    "velocity_acceleration": MetricSpec("measurement", frozenset({"smoothing"})),
    "sampling_jitter": MetricSpec("measurement", frozenset()),
    "visual_quality": MetricSpec("measurement", frozenset({"preprocess"})),
    "video_freeze": MetricSpec("measurement", frozenset({"preprocess", "low_change_threshold"})),
}
for _name in ("joint_limit", "timestamp_validity", "video_stream_sync", "video_timestamp_alignment",
              "missing_dropout", "invalid_values", "schema_consistency", "video_frame_integrity"):
    _SPECS[_name] = MetricSpec("delegated", frozenset())
for _name in ("temporal_sufficiency", "sensor_synchronization", "distribution", "coverage"):
    _SPECS[_name] = MetricSpec("deferred", frozenset())
METRICS = MappingProxyType(_SPECS)


def metric_spec(name: str) -> MetricSpec:
    if not isinstance(name, str) or name not in METRICS:
        raise ValueError(f"unknown metric: {name!r}")
    return METRICS[name]


def validate_preprocess(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) - {"roi"}:
        raise ValueError("preprocess supports only implemented roi")
    roi = value.get("roi", "full")
    if not isinstance(roi, str) or roi != "full":
        if not isinstance(roi, (tuple, list)) or len(roi) != 4 or any(type(x) is not int for x in roi):
            raise ValueError("preprocess.roi must be full or integer [y0,y1,x0,x1]")
        y0, y1, x0, x1 = roi
        if min(y0, x0) < 0 or y1 - y0 < 3 or x1 - x0 < 3:
            raise ValueError("preprocess.roi must be nonnegative and at least 3 by 3")
    return dict(value)


def validate_parameters(name: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    spec = metric_spec(name)
    if not isinstance(parameters, Mapping):
        raise ValueError(f"{name}.parameters must be a mapping")
    unknown = set(parameters) - spec.parameters
    if unknown:
        raise ValueError(f"unknown parameters for {name}: {sorted(unknown)}")
    result = dict(parameters)
    for key, value in parameters.items():
        if key in {"mad_tolerance", "activity_epsilon", "low_change_threshold"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name}.{key} must be finite and nonnegative")
        elif key == "smoothing" and value != "none":
            raise ValueError("velocity_acceleration.smoothing supports only none")
        elif key == "preprocess":
            result[key] = validate_preprocess(value)
    return result
