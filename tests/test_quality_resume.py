from rda.quality.runner import run_quality
from rda.quality.contracts import QualityRequest

def test_resume_reuses_checkpoint(tmp_path):
    calls=[]
    req=QualityRequest(tmp_path,tmp_path/'m',{'execution_plan':[{'plan_unit_id':'u1'}]},tmp_path/'o','r')
    run_quality(req, execute_unit=lambda u: calls.append(1) or u)
    run_quality(QualityRequest(tmp_path,tmp_path/'m',req.config,tmp_path/'o','r',resume=True), execute_unit=lambda u: calls.append(2) or u)
    assert calls == [1]
