"""Fixed-grid observational coverage; never a reachability verdict."""
from __future__ import annotations
import math
import hashlib, json
from dataclasses import dataclass
from typing import Iterable, Mapping, Any

@dataclass(frozen=True)
class CoverageResult:
    status: str
    occupied_bins: int
    total_bins: int
    occupancy_ratio: float | None
    reason_codes: tuple[str, ...] = ()
    grid_hash: str | None = None

@dataclass(frozen=True)
class GridConfig:
    bounds: tuple[tuple[float, float], ...]
    bins: tuple[int, ...]
    units: tuple[str, ...] | None = None
    frame: str | None = None
    def as_mapping(self) -> dict[str, Any]:
        return {"bounds": self.bounds, "bins": self.bins, "units": self.units, "frame": self.frame}
    @property
    def grid_hash(self):
        return hashlib.sha256(json.dumps(self.as_mapping(), sort_keys=True, default=list).encode()).hexdigest()

def fixed_grid_coverage(points: Iterable[Iterable[float]], config: Mapping[str, Any] | None) -> CoverageResult:
    if isinstance(config, GridConfig):
        config = config.as_mapping()
    if not config: return CoverageResult("UNASSESSED", 0, 0, None, ("FIXED_GRID_NOT_CONFIGURED",))
    bounds, bins = config.get("bounds"), config.get("bins")
    if config.get("units") is None or config.get("frame") is None:
        return CoverageResult("UNASSESSED", 0, 0, None, ("GRID_SEMANTICS_MISSING",))
    if not isinstance(bounds, (list, tuple)) or not isinstance(bins, (list, tuple)) or len(bounds) != len(bins) or not bounds:
        return CoverageResult("UNASSESSED", 0, 0, None, ("FIXED_GRID_INVALID",))
    total = 1
    for bound, n in zip(bounds, bins):
        if not isinstance(bound, (list, tuple)) or len(bound) != 2 or bound[1] <= bound[0] or not isinstance(n, int) or n <= 0: return CoverageResult("UNASSESSED", 0, 0, None, ("FIXED_GRID_INVALID",))
        total *= n
    occupied = set(); out_of_bounds = 0
    for point in points:
        if len(point) != len(bounds) or any(not math.isfinite(float(x)) for x in point): continue
        idx=[]
        for x, (lo, hi), n in zip(point, bounds, bins):
            if x < lo or x > hi: out_of_bounds += 1; break
            idx.append(min(n-1, int((x-lo)/(hi-lo)*n)))
        else: occupied.add(tuple(idx))
    reasons = ("POINTS_OUT_OF_BOUNDS",) if out_of_bounds else ()
    gh = hashlib.sha256(json.dumps(config, sort_keys=True, default=list).encode()).hexdigest()
    return CoverageResult("ASSESSED", len(occupied), total, len(occupied)/total, reasons, gh)
