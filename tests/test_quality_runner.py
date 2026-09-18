from pathlib import Path
import json

from rda.quality.runner import _publish_execution_artifacts, run_quality
from rda.quality.contracts import QualityRequest, QualityRunState

def test_runner_publishes_complete_marker(tmp_path):
    req=QualityRequest(tmp_path, tmp_path/'manifest.json', {'execution_plan':[{'plan_unit_id':'u1'}]}, tmp_path/'out','r1')
    s=run_quality(req)
    assert s.run_state is QualityRunState.COMPLETED
    assert (tmp_path/'out'/'r1.complete').exists()


def test_final_bundle_contains_plan_and_terminal_results(tmp_path):
    staging = tmp_path / "run.staging"
    final = tmp_path / "run"
    staging.mkdir()
    final.mkdir()
    (staging / "execution_plan.json").write_text('{"units": []}\n', encoding="utf-8")
    (staging / "unit_results.jsonl").write_text('{"plan_unit_id":"u1"}\n', encoding="utf-8")
    (final / "checksums.json").write_text('{}\n', encoding="utf-8")

    _publish_execution_artifacts(staging, final)

    assert (final / "execution_plan.json").read_text() == '{"units": []}\n'
    assert (final / "unit_results.jsonl").read_text() == '{"plan_unit_id":"u1"}\n'
    checksums = json.loads((final / "checksums.json").read_text())
    assert set(checksums) == {"execution_plan.json", "unit_results.jsonl"}
    assert all(value.startswith("sha256:") for value in checksums.values())
