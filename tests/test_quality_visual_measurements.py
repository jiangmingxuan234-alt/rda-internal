from __future__ import annotations

from fractions import Fraction

import numpy as np

from rda.quality.media import DecodedFrame
from rda.quality.visual_features import compute_visual_features


def _frame(
    target_time: float,
    mapped_timestamp: float,
    ordinal: int,
    pixels: np.ndarray,
) -> DecodedFrame:
    return DecodedFrame(
        target_time=target_time,
        pts=10 + ordinal,
        time_base=Fraction(1, 10),
        decoded_frame_ordinal=ordinal,
        lerobot_frame_index=None,
        mapped_timestamp=mapped_timestamp,
        sampling_error=mapped_timestamp - target_time,
        mapping_status="mapped",
        frame=pixels,
    )


def test_visual_features_report_actual_coverage_pts_and_low_change_spans():
    frames = [
        _frame(0.0, 0.0, 0, np.zeros((8, 8), dtype=np.uint8)),
        _frame(0.2, 0.2, 1, np.zeros((8, 8), dtype=np.uint8)),
        _frame(0.4, 1.2, 2, np.ones((8, 8), dtype=np.uint8)),
    ]
    result = compute_visual_features(frames, planned_samples=10, interval=(0.0, 1.0), preprocess={"roi": "full", "grayscale": True}, low_change_threshold=1.0)
    assert result.coverage == {"planned_samples": 10, "attempted_samples": 3, "decoded_samples": 3, "computed_samples": 2, "failed_samples": 1}
    assert result.frames[0]["pts"] == 10
    assert result.low_change_spans[0]["start_ordinal"] == 0
    assert result.low_change_spans[0]["end_pts"] == 11
    assert result.failures[0]["reason"] == "pts_outside_interval"


def test_invalid_or_outside_roi_records_no_fake_visual_measurement():
    result = compute_visual_features(
        [_frame(0.0, 0.0, 0, np.zeros((8, 8), dtype=np.uint8))],
        planned_samples=1,
        interval=(0.0, 1.0),
        preprocess={"roi": (0, 9, 0, 8), "grayscale": True},
        low_change_threshold=1.0,
    )

    assert result.coverage == {"planned_samples": 1, "attempted_samples": 1, "decoded_samples": 1, "computed_samples": 0, "failed_samples": 1}
    assert result.failures == ({"ordinal": 0, "reason": "invalid_roi", "detail": "ROI must lie inside the decoded frame"},)


def test_low_change_spans_do_not_cross_rejected_pts_or_missing_ordinals():
    black = np.zeros((8, 8), dtype=np.uint8)
    result = compute_visual_features(
        [
            _frame(0.0, 0.0, 0, black),
            _frame(0.1, 0.1, 1, black),
            _frame(0.2, 1.2, 2, black),
            _frame(0.3, 0.3, 3, black),
            _frame(0.4, 0.4, 4, black),
        ],
        planned_samples=5,
        interval=(0.0, 1.0),
        preprocess={"roi": "full", "grayscale": True},
        low_change_threshold=1.0,
    )

    assert [(span["start_ordinal"], span["end_ordinal"]) for span in result.low_change_spans] == [(0, 1), (3, 4)]


def test_visual_features_use_interior_laplacian_and_publish_exposure_clipping():
    pixels = np.zeros((8, 8), dtype=np.uint8)
    pixels[0, :] = 255  # Border-only energy must not inflate the interior focus fact.
    pixels[2:6, 2:6] = 255
    result = compute_visual_features(
        [_frame(0.0, 0.0, 0, pixels)],
        planned_samples=1,
        interval=(0.0, 1.0),
        preprocess={"roi": (1, 7, 1, 7), "grayscale": True},
        low_change_threshold=1.0,
    )

    frame = result.frames[0]
    assert frame["blur_laplacian_variance"] > 0.0
    assert frame["clipped_dark_fraction"] > 0.0
    assert frame["clipped_bright_fraction"] > 0.0
    assert frame["contrast_p5_p95"] == 255.0
