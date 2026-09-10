from __future__ import annotations

import pytest

from rda.quality.contracts import Applicability, Assessment, ExecutionState, UnitResult
from rda.quality.execution_plan import (
    AttemptRecord,
    ExecutionPlan,
    PlanUnit,
    build_plan,
    coverage_summary,
    validate_terminal_results,
)


def _unit(group="camera.front"):
    return {
        "episode_id": "episode-7",
        "metric": "visual_quality",
        "camera_or_dimension_group": group,
        "input_references": {"media": "videos/front.mp4"},
        "requested_config_hash": "sha256:" + "a" * 64,
        "effective_config_hash": "sha256:" + "b" * 64,
        "sampling_range": {"start": 0, "end": 10},
        "resource_estimate": {"frames": 10},
    }


def _result(plan_unit_id, state=ExecutionState.COMPUTED):
    return UnitResult(
        plan_unit_id=plan_unit_id,
        applicability=Applicability.APPLICABLE,
        execution_state=state,
        assessment=Assessment.UNASSESSED,
        coverage={"planned_samples": 10, "computed_samples": 10 if state is ExecutionState.COMPUTED else 0},
        measurement={"blur": 1.0} if state is ExecutionState.COMPUTED else {},
        evidence=(),
        reason_codes=("RULE_NOT_CONFIGURED",) if state is ExecutionState.COMPUTED else ("DEPENDENCY_MISSING",),
    )


def test_same_plan_input_generates_same_id():
    assert build_plan([_unit()]).units[0].plan_unit_id == build_plan([_unit()]).units[0].plan_unit_id


def test_direct_plan_unit_rejects_noncanonical_id():
    with pytest.raises(ValueError, match="canonical"):
        PlanUnit(plan_unit_id="arbitrary", **_unit())


def test_direct_execution_plan_freezes_constructor_lists():
    canonical_unit = build_plan([_unit()]).units[0]
    units = [canonical_unit]
    attempts = [AttemptRecord(canonical_unit.plan_unit_id, 1, "COMPUTED")]
    plan = ExecutionPlan(units=units, attempts=attempts)
    units.clear()
    attempts.clear()
    assert plan.units == (canonical_unit,)
    assert len(plan.attempts) == 1


def test_direct_execution_plan_rejects_duplicate_units_and_unknown_attempt_units():
    unit = build_plan([_unit()]).units[0]
    with pytest.raises(ValueError, match="duplicate"):
        ExecutionPlan(units=[unit, unit])
    with pytest.raises(ValueError, match="unknown plan_unit_id"):
        ExecutionPlan(
            units=[unit],
            attempts=[AttemptRecord("quality-unit:" + "f" * 64, 1, "FAILED")],
        )


def test_plan_unit_requires_content_hash_config_identities():
    spec = _unit()
    spec["requested_config_hash"] = "requested-abc"
    with pytest.raises(ValueError, match="requested_config_hash"):
        build_plan([spec])


def test_camera_or_dimension_group_participates_in_id():
    front = build_plan([_unit("camera.front")]).units[0].plan_unit_id
    wrist = build_plan([_unit("camera.wrist")]).units[0].plan_unit_id
    assert front != wrist


def test_plan_and_results_must_have_identical_id_sets():
    plan = build_plan([_unit()])
    with pytest.raises(ValueError, match="missing"):
        validate_terminal_results(plan, [])
    with pytest.raises(ValueError, match="extra"):
        validate_terminal_results(plan, [_result(plan.units[0].plan_unit_id), _result("extra")])


def test_duplicate_published_results_are_rejected():
    plan = build_plan([_unit()])
    result = _result(plan.units[0].plan_unit_id)
    with pytest.raises(ValueError, match="duplicate"):
        validate_terminal_results(plan, [result, result])


def test_missing_terminal_state_is_rejected():
    plan = build_plan([_unit()])
    result = _result(plan.units[0].plan_unit_id)
    object.__setattr__(result, "execution_state", None)
    with pytest.raises(ValueError, match="terminal"):
        validate_terminal_results(plan, [result])


def test_attempts_do_not_duplicate_published_unit_results():
    initial_plan = build_plan([_unit()])
    unit_id = initial_plan.units[0].plan_unit_id
    plan = build_plan([_unit()], attempts=(
        AttemptRecord(plan_unit_id=unit_id, attempt=1, state="FAILED", reason_codes=("TRANSIENT",)),
        AttemptRecord(plan_unit_id=unit_id, attempt=2, state="COMPUTED"),
    ))
    result = _result(plan.units[0].plan_unit_id)
    validate_terminal_results(plan, [result])
    assert len(plan.attempts) == 2


def test_coverage_summary_keeps_plan_and_sample_coverage_separate():
    plan = build_plan([_unit(), {**_unit("camera.wrist"), "resource_estimate": {"frames": 20}}])
    results = [
        _result(plan.units[0].plan_unit_id),
        _result(plan.units[1].plan_unit_id, ExecutionState.SKIPPED),
    ]
    summary = coverage_summary(plan, results)
    assert summary["units"] == {
        "planned": 2, "attempted": 1, "computed": 1, "skipped": 1, "failed": 0, "cancelled": 0
    }
    assert summary["samples"] == {"planned": 20, "computed": 10}
