import pytest
from rda.quality.resources import ResourceBudget, BudgetGuard, BudgetExceeded
from rda.quality.runner import run_quality
from rda.quality.contracts import QualityRequest, QualityRunState

def test_evidence_budget():
    g=BudgetGuard(ResourceBudget(max_evidence=1)); g.add_evidence()
    with pytest.raises(BudgetExceeded): g.add_evidence()

def test_budget_stops_without_complete_marker(tmp_path):
    req=QualityRequest(tmp_path,tmp_path/'m',{'execution_plan':[{'plan_unit_id':'a'},{'plan_unit_id':'b'}]},tmp_path/'o','x')
    s=run_quality(req,budget=ResourceBudget(max_runtime_seconds=0))
    assert s.run_state is QualityRunState.PARTIAL
    assert not (tmp_path/'o'/'x.complete').exists()
