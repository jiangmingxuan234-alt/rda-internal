from __future__ import annotations

import numpy as np

from rda.io.schema import EpisodeData
from rda.quality.config import QualityConfig
from rda.quality.features import compute_shared_features
from rda.quality.measurements import measure_unit
from rda.quality.execution_plan import build_plan


def _config(robot=None):
    value = {"contract_version": 1, "quality": {"metrics": [{"name": "action_discontinuity", "role": "informational", "parameters": {}}]}}
    if robot is not None:
        value["robot"] = robot
    return QualityConfig.from_mapping(value)


def _robot(representation="velocity"):
    return {
        "profile_id": "synthetic-arm", "action_field": "command", "state_field": "state",
        "action_representation": representation, "coordinate_frame": "base",
        "dimension_groups": {"arm": {"indices": [0], "physical_quantity": "angle", "unit": "rad"}},
        "cameras": [], "source_binding": {"profile_revision": "test", "profile_content_hash": "sha256:" + "a" * 64, "mapping_version": "test-v1", "mapping_hash": "sha256:" + "b" * 64},
    }


def _producer():
    return {"status": "complete", "profile_id": "synthetic-arm", "revision": "test", "raw_sha256": "sha256:" + "a" * 64}


def test_constant_nonzero_velocity_command_is_active_without_command_delta():
    episode = EpisodeData(0, 3, np.array([0., 1., 2.]), observation={"state": np.array([[0.], [1.], [2.]])}, action={"command": np.array([[2.], [2.], [2.]])})
    features = compute_shared_features(episode, _config(_robot()), producer_binding=_producer())
    assert features.numeric["action"]["dimensions"]["0"]["activity_count"] == 3
    assert features.numeric["action"]["dimensions"]["0"]["delta"]["p95"] == 0.0
    assert features.numeric["state"]["dimensions"]["0"]["derivative"]["unit"] == "rad/s"


def test_missing_profile_preserves_raw_values_but_not_physical_claims():
    episode = EpisodeData(0, 2, np.array([0., 1.]), observation={"state": np.array([[0.], [1.]])}, action={"command": np.array([[1.], [1.]])})
    features = compute_shared_features(episode, _config())
    assert features.numeric["raw_sources"]["action"]["command"] == [[1.0], [1.0]]
    assert features.semantic_status == "UNKNOWN"
    assert features.numeric["state"]["status"] == "missing_source"


def test_periodic_delta_requires_declared_period_and_degenerate_mad_keeps_spike_location():
    robot = _robot("absolute_position")
    robot["periodic_dimensions"] = [{"index": 0, "period": 360.0}]
    episode = EpisodeData(0, 4, np.arange(4.0), observation={"state": np.zeros((4, 1))}, action={"command": np.array([[359.], [1.], [1.], [1.]])})
    features = compute_shared_features(episode, _config(robot), producer_binding=_producer())
    dimension = features.numeric["action"]["dimensions"]["0"]
    assert dimension["delta"]["values"] == [2.0, 0.0, 0.0]
    assert dimension["delta"]["mad_status"] == "mad_degenerate"
    assert dimension["delta"]["non_median_locations"] == [0]


def test_measurement_record_is_versioned_fact_and_delegated_metric_is_unassessed():
    config = _config(_robot())
    episode = EpisodeData(0, 2, np.array([0., 1.]), observation={"state": np.array([[0.], [1.]])}, action={"command": np.array([[1.], [1.]])})
    unit = build_plan([{"episode_id": "0", "metric": "joint_limit", "camera_or_dimension_group": "arm", "input_references": {}, "requested_config_hash": config.requested_config_hash, "effective_config_hash": config.effective_config_hash, "sampling_range": {}, "resource_estimate": {}}]).units[0]
    record = measure_unit(unit, episode, None, config)
    assert record.metric_name == "joint_limit"
    assert record.applicability == "UNKNOWN"
    assert record.values == {}
    assert record.evidence[0]["reason"] == "delegated_to_robovet"
