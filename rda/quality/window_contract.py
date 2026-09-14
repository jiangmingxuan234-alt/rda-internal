"""Explicit contract for comparing RDA windows with a training loader."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


@dataclass(frozen=True)
class TrainingWindow:
    index: int
    episode_index: int | str
    observation_frames: tuple[int, ...]
    action_frames: tuple[int, ...]
    padding_mask: tuple[bool, ...]
    delta_t: tuple[float, ...]
    camera_tolerance: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise ValueError("window index must be a non-negative integer")
        if not str(self.episode_index).strip():
            raise ValueError("episode_index must be non-empty")
        for name in ("observation_frames", "action_frames"):
            vals = tuple(getattr(self, name))
            if not vals or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in vals):
                raise ValueError(f"{name} must contain non-negative frame indices")
            object.__setattr__(self, name, vals)
        mask = tuple(self.padding_mask)
        if len(mask) != len(self.observation_frames) or any(type(v) is not bool for v in mask):
            raise ValueError("padding_mask must match observation_frames")
        object.__setattr__(self, "padding_mask", mask)
        dt = tuple(float(v) for v in self.delta_t)
        if len(dt) not in (0, len(self.observation_frames)):
            raise ValueError("delta_t must be empty or match observation_frames")
        object.__setattr__(self, "delta_t", dt)
        if self.camera_tolerance is not None and float(self.camera_tolerance) < 0:
            raise ValueError("camera_tolerance must be non-negative")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TrainingWindow":
        return cls(value["index"], value["episode_index"], tuple(value["observation_frames"]),
                   tuple(value["action_frames"]), tuple(value["padding_mask"]),
                   tuple(value.get("delta_t", ())), value.get("camera_tolerance"))


def load_training_windows(path_or_provider: Any, profile: Mapping[str, Any] | None = None) -> Iterator[TrainingWindow]:
    """Load windows from an explicit provider or JSONL export.

    A missing provider is deliberately an empty iterator; callers must mark
    loader alignment UNASSESSED rather than treating it as an empty dataset.
    """
    if path_or_provider is None:
        return iter(())
    if hasattr(path_or_provider, "iter_training_windows"):
        return (TrainingWindow.from_mapping(w) if isinstance(w, Mapping) else w
                for w in path_or_provider.iter_training_windows(profile))
    if callable(path_or_provider):
        return (TrainingWindow.from_mapping(w) if isinstance(w, Mapping) else w
                for w in path_or_provider(profile))
    path = Path(path_or_provider)
    def _read() -> Iterator[TrainingWindow]:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield TrainingWindow.from_mapping(json.loads(line))
    return _read()


@dataclass(frozen=True)
class WindowParityReport:
    alignment: str
    missing_indices: tuple[int, ...] = ()
    extra_indices: tuple[int, ...] = ()
    mismatches: tuple[Mapping[str, Any], ...] = ()


def compare_window_indices(rda_windows: Iterable[TrainingWindow], training_windows: Iterable[TrainingWindow]) -> WindowParityReport:
    left = {w.index: w for w in rda_windows}
    right = {w.index: w for w in training_windows}
    missing = tuple(sorted(set(left) - set(right)))
    extra = tuple(sorted(set(right) - set(left)))
    mismatches: list[Mapping[str, Any]] = []
    for idx in sorted(set(left) & set(right)):
        a, b = left[idx], right[idx]
        for field in ("episode_index", "observation_frames", "action_frames", "padding_mask", "delta_t", "camera_tolerance"):
            if getattr(a, field) != getattr(b, field):
                mismatches.append({"window_index": idx, "field": field, "rda": getattr(a, field), "training": getattr(b, field)})
    alignment = "ALIGNED" if not missing and not extra and not mismatches else "MISMATCH"
    return WindowParityReport(alignment, missing, extra, tuple(mismatches))
