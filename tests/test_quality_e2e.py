"""Synthetic end-to-end contract for the internal quality pipeline.

This deliberately uses in-memory/synthetic records.  It verifies the seams
between advice output, evidence projection, and append-only review events;
it does not claim real trainer parity or calibrated production thresholds.
"""
import json

from rda.quality.contracts import Applicability, Assessment, ExecutionState, UnitResult
from rda.quality.core_review import AppendOnlyReviewClient, new_review_event
from rda.quality.evidence import to_fiftyone_records
from rda.quality.report import write_quality_bundle
from rda.quality.runner import run_quality


def _unit(pid, assessment):
    return UnitResult(
        pid, Applicability.APPLICABLE, ExecutionState.COMPUTED, assessment,
        {"planned_samples": 1, "attempted_samples": 1, "computed_samples": 1,
         "sampling_complete": True}, {"value": 0.25},
        [{"locator": {"episode": pid.split(":")[0]}}],
        () if assessment is Assessment.PASS else ("THRESHOLD",),
        "speed_rule" if assessment is not Assessment.UNASSESSED else None,
        "1" if assessment is not Assessment.UNASSESSED else None,
        {"kind": "calibrated_rule", "rule_id": "speed_rule", "rule_version": "1",
         "calibration_id": "cal-1", "calibration_hash": "sha256:" + "a" * 64}
        if assessment is Assessment.PASS else ({"kind": "provisional_rule", "rule_id": "speed_rule", "rule_version": "1"} if assessment is not Assessment.UNASSESSED else None),
    )


def test_synthetic_quality_bundle_to_evidence_and_review(tmp_path):
    paths = write_quality_bundle(
        tmp_path, "synthetic-run",
        [_unit("ep1:speed", Assessment.PASS),
         _unit("ep2:speed", Assessment.REVIEW)],
        run_state="COMPLETED", metadata={"synthetic": True},
    )
    report = json.loads(paths["report"].read_text())
    records = to_fiftyone_records(paths["advice"], run_id="synthetic-run")
    assert report["decision_authority"] == "company_core"
    assert len(records) == 2
    assert all("procurement_decision" not in record.to_dict() for record in records)

    received = []
    client = AppendOnlyReviewClient(lambda event: received.append(event) or {"accepted": True})
    response = client.submit(new_review_event(
        "synthetic-run", records[1].sample_id, "reviewer-1", "ANNOTATION_ADDED",
        {"label": "inspect", "evidence_locator": records[1].evidence[0]["locator"]},
    ))
    assert response == {"accepted": True}
    assert received[0]["sample_id"] == "ep2:speed"
    assert "training_selection_decision" not in received[0]


def test_synthetic_runner_failure_closes_unit_without_complete_marker(tmp_path):
    class Request:
        output_root = tmp_path
        run_id = "failed-run"
        config = {}
        resume = False

    def execute(unit):
        if unit["plan_unit_id"] == "u2":
            raise RuntimeError("synthetic decode failure")
        return {"plan_unit_id": unit["plan_unit_id"], "execution_state": "COMPUTED"}

    summary = run_quality(Request(), plan=[{"plan_unit_id": "u1"}, {"plan_unit_id": "u2"}], execute_unit=execute)
    assert summary.failed == 1
    assert summary.run_state.value == "PARTIAL"
    assert not (tmp_path / "failed-run.complete").exists()
