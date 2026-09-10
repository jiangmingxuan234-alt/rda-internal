"""Translate one explicit plan unit into a versioned measurement record."""
from __future__ import annotations

from typing import Any

from rda.io.schema import EpisodeData
from rda.quality.config import QualityConfig
from rda.quality.contracts import Applicability, MeasurementRecord
from rda.quality.execution_plan import PlanUnit
from rda.quality.features import ALGORITHM_VERSION, compute_shared_features
from rda.quality.visual_features import compute_visual_features


_DELEGATED = {"joint_limit", "timestamp_validity", "video_stream_sync", "video_timestamp_alignment"}
_DEFERRED = {"temporal_sufficiency", "sensor_synchronization"}


def measure_unit(unit: PlanUnit, episode: EpisodeData, media: Any, config: QualityConfig) -> MeasurementRecord:
    """Measure only ``unit.metric``; this never selects a default metric set."""
    if unit.effective_config_hash != config.effective_config_hash:
        raise ValueError("plan unit effective config does not match measurement config")
    if unit.metric in _DELEGATED | _DEFERRED:
        reason = "delegated_to_robovet" if unit.metric in _DELEGATED else "provider_not_available"
        return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION,
                                 config.effective_config_hash, Applicability.UNKNOWN,
                                 {"planned_samples": 0, "attempted_samples": 0, "computed_samples": 0}, {},
                                 ({"reason": reason, "metric": unit.metric},))
    metric_config = next((item for item in config.quality["metrics"] if item["name"] == unit.metric), None)
    if metric_config is None:
        raise ValueError(f"metric {unit.metric!r} was not configured")
    if unit.metric in {"visual_quality", "video_freeze"}:
        if media is None:
            return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION, config.effective_config_hash,
                                     Applicability.UNKNOWN, {"planned_samples": 0, "attempted_samples": 0, "computed_samples": 0}, {},
                                     ({"reason": "media_provider_missing"},))
        sample_range = unit.sampling_range
        interval = (float(sample_range.get("from_timestamp", getattr(media.ref, "from_timestamp", 0.0))), float(sample_range.get("to_timestamp", getattr(media.ref, "to_timestamp", 0.0))))
        planned = int(sample_range.get("planned_samples", len(getattr(media, "target_times", ()))))
        params = metric_config["parameters"]
        visual = compute_visual_features(media, planned_samples=planned, interval=interval,
                                         preprocess=params.get("preprocess", {"roi": "full"}),
                                         low_change_threshold=float(params.get("low_change_threshold", 0.0)))
        return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION, config.effective_config_hash,
                                 Applicability.APPLICABLE if visual.coverage["computed_samples"] else Applicability.UNKNOWN,
                                 visual.coverage, {"frames": visual.frames, "low_change_spans": visual.low_change_spans, "preprocess": visual.preprocess}, visual.failures)
    features = compute_shared_features(episode, config, producer_binding=unit.input_references.get("robot_profile"))
    needed = {"action_discontinuity", "idle_ratio"}
    source_failures = [kind for kind in (("action",) if unit.metric in needed else ("state",)) if features.numeric.get(kind, {}).get("status") in {"missing_source", "invalid_shape", "nonnumeric_source"}]
    if source_failures:
        return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION,
                                 config.effective_config_hash, Applicability.UNKNOWN,
                                 {"planned_samples": episode.num_frames, "attempted_samples": 0, "computed_samples": 0}, {},
                                 tuple({"reason": "source_unavailable", "source": kind} for kind in source_failures))
    values = {"numeric": features.numeric, "semantic_status": features.semantic_status}
    if config.robot is None:
        coverage = {"planned_samples": episode.num_frames, "attempted_samples": episode.num_frames, "computed_samples": 0}
        return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION, config.effective_config_hash,
                                 Applicability.UNKNOWN, coverage, values, ({"reason": "semantic_profile_missing"},))
    if unit.camera_or_dimension_group not in config.robot["dimension_groups"]:
        raise ValueError("plan unit dimension group is not configured")
    indices = {str(index) for index in config.robot["dimension_groups"][unit.camera_or_dimension_group]["indices"]}
    for source in ("action", "state"):
        dimensions = values["numeric"].get(source, {}).get("dimensions")
        if isinstance(dimensions, dict):
            values["numeric"][source]["dimensions"] = {index: fact for index, fact in dimensions.items() if index in indices}
    timestamp_error = features.numeric["timestamps"].get("status") != "ok"
    coverage = {"planned_samples": episode.num_frames, "attempted_samples": episode.num_frames,
                "computed_samples": 0 if timestamp_error else episode.num_frames}
    if timestamp_error:
        return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION, config.effective_config_hash,
                                 Applicability.UNKNOWN, coverage, values, ({"reason": "invalid_timestamps"},))
    return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION,
                             config.effective_config_hash, Applicability.APPLICABLE,
                             coverage, values, ())
