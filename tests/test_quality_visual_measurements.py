from __future__ import annotations

import numpy as np

from rda.quality.features import compute_visual_features


def test_visual_features_report_actual_coverage_pts_and_low_change_spans():
    frames = [
        {"target_time": 0.0, "mapped_timestamp": 0.0, "pts": 10, "camera": "front", "frame": np.zeros((8, 8), dtype=np.uint8)},
        {"target_time": 0.2, "mapped_timestamp": 0.2, "pts": 12, "camera": "front", "frame": np.zeros((8, 8), dtype=np.uint8)},
        {"target_time": 0.4, "mapped_timestamp": 1.2, "pts": 20, "camera": "front", "frame": np.ones((8, 8), dtype=np.uint8)},
    ]
    result = compute_visual_features(frames, planned_samples=10, interval=(0.0, 1.0), preprocess={"roi": "full", "grayscale": True}, low_change_threshold=1.0)
    assert result.coverage == {"planned_samples": 10, "attempted_samples": 3, "computed_samples": 2, "failed_samples": 1}
    assert result.frames[0]["pts"] == 10
    assert result.low_change_spans == ({"start_ordinal": 0, "end_ordinal": 1, "length": 2},)
    assert result.failures[0]["reason"] == "pts_outside_interval"
