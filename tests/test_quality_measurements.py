from __future__ import annotations

import numpy as np

from rda.io.schema import EpisodeData
from rda.quality.config import QualityConfig
from rda.quality.features import compute_shared_features
from rda.quality.measurements import measure_unit
from rda.quality.execution_plan import build_plan
from tests.test_quality_semantic_binding import bound_robot, profile_facts, seal_mapping


def _config(robot=None):
    value = {"contract_version": 1, "quality": {"metrics": [{"name": "action_discontinuity", "role": "informational", "parameters": {}}]}}
    if robot is not None:
        value["robot"] = robot
    return QualityConfig.from_mapping(value)


def _robot(representation="absolute_position"):
    robot = bound_robot()
    if representation == "velocity":
        robot["source_binding"]["source_profile"]["signals"][0].update(quantity="angular_velocity", unit="rad/s")
        robot["signal_mappings"]["action"]["groups"]["arm"].update(representation="velocity", physical_quantity="angular_velocity", unit="rad/s")
    else:
        for source in ("action", "state"):
            robot["signal_mappings"][source]["groups"]["arm"]["representation"] = representation
    seal_mapping(robot)
    return robot


def _producer():
    return profile_facts()


def test_constant_nonzero_velocity_command_is_active_without_command_delta():
    episode = EpisodeData(0, 3, np.array([0., 1., 2.]), observation={"state": np.array([[0., 0.], [1., 0.], [2., 0.]], dtype=np.float32)}, action={"action": np.array([[2., 0.], [2., 0.], [2., 0.]], dtype=np.float32)})
    robot = _robot("velocity")
    features = compute_shared_features(episode, _config(robot), producer_binding=robot["source_binding"]["source_profile"])
    assert features.numeric["action"]["dimensions"]["0"]["activity_count"] == 3
    assert features.numeric["action"]["dimensions"]["0"]["delta"]["p95"] == 0.0
    assert features.numeric["state"]["dimensions"]["0"]["derivative"]["unit"] == "rad/s"


def test_missing_profile_preserves_raw_values_but_not_physical_claims():
    episode = EpisodeData(0, 2, np.array([0., 1.]), observation={"state": np.array([[0.], [1.]])}, action={"command": np.array([[1.], [1.]])})
    features = compute_shared_features(episode, _config())
    assert features.numeric["raw_sources"]["action"]["command"]["dimensions"]["0"]["finite_count"] == 2
    assert features.semantic_status == "UNKNOWN"
    assert features.numeric["state"]["status"] == "missing_source"


def test_periodic_delta_requires_declared_period_and_degenerate_mad_keeps_spike_location():
    robot = _robot("absolute_position")
    for source in ("action", "state"):
        robot["signal_mappings"][source]["groups"]["arm"]["periodic_dimensions"] = [{"index": 0, "period": 360}]
    seal_mapping(robot)
    episode = EpisodeData(0, 4, np.arange(4.0), observation={"state": np.zeros((4, 2), dtype=np.float32)}, action={"action": np.array([[359., 0.], [1., 0.], [1., 0.], [1., 0.]], dtype=np.float32)})
    features = compute_shared_features(episode, _config(robot), producer_binding=_producer())
    dimension = features.numeric["action"]["dimensions"]["0"]
    assert dimension["delta"]["values"] == [2.0, 0.0, 0.0]
    assert dimension["delta"]["mad_status"] == "mad_degenerate"
    assert dimension["delta"]["non_median_locations"] == [0]


def test_measurement_record_is_versioned_fact_and_delegated_metric_is_unassessed():
    config = _config(_robot())
    episode = EpisodeData(0, 2, np.array([0., 1.]), observation={"state": np.array([[0., 0.], [1., 0.]], dtype=np.float32)}, action={"action": np.array([[1., 0.], [1., 0.]], dtype=np.float32)})
    unit = build_plan([{"episode_id": "0", "metric": "joint_limit", "camera_or_dimension_group": "arm", "input_references": {}, "requested_config_hash": config.requested_config_hash, "effective_config_hash": config.effective_config_hash, "sampling_range": {}, "resource_estimate": {}}]).units[0]
    record = measure_unit(unit, episode, None, config)
    assert record.metric_name == "joint_limit"
    assert record.applicability == "UNKNOWN"
    assert record.values == {}
    assert record.evidence[0]["reason"] == "delegated_to_robovet"


def test_measure_unit_fails_closed_for_episode_or_unprovided_sampling_window():
    config = _config(_robot())
    episode = EpisodeData(0, 2, np.array([0., 1.]), observation={"state": np.array([[0., 0.], [1., 0.]], dtype=np.float32)}, action={"action": np.array([[1., 0.], [1., 0.]], dtype=np.float32)})
    spec = {"episode_id": "0", "metric": "action_discontinuity", "camera_or_dimension_group": "arm", "input_references": {"robot_profile": profile_facts()}, "requested_config_hash": config.requested_config_hash, "effective_config_hash": config.effective_config_hash, "sampling_range": {"from_timestamp": 0.2, "to_timestamp": 0.8}, "resource_estimate": {}}
    unit = build_plan([spec]).units[0]
    record = measure_unit(unit, episode, None, config)
    assert record.applicability == "UNKNOWN"
    assert record.evidence[0]["reason"] == "sampling_range_requires_window_provider"
