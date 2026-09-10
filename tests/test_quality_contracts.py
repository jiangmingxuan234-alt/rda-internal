from __future__ import annotations

import json
from pathlib import Path

import pytest

from rda.quality.contracts import (
    Applicability,
    Assessment,
    ExecutionState,
    QualityRequest,
    QualityRunState,
    UnitResult,
)


def test_four_state_layers_reject_unknown_strings():
    assert [state.value for state in Applicability] == [
        "APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"
    ]
    assert [state.value for state in ExecutionState] == [
        "COMPUTED", "SKIPPED", "FAILED", "CANCELLED"
    ]
    assert [state.value for state in Assessment] == [
        "UNASSESSED", "PASS", "REVIEW", "EXCLUDE_CANDIDATE"
    ]
    assert [state.value for state in QualityRunState] == [
        "COMPLETED", "PARTIAL", "BLOCKED", "ERROR", "INTERRUPTED"
    ]

    with pytest.raises(ValueError):
        Assessment("EXCLUDE")


def test_exclude_candidate_remains_quality_advice():
    result = UnitResult(
        plan_unit_id="unit-1",
        applicability=Applicability.APPLICABLE,
        execution_state=ExecutionState.COMPUTED,
        assessment=Assessment.EXCLUDE_CANDIDATE,
        coverage={
            "planned_samples": 10,
            "attempted_samples": 10,
            "computed_samples": 10,
            "sampling_complete": True,
        },
        measurement={"blur": 0.9},
        evidence=({"frame_range": [0, 10]},),
        reason_codes=("CALIBRATED_RULE_MATCH",),
        rule_id="blur-upper-bound",
        rule_version="blur-rule-v1",
        rule_source={
            "kind": "calibrated_rule",
            "rule_id": "blur-upper-bound",
            "rule_version": "blur-rule-v1",
            "calibration_id": "gold-v1",
            "calibration_hash": "sha256:" + "a" * 64,
        },
    )

    assert result.assessment.value == "EXCLUDE_CANDIDATE"
    assert "EXCLUDE" not in result.to_dict().values()


def test_unit_result_requires_plan_unit_id():
    with pytest.raises(ValueError, match="plan_unit_id"):
        UnitResult(
            plan_unit_id="",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.UNASSESSED,
            coverage={
                "planned_samples": 1,
                "attempted_samples": 1,
                "computed_samples": 1,
                "sampling_complete": True,
            },
            measurement={"value": 1},
            evidence=(),
            reason_codes=(),
        )


def test_computed_measurement_without_rule_is_unassessed():
    result = UnitResult(
        plan_unit_id="unit-1",
        applicability=Applicability.APPLICABLE,
        execution_state=ExecutionState.COMPUTED,
        assessment=Assessment.UNASSESSED,
        coverage={"planned_samples": 1, "computed_samples": 1},
        measurement={"value": 1.25},
        evidence=(),
        reason_codes=("RULE_NOT_CONFIGURED",),
    )
    assert result.measurement["value"] == 1.25

    with pytest.raises(ValueError, match="rule_version"):
        UnitResult(
            plan_unit_id="unit-2",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.PASS,
            coverage={
                "planned_samples": 1,
                "attempted_samples": 1,
                "computed_samples": 1,
                "sampling_complete": True,
            },
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=(),
        )


def test_assessment_requires_rule_id_as_well_as_version():
    with pytest.raises(ValueError, match="rule_id"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.REVIEW,
            coverage={"planned_samples": 1, "computed_samples": 1},
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("RULE_MATCH",),
            rule_version="1",
        )


def test_exclude_candidate_requires_calibrated_rule_source():
    with pytest.raises(ValueError, match="calibrated rule_source"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.EXCLUDE_CANDIDATE,
            coverage={
                "planned_samples": 1,
                "attempted_samples": 1,
                "computed_samples": 1,
                "sampling_complete": True,
            },
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("RULE_MATCH",),
            rule_id="rule-1",
            rule_version="1",
            rule_source={"kind": "provisional"},
        )


@pytest.mark.parametrize("assessment", [Assessment.PASS, Assessment.EXCLUDE_CANDIDATE])
def test_calibrated_assessment_requires_explicit_complete_coverage(assessment):
    with pytest.raises(ValueError, match="coverage"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=assessment,
            coverage={},
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("CALIBRATED_RULE_MATCH",),
            rule_id="rule-1",
            rule_version="1",
            rule_source={
                "kind": "calibrated_rule",
                "rule_id": "rule-1",
                "rule_version": "1",
                "calibration_id": "cal-1",
                "calibration_hash": "sha256:" + "b" * 64,
            },
        )


def test_calibration_provenance_is_tied_to_rule_identity_and_content_hash():
    source = {
        "kind": "calibrated_rule",
        "rule_id": "different-rule",
        "rule_version": "1",
        "calibration_id": "cal-1",
        "calibration_hash": "sha256:" + "b" * 64,
    }
    with pytest.raises(ValueError, match="rule_id"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.EXCLUDE_CANDIDATE,
            coverage={
                "planned_samples": 1,
                "attempted_samples": 1,
                "computed_samples": 1,
                "sampling_complete": True,
            },
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("CALIBRATED_RULE_MATCH",),
            rule_id="rule-1",
            rule_version="1",
            rule_source=source,
        )

    source["rule_id"] = "rule-1"
    source["calibration_hash"] = "not-a-content-hash"
    with pytest.raises(ValueError, match="calibration_hash"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.EXCLUDE_CANDIDATE,
            coverage={
                "planned_samples": 1,
                "attempted_samples": 1,
                "computed_samples": 1,
                "sampling_complete": True,
            },
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("CALIBRATED_RULE_MATCH",),
            rule_id="rule-1",
            rule_version="1",
            rule_source=source,
        )


def test_assessed_result_rule_identity_must_be_nonempty_strings():
    with pytest.raises(ValueError, match="rule_id"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.REVIEW,
            coverage={"planned_samples": 1, "computed_samples": 1},
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("RULE_MATCH",),
            rule_id=7,
            rule_version="1",
        )


def test_partial_coverage_cannot_pass():
    with pytest.raises(ValueError, match="partial coverage"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.PASS,
            coverage={
                "planned_samples": 10,
                "attempted_samples": 10,
                "computed_samples": 9,
                "sampling_complete": False,
            },
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("RULE_NO_MATCH",),
            rule_id="rule-1",
            rule_version="1",
        )


def test_pass_requires_calibrated_rule_source():
    with pytest.raises(ValueError, match="calibrated rule_source"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.PASS,
            coverage={
                "planned_samples": 10,
                "attempted_samples": 10,
                "computed_samples": 10,
                "sampling_complete": True,
            },
            measurement={"value": 1.25},
            evidence=(),
            reason_codes=("CALIBRATED_RULE_NO_MATCH",),
            rule_id="rule-1",
            rule_version="1",
        )

    result = UnitResult(
        plan_unit_id="unit-1",
        applicability=Applicability.APPLICABLE,
        execution_state=ExecutionState.COMPUTED,
        assessment=Assessment.PASS,
        coverage={
            "planned_samples": 10,
            "attempted_samples": 10,
            "computed_samples": 10,
            "sampling_complete": True,
        },
        measurement={"value": 1.25},
        evidence=(),
        reason_codes=("CALIBRATED_RULE_NO_MATCH",),
        rule_id="rule-1",
        rule_version="1",
        rule_source={
            "kind": "calibrated_rule",
            "rule_id": "rule-1",
            "rule_version": "1",
            "calibration_id": "gold-v1",
            "calibration_hash": "sha256:" + "a" * 64,
        },
    )
    assert result.assessment is Assessment.PASS


def test_noncomputed_result_cannot_publish_measurement_and_needs_reason():
    with pytest.raises(ValueError, match="measurement"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.UNKNOWN,
            execution_state=ExecutionState.SKIPPED,
            assessment=Assessment.UNASSESSED,
            coverage={"planned_samples": 1, "computed_samples": 0},
            measurement={"invented": 0},
            evidence=(),
            reason_codes=("ROBOT_PROFILE_MISSING",),
        )

    with pytest.raises(ValueError, match="reason_codes"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.UNKNOWN,
            execution_state=ExecutionState.SKIPPED,
            assessment=Assessment.UNASSESSED,
            coverage={"planned_samples": 1, "computed_samples": 0},
            measurement={},
            evidence=(),
            reason_codes=(),
        )


def test_unknown_applicability_requires_reason_even_when_raw_measurement_computed():
    with pytest.raises(ValueError, match="reason_codes"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.UNKNOWN,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.UNASSESSED,
            coverage={"planned_samples": 1, "computed_samples": 1},
            measurement={"raw_value": 2.0},
            evidence=(),
            reason_codes=(),
        )

    result = UnitResult(
        plan_unit_id="unit-1",
        applicability=Applicability.UNKNOWN,
        execution_state=ExecutionState.COMPUTED,
        assessment=Assessment.UNASSESSED,
        coverage={"planned_samples": 1, "computed_samples": 1},
        measurement={"raw_value": 2.0},
        evidence=(),
        reason_codes=("ROBOT_PROFILE_MISSING",),
    )
    assert result.measurement["raw_value"] == 2


def test_not_applicable_result_cannot_publish_measurement():
    with pytest.raises(ValueError, match="NOT_APPLICABLE"):
        UnitResult(
            plan_unit_id="unit-1",
            applicability=Applicability.NOT_APPLICABLE,
            execution_state=ExecutionState.COMPUTED,
            assessment=Assessment.UNASSESSED,
            coverage={"planned_samples": 1, "computed_samples": 1},
            measurement={"invented": 0},
            evidence=(),
            reason_codes=("MODALITY_NOT_PRESENT",),
        )


def test_contracts_are_deeply_immutable_and_json_safe(tmp_path: Path):
    request = QualityRequest(
        dataset_root=tmp_path / "dataset",
        input_manifest=tmp_path / "manifest.json",
        config={"contract_version": 1, "quality": {"metrics": []}},
        output_root=tmp_path / "out",
        run_id="run-1",
    )
    with pytest.raises(TypeError):
        request.config["quality"]["metrics"] += ("idle_ratio",)

    encoded = json.dumps(request.to_dict(), ensure_ascii=False, sort_keys=True)
    assert "manifest.json" in encoded
