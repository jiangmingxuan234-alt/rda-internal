import json
from pathlib import Path

from rda.quality.contracts import Applicability, Assessment, ExecutionState, UnitResult
from rda.quality.report import build_quality_report, write_quality_bundle


def _result(pid, assessment=Assessment.UNASSESSED):
    return UnitResult(pid, Applicability.APPLICABLE, ExecutionState.COMPUTED,
                      assessment, {"planned_samples": 1, "attempted_samples": 1,
                                   "computed_samples": 1, "sampling_complete": True},
                      {"value": 0.2}, [{"locator": {"episode": 1}}],
                      () if assessment is not Assessment.UNASSESSED else ("RULE_NOT_CONFIGURED",),
                      "r" if assessment is not Assessment.UNASSESSED else None,
                      "1" if assessment is not Assessment.UNASSESSED else None,
                      {"kind": "calibrated_rule", "rule_id": "r", "rule_version": "1",
                       "calibration_id": "c", "calibration_hash": "sha256:" + "a" * 64}
                      if assessment is not Assessment.UNASSESSED else None)


def test_report_is_advice_and_separates_assessments():
    report = build_quality_report([_result("u1", Assessment.PASS), _result("u2", Assessment.EXCLUDE_CANDIDATE)])
    assert report["schema_version"] == 1
    assert report["summary"]["pass"] == 1
    assert report["summary"]["exclude_candidate"] == 1
    assert "training_selection_manifest" not in report


def test_bundle_writes_jsonl_and_checksums_without_training_manifest(tmp_path: Path):
    paths = write_quality_bundle(tmp_path, "run1", [_result("u1")], run_state="COMPLETED")
    assert paths["advice"].name == "quality_advice.jsonl"
    row = json.loads(paths["advice"].read_text().strip())
    assert row["plan_unit_id"] == "u1"
    assert (tmp_path / "run1" / "report.json").exists()
    assert (tmp_path / "run1" / "checksums.json").exists()
    assert not (tmp_path / "run1" / "training_selection_manifest.jsonl").exists()
