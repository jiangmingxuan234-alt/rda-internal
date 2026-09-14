"""Quality-only scoring of current MeasurementRecord values."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Iterable

from rda.quality.contracts import MeasurementRecord
from rda.calibration.reference import MetricStats, QualityReference


@dataclass(frozen=True)
class ScoredMeasurement:
    plan_unit_id: str
    metric_name: str
    value: float | None
    score: float | None
    reason_codes: tuple[str, ...] = ()
    group: Mapping[str, Any] | None = None
    evidence: tuple[Mapping[str, Any], ...] = ()


def _extract(values: Mapping[str, Any]):
    if isinstance(values.get("value"), (int, float)):
        return values["value"]
    for key in ("score", "deviation", "idle_ratio", "duration_sec", "spike_count"):
        if isinstance(values.get(key), (int, float)):
            return values[key]
    for v in values.values():
        if isinstance(v, Mapping):
            x = _extract(v)
            if x is not None:
                return x
    return None


def _stats(ref: Any, metric: str):
    metrics = ref.metrics if hasattr(ref, "metrics") else ref.get("metrics", {})
    s = metrics.get(metric)
    if isinstance(s, Mapping):
        return MetricStats(float(s["median"]), float(s["mad"]), float(s.get("p05", s["median"])), float(s.get("p25", s["median"])), float(s.get("p75", s["median"])), float(s.get("p95", s["median"])))
    return s


def score_measurements(records: Iterable[MeasurementRecord], reference: QualityReference | Mapping[str, Any], groups: Mapping[str, Any] | None = None) -> tuple[ScoredMeasurement, ...]:
    """Score records only; no EpisodeData or legacy metric constructors are touched."""
    out = []
    ref_count = getattr(reference, "sample_count", None)
    if ref_count is None and isinstance(reference, Mapping):
        ref_count = reference.get("sample_count", reference.get("n_calibration", 0))
    for record in records:
        group = (groups or {}).get(record.plan_unit_id, groups or {}) if isinstance(groups, Mapping) else {}
        value = _extract(record.values)
        reasons: list[str] = []
        if record.applicability.value != "APPLICABLE": reasons.append("APPLICABILITY_UNKNOWN")
        cov = record.coverage
        if cov.get("computed_samples", 0) <= 0 or cov.get("computed_samples") != cov.get("attempted_samples"):
            reasons.append("INCOMPLETE_COVERAGE")
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            reasons.append("MEASUREMENT_VALUE_MISSING")
        stats = _stats(reference, record.metric_name)
        applicability = getattr(reference, "applicability", None)
        if isinstance(applicability, Mapping) and applicability:
            for key, expected in applicability.items():
                if key in group and group.get(key) != expected:
                    reasons.append("REFERENCE_SCOPE_MISMATCH")
                    break
        if stats is None: reasons.append("REFERENCE_GROUP_MISSING")
        elif ref_count is not None and ref_count < 2: reasons.append("INSUFFICIENT_REFERENCE_SAMPLES")
        elif abs(float(stats.mad)) <= 1e-12 and abs(float(stats.iqr)) <= 1e-12: reasons.append("REFERENCE_DEGENERATE")
        score = None
        if not reasons:
            score = float((float(value) - float(stats.median)) / max(abs(float(stats.mad)), 1e-12))
        out.append(ScoredMeasurement(record.plan_unit_id, record.metric_name, None if value is None else float(value), score, tuple(reasons), group, tuple(record.evidence)))
    return tuple(out)
