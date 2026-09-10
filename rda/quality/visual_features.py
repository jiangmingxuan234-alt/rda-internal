"""Facts derived from bounded, PTS-verified visual decode results."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import numpy as np

from rda.quality.media import DecodedFrame, MediaDecodeResult


@dataclass(frozen=True)
class VisualFeatures:
    frames: tuple[Mapping[str, Any], ...]
    failures: tuple[Mapping[str, Any], ...]
    coverage: Mapping[str, int]
    low_change_spans: tuple[Mapping[str, int], ...]
    preprocess: Mapping[str, Any]


def _roi(gray: np.ndarray, value: Any) -> tuple[np.ndarray | None, str | None]:
    if value == "full":
        return gray, None
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None, "ROI must be 'full' or (y0, y1, x0, x1)"
    if any(isinstance(item, bool) or not isinstance(item, (int, np.integer)) for item in value):
        return None, "ROI coordinates must be integers"
    y0, y1, x0, x1 = (int(item) for item in value)
    height, width = gray.shape
    if y0 < 0 or x0 < 0 or y1 > height or x1 > width or y0 >= y1 or x0 >= x1:
        return None, "ROI must lie inside the decoded frame"
    crop = gray[y0:y1, x0:x1]
    if min(crop.shape) < 3:
        return None, "ROI must be at least 3 by 3 for interior Laplacian"
    return crop, None


def _gray(frame: Any) -> np.ndarray:
    pixels = np.asarray(frame)
    if pixels.ndim == 3:
        if pixels.shape[2] not in (1, 3, 4):
            raise ValueError("decoded frame must have one, three, or four channels")
        pixels = pixels[..., :3].mean(axis=2)
    if pixels.ndim != 2 or not np.issubdtype(pixels.dtype, np.number):
        raise ValueError("decoded frame must be a numeric grayscale or RGB image")
    values = pixels.astype(np.float64, copy=False)
    if not np.all(np.isfinite(values)):
        raise ValueError("decoded frame contains non-finite pixels")
    return values


def _laplacian_variance(gray: np.ndarray) -> float:
    interior = (-4.0 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1]
                + gray[1:-1, :-2] + gray[1:-1, 2:])
    return float(np.var(interior))


def compute_visual_features(
    frames: Iterable[DecodedFrame] | MediaDecodeResult, *, planned_samples: int,
    interval: tuple[float, float], preprocess: Mapping[str, Any],
    low_change_threshold: float,
) -> VisualFeatures:
    """Publish visual facts from actual PTS-mapped frames without fabricated coverage."""
    if not isinstance(preprocess, Mapping):
        raise ValueError("preprocess must be a mapping")
    if isinstance(planned_samples, bool) or not isinstance(planned_samples, int) or planned_samples < 0:
        raise ValueError("planned_samples must be a non-negative integer")
    if len(interval) != 2 or not np.all(np.isfinite(interval)) or interval[0] >= interval[1]:
        raise ValueError("interval must be an ordered finite pair")
    if not np.isfinite(low_change_threshold):
        raise ValueError("low_change_threshold must be finite")
    accepted: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    spans: list[dict[str, int]] = []
    run: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    decoded = targeted_failures = 0

    def close_run() -> None:
        nonlocal run
        if len(run) >= 2:
            spans.append({"start_ordinal": run[0]["ordinal"], "end_ordinal": run[-1]["ordinal"], "length": len(run)})
        run = []

    for source_ordinal, decoded_frame in enumerate(frames):
        decoded += 1
        if not isinstance(decoded_frame, DecodedFrame):
            raise TypeError("visual features require DecodedFrame values from decode_media_interval")
        if not interval[0] <= decoded_frame.mapped_timestamp < interval[1]:
            failures.append({"ordinal": source_ordinal, "reason": "pts_outside_interval", "mapped_timestamp": decoded_frame.mapped_timestamp})
            targeted_failures += 1; previous = None; close_run(); continue
        try:
            crop, roi_error = _roi(_gray(decoded_frame.frame), preprocess.get("roi", "full"))
            if roi_error:
                failures.append({"ordinal": source_ordinal, "reason": "invalid_roi", "detail": roi_error})
                targeted_failures += 1; previous = None; close_run(); continue
            assert crop is not None
        except ValueError as exc:
            failures.append({"ordinal": source_ordinal, "reason": "invalid_frame", "detail": str(exc)})
            targeted_failures += 1; previous = None; close_run(); continue
        item = {"ordinal": decoded_frame.decoded_frame_ordinal, "target_time": decoded_frame.target_time,
                "mapped_timestamp": decoded_frame.mapped_timestamp, "pts": decoded_frame.pts,
                "time_base": str(decoded_frame.time_base), "mapping_status": decoded_frame.mapping_status,
                "camera": getattr(getattr(frames, "ref", None), "feature_key", None),
                "sampling_error": decoded_frame.sampling_error,
                "blur_laplacian_variance": _laplacian_variance(crop), "mean_luminance": float(crop.mean()),
                "contrast_p5_p95": float(np.percentile(crop, 95) - np.percentile(crop, 5)),
                "clipped_dark_fraction": float(np.mean(crop <= 0.0)),
                "clipped_bright_fraction": float(np.mean(crop >= 255.0)), "_pixels": crop}
        accepted.append(item)
        contiguous = previous is not None and item["ordinal"] == previous["ordinal"] + 1
        low_change = contiguous and float(np.mean(np.abs(item["_pixels"] - previous["_pixels"]))) <= low_change_threshold
        if not low_change:
            close_run(); run = [item]
        else:
            run.append(item)
        previous = item
    close_run()
    for error in getattr(frames, "errors", ()):
        failures.append({"target_time": error.target_time, "reason": error.reason, "detail": error.detail})
        if error.target_time is not None:
            targeted_failures += 1
    for item in accepted:
        item.pop("_pixels")
    source_coverage = getattr(frames, "coverage", {})
    attempted = source_coverage.get("attempted", decoded)
    if isinstance(attempted, bool) or not isinstance(attempted, int) or attempted < 0:
        attempted = decoded
    coverage = {"planned_samples": planned_samples, "attempted_samples": attempted,
                "decoded_samples": decoded, "computed_samples": len(accepted),
                "failed_samples": targeted_failures}
    return VisualFeatures(tuple(accepted), tuple(failures), coverage, tuple(spans), dict(preprocess))
