"""Metric-local rules for quality measurements."""
from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Mapping

from rda.quality.contracts import Assessment, Applicability, ExecutionState, MeasurementRecord, UnitResult


@dataclass(frozen=True)
class RuleContext:
    rule_id: str
    rule_version: str | None
    applicable_scope: Mapping[str, Any] | None = None
    threshold: Mapping[str, Any] | Any = None
    calibration_id: str | None = None


def _get(rule: Any, name: str, default=None):
    return rule.get(name, default) if isinstance(rule, Mapping) else getattr(rule, name, default)


def _value(record: MeasurementRecord, path: str | None):
    cur: Any = record.values
    if path:
        for p in path.split("."):
            if isinstance(cur, Mapping) and p in cur:
                cur = cur[p]
            else:
                return None
    if isinstance(cur, (int, float)) and not isinstance(cur, bool):
        return cur
    if isinstance(cur, Mapping) and "value" in cur:
        return cur["value"]
    return None


def evaluate_measurement(record: MeasurementRecord, rule: Any, context: RuleContext | None = None) -> UnitResult:
    """Evaluate one completed measurement without consulting episode data."""
    if context is None:
        # Accept the standard quality config spelling as a compatibility
        # adapter (version/scope/thresholds and nested calibration).
        calibration = _get(rule, "calibration", {}) or {}
        status = _get(rule, "calibration_status", "")
        calibration = _get(rule, "calibration", {}) or {}
        inferred_kind = "calibrated_rule" if status == "calibrated" else "provisional"
        context = RuleContext(str(_get(rule, "rule_id", _get(rule, "name", "unknown"))),
                              _get(rule, "rule_version", _get(rule, "version")),
                              _get(rule, "applicable_scope", _get(rule, "scope")),
                              _get(rule, "threshold", _get(rule, "thresholds")),
                              _get(rule, "calibration_id", _get(calibration, "calibration_id"))) if rule else RuleContext("none", None)
    base = dict(record.coverage)
    base.setdefault("sampling_complete", base.get("planned_samples", 0) == base.get("attempted_samples", -1) == base.get("computed_samples", -2) and base.get("planned_samples", 0) > 0)
    if record.applicability is not Applicability.APPLICABLE:
        return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("APPLICABILITY_UNKNOWN" if record.applicability is Applicability.UNKNOWN else "NOT_APPLICABLE",))
    if rule is None:
        return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("RULE_NOT_CONFIGURED",))
    rule_id, version = context.rule_id, context.rule_version
    scope = _get(rule, "applicable_scope", None)
    if scope is not None and (context.applicable_scope is None or dict(scope) != dict(context.applicable_scope)):
        return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("RULE_SCOPE_MISMATCH",), rule_id, version)
    kind = _get(rule, "kind", _get(rule, "type", "calibrated_rule" if _get(rule, "calibration_status") == "calibrated" else "provisional"))
    threshold = context.threshold if context.threshold is not None else _get(rule, "threshold", None)
    if isinstance(threshold, Mapping) and "value" not in threshold and len(threshold) == 1:
        threshold = next(iter(threshold.values()))
    if threshold is None:
        return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("THRESHOLD_MISSING",), rule_id, version)
    val = _value(record, _get(rule, "path", None))
    if val is None:
        return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("MEASUREMENT_VALUE_MISSING",), rule_id, version)
    if kind in {"calibrated", "calibrated_rule"}:
        source = dict(_get(rule, "rule_source", {}) or {})
        source.setdefault("kind", "calibrated_rule"); source.setdefault("rule_id", rule_id); source.setdefault("rule_version", version); source.setdefault("calibration_id", context.calibration_id or _get(rule, "calibration_id"))
        source.setdefault("calibration_hash", _get(rule, "calibration_hash", ""))
        if not version or not source.get("calibration_id") or not source.get("calibration_hash"):
            return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("CALIBRATION_PROVENANCE_MISSING",), rule_id, version, source)
        # Task1 identity fields, when declared by the rule, must be complete.
        declared = ("profile_revision", "profile_content_hash", "mapping_version", "mapping_hash", "task", "camera", "dimensions", "units")
        if any(k in source for k in declared) and any(not source.get(k) for k in declared):
            return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("CALIBRATION_PROVENANCE_MISMATCH",), rule_id, version, source)
        if base.get("planned_samples") != base.get("attempted_samples") or base.get("attempted_samples") != base.get("computed_samples") or base.get("computed_samples", 0) <= 0:
            return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, Assessment.UNASSESSED, base, record.values, record.evidence, ("INCOMPLETE_COVERAGE",), rule_id, version, source)
    op_name = _get(rule, "operator", "gt")
    target = threshold.get("value") if isinstance(threshold, Mapping) else threshold
    passed = True if target is None else {"gt": operator.gt, "gte": operator.ge, "ge": operator.ge, "lt": operator.lt, "lte": operator.le, "le": operator.le, "eq": operator.eq}.get(op_name, operator.gt)(val, target)
    if kind in {"provisional", "heuristic", "temporary"}:
        assessment, reasons = Assessment.REVIEW, ("PROVISIONAL_RULE", "PROVISIONAL_SOURCE")
    else:
        assessment, reasons = (Assessment.EXCLUDE_CANDIDATE, ("CALIBRATED_RULE_MATCH",)) if passed else (Assessment.PASS, ("CALIBRATED_RULE_CLEAR",))
    finding = {"measurement": val, "threshold": threshold, "rule_id": rule_id, "rule_version": version, "calibration_id": context.calibration_id, "calibration_hash": source.get("calibration_hash") if kind in {"calibrated", "calibrated_rule"} else None, "evidence_level": "computed", "locator": _get(rule, "locator", None)}
    return UnitResult(record.plan_unit_id, record.applicability, ExecutionState.COMPUTED, assessment, base, record.values, tuple(record.evidence) + (finding,), reasons, rule_id, version, source if kind in {"calibrated", "calibrated_rule"} else {"kind": "provisional", "rule_id": rule_id, "rule_version": version})
