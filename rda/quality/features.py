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
    result: dict[str, Any] = {"sample_count": int(values.size), "finite_count": int(finite.size)}
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


def compute_shared_features(episode: EpisodeData, config: QualityConfig, *, producer_binding: Mapping[str, Any] | None = None) -> SharedFeatures:
    """Compute explicit action/state observations without a legacy metric call."""
    action, state = _arrays(episode, config)
    semantic = "UNKNOWN"
    if config.robot is not None and "source_binding" in config.robot and producer_binding is not None and (
        producer_binding.get("profile_id") == config.robot["profile_id"]
        and producer_binding.get("revision") == config.robot["source_binding"]["profile_revision"]
        and producer_binding.get("raw_sha256") == config.robot["source_binding"]["profile_content_hash"]
        and producer_binding.get("status") == "complete"
    ):
        semantic = "BOUND"
    numeric: dict[str, Any] = {"timestamps": {"sample_count": int(len(episode.timestamps))}}
    timestamps = np.asarray(episode.timestamps, dtype=float)
    valid_time = timestamps.ndim == 1 and len(timestamps) == episode.num_frames and np.all(np.isfinite(timestamps)) and (len(timestamps) < 2 or np.all(np.diff(timestamps) > 0))
    numeric["timestamps"]["status"] = "ok" if valid_time else "invalid_timestamps"
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
        numeric["raw_sources"] = {
            "action": {name: np.asarray(values).tolist() for name, values in episode.action.items()},
            "state": {name: np.asarray(values).tolist() for name, values in episode.observation.items()},
        }
    for kind, array in (("action", action), ("state", state)):
        if array is None:
            numeric[kind] = {"status": "missing_source", "dimensions": {}}
            continue
        arr = np.asarray(array)
        if arr.ndim == 1:
            arr = arr[:, None]
        if arr.ndim != 2 or arr.shape[0] != episode.num_frames:
            numeric[kind] = {"status": "invalid_shape", "dimensions": {}}
            continue
        dimensions: dict[str, Any] = {}
        for index in range(arr.shape[1]):
            values = np.asarray(arr[:, index], dtype=float)
            entry: dict[str, Any] = {"raw_values": [float(v) for v in values], "statistics": _stat(values), "kind": "discrete" if index in discrete else "continuous"}
            if index in discrete:
                transitions = np.flatnonzero(np.diff(values) != 0)
                entry["transitions"] = [int(v) for v in transitions]
                entry["value_counts"] = {str(value): int(count) for value, count in zip(*np.unique(values, return_counts=True))}
            else:
                entry["delta"] = _delta(values, period=periodic.get(index))
                if kind == "action":
                    if representation in {"velocity", "delta_position"}:
                        entry["activity_count"] = int(np.count_nonzero(np.abs(values) > 0))
                    else:
                        entry["activity_count"] = int(np.count_nonzero(np.abs(np.diff(values)) > 0))
                if kind == "state":
                    if semantic == "BOUND" and valid_time:
                        state_delta = np.diff(values)
                        if index in periodic:
                            state_delta = (state_delta + periodic[index] / 2.0) % periodic[index] - periodic[index] / 2.0
                        derivative = state_delta / np.diff(timestamps)
                        group = next((group for group in config.robot["dimension_groups"].values() if index in group["indices"]), None)
                        unit = (str(group["unit"]) if group else "unknown") + "/s"
                        entry["derivative"] = _stat(derivative) | {"values": [float(value) for value in derivative], "locations": [int(value) for value in range(len(derivative))], "unit": unit, "difference": "wrapped_first_difference" if index in periodic else "first_difference", "smoothing": "none", "status": "ok"}
                    else:
                        entry["derivative"] = {"status": "UNASSESSED" if semantic == "UNKNOWN" else "invalid_timestamps"}
            dimensions[str(index)] = entry
        numeric[kind] = {"status": "ok", "dimensions": dimensions, "representation": representation}
    return SharedFeatures(numeric=numeric, visual={}, semantic_status=semantic)

