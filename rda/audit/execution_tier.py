"""D-17: Execution tier definitions for video audit layered execution model.

Three-tier model:
  - Fast Audit (default): Video Integrity + Video Temporal + all non-visual-quality metrics
  - Video Quality (opt-in): All metrics including visual_quality
  - Full Audit: All metrics including visual quality

Additional modes:
  - no-video: Skip ALL video-related metrics
  - video-only: Only video-related metrics
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, Optional, Set


class ExecutionTier(str, Enum):
    """Execution tier for the audit pipeline."""
    FAST = "fast"
    VIDEO_QUALITY = "video_quality"
    NO_VIDEO = "no_video"
    VIDEO_ONLY = "video_only"
    FULL = "full"


# All video-related metric names
VIDEO_METRICS: FrozenSet[str] = frozenset({
    # L1 - Video Integrity
    "video_frame_integrity",
    "video_freeze",
    "video_timestamp_alignment",
    "video_stream_presence",
    # L2 - Visual Quality
    "visual_quality",
    # L2 - Video Temporal
    "video_stream_span_consistency",
    "video_stream_temporal_offset",
    "video_stream_temporal_drift",
})

# Visual quality metrics (opt-in subset of video metrics)
VISUAL_QUALITY_METRICS: FrozenSet[str] = frozenset({
    "visual_quality",
})

# Video integrity + temporal metrics (always run in fast mode)
VIDEO_INTEGRITY_TEMPORAL_METRICS: FrozenSet[str] = VIDEO_METRICS - VISUAL_QUALITY_METRICS


def get_tier_config(tier: ExecutionTier) -> Dict:
    """Get the metric inclusion/exclusion configuration for an execution tier.

    Returns a dict with:
      - exclude_metrics: set of metric names to exclude
      - include_only: set of metric names to include (None = include all minus excludes)
      - description: human-readable description
      - video_quality_executed: whether visual_quality was actually run
    """
    configs = {
        ExecutionTier.FAST: {
            "exclude_metrics": VISUAL_QUALITY_METRICS,
            "include_only": None,
            "description": "Fast Audit — all metrics except visual quality",
            "video_quality_executed": False,
        },
        ExecutionTier.VIDEO_QUALITY: {
            "exclude_metrics": frozenset(),
            "include_only": None,
            "description": "Video Quality Audit — all metrics including visual quality",
            "video_quality_executed": True,
        },
        ExecutionTier.NO_VIDEO: {
            "exclude_metrics": VIDEO_METRICS,
            "include_only": None,
            "description": "No Video — skip all video-related metrics",
            "video_quality_executed": False,
        },
        ExecutionTier.VIDEO_ONLY: {
            "exclude_metrics": frozenset(),
            "include_only": VIDEO_METRICS,
            "description": "Video Only — only video-related metrics",
            "video_quality_executed": True,
        },
        ExecutionTier.FULL: {
            "exclude_metrics": frozenset(),
            "include_only": None,
            "description": "Full Audit — all metrics including visual quality",
            "video_quality_executed": True,
        },
    }
    return configs[tier]


def filter_metrics_by_tier(all_metric_names: Set[str], tier: ExecutionTier) -> Set[str]:
    """Given all available metric names and an execution tier, return the
    set of metric names that should be executed."""
    config = get_tier_config(tier)
    result = set(all_metric_names)

    # Apply exclusions
    result -= config["exclude_metrics"]

    # Apply inclusion filter
    if config["include_only"] is not None:
        result &= config["include_only"]

    return result
