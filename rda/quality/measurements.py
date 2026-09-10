"""Translate one explicit plan unit into a versioned measurement record."""
from __future__ import annotations

from typing import Any

from rda.io.schema import EpisodeData
from rda.quality.config import QualityConfig
from rda.quality.contracts import Applicability, MeasurementRecord
from rda.quality.execution_plan import PlanUnit
from rda.quality.features import ALGORITHM_VERSION, compute_shared_features


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
    features = compute_shared_features(episode, config)
    source_failures = [kind for kind in ("action", "state") if features.numeric.get(kind, {}).get("status") in {"missing_source", "invalid_shape"}]
    if source_failures:
        return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION,
                                 config.effective_config_hash, Applicability.UNKNOWN,
                                 {"planned_samples": episode.num_frames, "attempted_samples": 0, "computed_samples": 0}, {},
                                 tuple({"reason": "source_unavailable", "source": kind} for kind in source_failures))
    values = {"numeric": features.numeric, "semantic_status": features.semantic_status}
    coverage = {"planned_samples": episode.num_frames, "attempted_samples": episode.num_frames,
                "computed_samples": episode.num_frames}
    return MeasurementRecord(unit.plan_unit_id, unit.metric, ALGORITHM_VERSION,
                             config.effective_config_hash, Applicability.APPLICABLE,
                             coverage, values, ())
