"""Pure, versioned feature calculations for quality measurements.

These functions deliberately publish observations only.  Rules and verdicts
are owned by the later assessment layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from rda.io.schema import EpisodeData
from rda.quality.config import QualityConfig
from rda.quality.semantic_binding import validate_semantic_binding
from rda.quality.visual_features import VisualFeatures, compute_visual_features


ALGORITHM_VERSION = "quality-features-v1"


@dataclass(frozen=True)
class SharedFeatures:
    numeric: Mapping[str, Any]
    visual: Mapping[str, Any]
    semantic_status: str


def _stat(values: np.ndarray) -> dict[str, Any]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    result: dict[str, Any] = {"sample_count": int(values.size), "finite_count": int(finite.size), "missing_count": int(values.size - finite.size), "minimum_samples": 1}
    if not finite.size:
        return result | {"status": "empty"}
    result.update({"median": float(np.median(finite)), "p95": float(np.percentile(finite, 95))})
    return result


def _delta(values: np.ndarray, *, period: float | None = None) -> dict[str, Any]:
    values = np.asarray(values, dtype=float)
    if values.size < 2:
        return {"status": "insufficient_sample", "values": [], "sample_count": 0}
    raw = np.diff(values)
    if period is not None:
        raw = (raw + period / 2.0) % period - period / 2.0
    finite = raw[np.isfinite(raw)]
    result: dict[str, Any] = {"values": [float(x) for x in raw], "sample_count": int(raw.size), "finite_count": int(finite.size)}
    if finite.size != raw.size:
        return result | {"status": "nonfinite_sample"}
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    result.update({"median": median, "p95": float(np.percentile(np.abs(finite), 95)), "mad": mad})
    if mad <= np.finfo(float).eps * max(1.0, abs(median)):
        result.update({"mad_status": "mad_degenerate", "tolerance": float(np.finfo(float).eps * max(1.0, abs(median))), "non_median_locations": [int(i) for i, value in enumerate(raw) if value != median]})
    else:
        result["mad_status"] = "ok"
    return result


def _arrays(episode: EpisodeData, config: QualityConfig) -> tuple[np.ndarray | None, np.ndarray | None]:
    if config.robot is None:
        return None, None
    else:
        action = episode.action.get(config.robot["action_field"])
        state = episode.observation.get(config.robot["state_field"])
    return action, state


def compute_shared_features(episode: EpisodeData, config: QualityConfig, *, producer_binding: Mapping[str, Any] | None = None, parameters: Mapping[str, Any] | None = None) -> SharedFeatures:
    """Compute explicit action/state observations without a legacy metric call."""
    action, state = _arrays(episode, config)
    parameters = parameters or {}
    binding = validate_semantic_binding(config.robot, producer_binding) if config.robot is not None else None
    semantic = "BOUND" if binding is not None else "UNKNOWN"
    numeric: dict[str, Any] = {"timestamps": {"sample_count": int(len(episode.timestamps)), "minimum_samples": 2}}
    try:
        timestamps = np.asarray(episode.timestamps, dtype=float)
    except (TypeError, ValueError):
        timestamps = np.array([], dtype=float)
    valid_time = timestamps.ndim == 1 and len(timestamps) == episode.num_frames and np.all(np.isfinite(timestamps)) and (len(timestamps) < 2 or np.all(np.diff(timestamps) > 0))
    numeric["timestamps"]["status"] = "ok" if valid_time else "invalid_timestamps"
    if valid_time and len(timestamps) >= 2:
        dt = np.diff(timestamps)
        numeric["timestamps"].update({"duration": float(timestamps[-1] - timestamps[0]), "first": float(timestamps[0]), "last": float(timestamps[-1]), "interval": _stat(dt) | {"values": [float(value) for value in dt], "unit": "s"}})
    periodic: dict[int, float] = {}
    discrete: set[int] = set()
    representation = None
    if config.robot is not None:
        representation = config.robot["action_representation"]
        for item in config.robot.get("periodic_dimensions", ()):  # normalized config accepts mapping entries
            if isinstance(item, Mapping):
                periodic[int(item["index"])] = float(item["period"])
        discrete = set(config.robot.get("discrete_dimensions", ()))

    if config.robot is None:
        raw: dict[str, Any] = {"action": {}, "state": {}}
        for kind, sources in (("action", episode.action), ("state", episode.observation)):
            for name, source in sources.items():
                try:
                    array = np.asarray(source, dtype=float)
                    if array.ndim == 1: array = array[:, None]
                    raw[kind][name] = {"dimensions": {str(index): _stat(array[:, index]) for index in range(array.shape[1])}, "shape": list(array.shape)}
                except (TypeError, ValueError, IndexError):
                    raw[kind][name] = {"status": "nonnumeric_source"}
        numeric["raw_sources"] = raw
    for kind, array in (("action", action), ("state", state)):
        if array is None:
            numeric[kind] = {"status": "missing_source", "dimensions": {}}
            continue
        try:
            arr = np.asarray(array, dtype=float)
        except (TypeError, ValueError):
            numeric[kind] = {"status": "nonnumeric_source", "dimensions": {}}
            continue
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.ndim != 2 or arr.shape[0] != episode.num_frames:
            numeric[kind] = {"status": "invalid_shape", "dimensions": {}}
            continue
        dimensions: dict[str, Any] = {}
        source_dimensions = binding["sources"][kind]["dimensions"] if binding is not None else {}
        for index in range(arr.shape[1]):
            values = np.asarray(arr[:, index], dtype=float)
            semantics = source_dimensions.get(str(index), {})
            dimension_period = semantics.get("period", periodic.get(index))
            dimension_discrete = bool(semantics.get("discrete", index in discrete))
            dimension_representation = semantics.get("representation", representation)
            entry: dict[str, Any] = {"statistics": _stat(values), "kind": "discrete" if dimension_discrete else "continuous"}
            if dimension_discrete:
                transitions = np.flatnonzero(np.diff(values) != 0)
                entry["transitions"] = [int(v) for v in transitions]
                if kind == "action" and semantic == "BOUND":
                    entry["activity_count"] = int(transitions.size)
                    entry["activity_runs"] = _runs(np.r_[False, np.diff(values) != 0])
                entry["value_counts"] = {str(value): int(count) for value, count in zip(*np.unique(values, return_counts=True))}
            else:
                entry["delta"] = _delta(values, period=dimension_period)
                if kind == "action":
                    if semantic == "BOUND" and dimension_representation in {"velocity", "delta_position"}:
                        mask = np.abs(values) > float(parameters.get("activity_epsilon", 0.0))
                        entry["activity_count"] = int(np.count_nonzero(mask))
                        entry["activity_runs"] = _runs(mask)
                        entry["idle_count"] = int(mask.size - np.count_nonzero(mask))
                    elif semantic == "BOUND" and dimension_representation == "absolute_position":
                        entry["activity_count"] = int(np.count_nonzero(np.abs(np.diff(values)) > 0))
                        entry["activity_runs"] = _runs(np.abs(np.diff(values)) > 0)
                    else:
                        entry["activity_status"] = "UNASSESSED"
                if kind == "state":
                    if semantic == "BOUND" and valid_time:
                        state_delta = np.diff(values)
                        if dimension_period is not None:
                            state_delta = (state_delta + dimension_period / 2.0) % dimension_period - dimension_period / 2.0
                        derivative = state_delta / np.diff(timestamps)
                        unit = str(semantics.get("unit", "unknown")) + "/s"
                        acceleration = np.diff(derivative) / np.diff(timestamps)[1:] if len(derivative) >= 2 else np.array([])
                        derivative_fact = _stat(derivative) | {"values": [float(value) if np.isfinite(value) else None for value in derivative], "locations": [int(value) for value in range(len(derivative))], "unit": unit, "difference": "wrapped_first_difference" if dimension_period is not None else "first_difference", "smoothing": str(parameters.get("smoothing", "none")), "status": "ok" if np.all(np.isfinite(derivative)) else "nonfinite_sample", "acceleration": _stat(acceleration) | {"values": [float(value) if np.isfinite(value) else None for value in acceleration], "locations": [int(value + 1) for value in range(len(acceleration))], "unit": unit + "/s"}}
                        entry["derivative"] = derivative_fact
                    else:
                        entry["derivative"] = {"status": "UNASSESSED" if semantic == "UNKNOWN" else "invalid_timestamps"}
            dimensions[str(index)] = entry
        numeric[kind] = {"status": "ok", "dimensions": dimensions, "representation": representation}
    return SharedFeatures(numeric=numeric, visual={}, semantic_status=semantic)


def _runs(mask: np.ndarray) -> list[dict[str, int]]:
    runs: list[dict[str, int]] = []
    start: int | None = None
    for index, active in enumerate(mask):
        if active and start is None: start = index
        if start is not None and (not active or index == len(mask) - 1):
            end = index if active else index - 1
            runs.append({"start": start, "end": end, "length": end - start + 1})
            start = None
    return runs
