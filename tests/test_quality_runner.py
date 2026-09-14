from pathlib import Path
from rda.quality.runner import run_quality
from rda.quality.contracts import QualityRequest, QualityRunState

def test_runner_publishes_complete_marker(tmp_path):
    req=QualityRequest(tmp_path, tmp_path/'manifest.json', {'execution_plan':[{'plan_unit_id':'u1'}]}, tmp_path/'out','r1')
    s=run_quality(req)
    assert s.run_state is QualityRunState.COMPLETED
    assert (tmp_path/'out'/'r1.complete').exists()
