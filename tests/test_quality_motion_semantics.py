from __future__ import annotations

import numpy as np

from rda.io.schema import EpisodeData
from rda.quality.config import QualityConfig
from rda.quality.features import compute_shared_features


def test_wrapped_bound_state_derivative_uses_shortest_delta():
    config = QualityConfig.from_mapping({"contract_version": 1, "quality": {"metrics": []}, "robot": {"profile_id": "r", "action_field": "a", "state_field": "s", "action_representation": "absolute_position", "coordinate_frame": "base", "dimension_groups": {"joint": {"indices": [0], "physical_quantity": "angle", "unit": "deg"}}, "periodic_dimensions": [{"index": 0, "period": 360}], "cameras": [], "source_binding": {"profile_revision": "1", "profile_content_hash": "sha256:" + "a" * 64, "mapping_version": "v1", "mapping_hash": "sha256:" + "b" * 64}}})
    episode = EpisodeData(0, 2, np.array([0., 1.]), observation={"s": np.array([[359.], [1.]])}, action={"a": np.zeros((2, 1))})
    producer = {"status": "complete", "profile_id": "r", "revision": "1", "raw_sha256": "sha256:" + "a" * 64}
    features = compute_shared_features(episode, config, producer_binding=producer)
    assert features.numeric["state"]["dimensions"]["0"]["derivative"]["median"] == 2.0


def test_temporal_facts_and_velocity_activity_publish_runs_without_verdict():
    config = QualityConfig.from_mapping({"contract_version": 1, "quality": {"metrics": []}, "robot": {"profile_id": "r", "action_field": "a", "state_field": "s", "action_representation": "velocity", "coordinate_frame": "base", "dimension_groups": {"joint": {"indices": [0], "physical_quantity": "angle", "unit": "deg"}}, "cameras": [], "source_binding": {"profile_revision": "1", "profile_content_hash": "sha256:" + "a" * 64, "mapping_version": "v1", "mapping_hash": "sha256:" + "b" * 64}}})
    episode = EpisodeData(0, 4, np.array([0., .2, .5, .7]), observation={"s": np.array([[0.], [1.], [3.], [6.]])}, action={"a": np.array([[0.], [2.], [2.], [0.]])})
    features = compute_shared_features(episode, config, producer_binding={"status": "complete", "profile_id": "r", "revision": "1", "raw_sha256": "sha256:" + "a" * 64})
    assert features.numeric["timestamps"]["duration"] == .7
    assert features.numeric["action"]["dimensions"]["0"]["activity_runs"] == [{"start": 1, "end": 2, "length": 2}]
    assert features.numeric["state"]["dimensions"]["0"]["derivative"]["acceleration"]["sample_count"] == 2
