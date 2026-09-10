"""Stable execution planning and terminal-result reconciliation."""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from rda.quality.config import canonical_json
from rda.quality.contracts import (
    Applicability,
    ExecutionState,
    FrozenDict,
    UnitResult,
    freeze_json,
    thaw_json,
)


@dataclass(frozen=True)
class PlanUnit:
    plan_unit_id: str
    episode_id: str
    metric: str
    camera_or_dimension_group: str
    input_references: Mapping[str, Any]
    requested_config_hash: str
    effective_config_hash: str
    sampling_range: Mapping[str, Any]
    resource_estimate: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in (
            "plan_unit_id", "episode_id", "metric", "camera_or_dimension_group",
            "requested_config_hash", "effective_config_hash",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("input_references", "sampling_range", "resource_estimate"):
            frozen = freeze_json(getattr(self, name), path=name)
            if not isinstance(frozen, FrozenDict):
                raise TypeError(f"{name} must be a mapping")
            object.__setattr__(self, name, frozen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_unit_id": self.plan_unit_id,
            "episode_id": self.episode_id,
            "metric": self.metric,
            "camera_or_dimension_group": self.camera_or_dimension_group,
            "input_references": thaw_json(self.input_references),
            "requested_config_hash": self.requested_config_hash,
            "effective_config_hash": self.effective_config_hash,
            "sampling_range": thaw_json(self.sampling_range),
            "resource_estimate": thaw_json(self.resource_estimate),
        }


@dataclass(frozen=True)
class AttemptRecord:
    plan_unit_id: str
    attempt: int
    state: str
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.plan_unit_id, str) or not self.plan_unit_id:
            raise ValueError("attempt plan_unit_id must be non-empty")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))


@dataclass(frozen=True)
class ExecutionPlan:
    units: tuple[PlanUnit, ...]
    attempts: tuple[AttemptRecord, ...] = ()

    def validate_terminal_results(self, results: Iterable[UnitResult]) -> None:
        validate_terminal_results(self, results)

    def coverage_summary(self, results: Iterable[UnitResult]) -> dict[str, Any]:
        return coverage_summary(self, results)


def _unit_id(fields: Mapping[str, Any]) -> str:
    identity = {
        "episode_id": fields["episode_id"],
        "metric": fields["metric"],
        "camera_or_dimension_group": fields["camera_or_dimension_group"],
        "input_references": fields["input_references"],
        "requested_config_hash": fields["requested_config_hash"],
        "effective_config_hash": fields["effective_config_hash"],
        "sampling_range": fields["sampling_range"],
    }
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return "quality-unit:" + digest


def build_plan(
    unit_specs: Iterable[PlanUnit | Mapping[str, Any]],
    *,
    attempts: Iterable[AttemptRecord] = (),
) -> ExecutionPlan:
    """Build an immutable plan, deriving stable IDs for mapping specs."""
    units: list[PlanUnit] = []
    for spec in unit_specs:
        if isinstance(spec, PlanUnit):
            unit = spec
        else:
            values = dict(spec)
            supplied_id = values.pop("plan_unit_id", None)
            derived_id = _unit_id(values)
            if supplied_id is not None and supplied_id != derived_id:
                raise ValueError("supplied plan_unit_id does not match plan inputs")
            unit = PlanUnit(plan_unit_id=derived_id, **values)
        units.append(unit)
    ids = [unit.plan_unit_id for unit in units]
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate plan units: {duplicates}")
    return ExecutionPlan(tuple(units), tuple(attempts))


def validate_terminal_results(plan: ExecutionPlan, results: Iterable[UnitResult]) -> None:
    result_list = tuple(results)
    ids = [result.plan_unit_id for result in result_list]
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate published results: {duplicates}")
    terminal = set(ExecutionState)
    if any(result.execution_state not in terminal for result in result_list):
        raise ValueError("every result must have a terminal execution state")
    planned_ids = {unit.plan_unit_id for unit in plan.units}
    result_ids = set(ids)
    missing = sorted(planned_ids - result_ids)
    extra = sorted(result_ids - planned_ids)
    if missing or extra:
        raise ValueError(f"plan/result ID mismatch; missing={missing}, extra={extra}")


def coverage_summary(plan: ExecutionPlan, results: Iterable[UnitResult]) -> dict[str, Any]:
    result_list = tuple(results)
    validate_terminal_results(plan, result_list)
    states = Counter(result.execution_state for result in result_list)
    applicability = Counter(result.applicability for result in result_list)
    planned_ids = {unit.plan_unit_id for unit in plan.units}
    attempted_ids = {
        result.plan_unit_id
        for result in result_list
        if result.execution_state in {ExecutionState.COMPUTED, ExecutionState.FAILED}
    }
    attempted_ids.update(
        attempt.plan_unit_id
        for attempt in plan.attempts
        if attempt.plan_unit_id in planned_ids
    )

    def sample_total(key: str) -> int | float:
        total: int | float = 0
        for result in result_list:
            value = result.coverage.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"coverage.{key} must be a non-negative number")
            total += value
        return total

    return {
        "units": {
            "planned": len(plan.units),
            "attempted": len(attempted_ids),
            "computed": states[ExecutionState.COMPUTED],
            "skipped": states[ExecutionState.SKIPPED],
            "failed": states[ExecutionState.FAILED],
            "cancelled": states[ExecutionState.CANCELLED],
        },
        "applicability": {
            "applicable": applicability[Applicability.APPLICABLE],
            "not_applicable": applicability[Applicability.NOT_APPLICABLE],
            "unknown": applicability[Applicability.UNKNOWN],
        },
        "samples": {
            "planned": sample_total("planned_samples"),
            "computed": sample_total("computed_samples"),
        },
    }
