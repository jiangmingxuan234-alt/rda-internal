from __future__ import annotations

import numpy as np

from rda.io.schema import EpisodeData
from rda.quality.config import QualityConfig
from rda.quality.features import compute_shared_features
from tests.test_quality_semantic_binding import bound_robot, profile_facts, seal_mapping


def _config(periodic=False):
    robot = bound_robot()
    if periodic:
        for source in ("action", "state"):
            robot["signal_mappings"][source]["groups"]["arm"]["periodic_dimensions"] = [{"index": 0, "period": 360}]
    seal_mapping(robot)
    return QualityConfig.from_mapping({"contract_version": 1, "quality": {"metrics": []}, "robot": robot})


def test_wrapped_bound_state_derivative_uses_shortest_delta():
    config = _config(periodic=True)
    episode = EpisodeData(0, 2, np.array([0., 1.]), observation={"state": np.array([[359., 0.], [1., 0.]], dtype=np.float32)}, action={"action": np.zeros((2, 2), dtype=np.float32)})
    features = compute_shared_features(episode, config, producer_binding=profile_facts())
    assert features.numeric["state"]["dimensions"]["0"]["derivative"]["median"] == 2.0


def test_temporal_facts_and_velocity_activity_publish_runs_without_verdict():
    config = _config()
    episode = EpisodeData(0, 4, np.array([0., .2, .5, .7]), observation={"state": np.array([[0., 0.], [1., 0.], [3., 0.], [6., 0.]], dtype=np.float32)}, action={"action": np.array([[0., 0.], [2., 0.], [2., 0.], [0., 0.]], dtype=np.float32)})
    features = compute_shared_features(episode, config, producer_binding=profile_facts())
    assert features.numeric["timestamps"]["duration"] == .7
    assert features.numeric["state"]["dimensions"]["0"]["derivative"]["acceleration"]["sample_count"] == 2
