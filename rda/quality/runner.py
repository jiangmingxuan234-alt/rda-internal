"""Bounded, resumable quality-mode execution."""
from dataclasses import dataclass
from pathlib import Path
import json
from .checkpoint import CheckpointStore
from .resources import ResourceBudget, BudgetGuard, BudgetExceeded
from .contracts import QualityRunState

@dataclass(frozen=True)
class QualityRunSummary:
    run_id: str; run_state: QualityRunState; planned: int; completed: int; skipped: int; failed: int; output_root: Path; reason_codes: tuple[str,...]=()
    def to_dict(self): return {'run_id':self.run_id,'run_state':self.run_state.value,'planned':self.planned,'completed':self.completed,'skipped':self.skipped,'failed':self.failed,'reason_codes':list(self.reason_codes)}

def run_quality(request, *, plan=None, execute_unit=None, budget=None):
    budget = budget or ResourceBudget(); guard=BudgetGuard(budget)
    out=Path(request.output_root); staging=out/(request.run_id+'.staging'); staging.mkdir(parents=True,exist_ok=True)
    store=CheckpointStore(staging, request.run_id); cached=store.load(request.run_id)
    units=list(plan or request.config.get('execution_plan', [])); results=[]; reasons=[]; failed=skipped=0
    for unit in units:
        pid=unit.get('plan_unit_id') if isinstance(unit,dict) else getattr(unit,'plan_unit_id')
        if request.resume and pid in cached: results.append(cached[pid]); continue
        try:
            guard.check(); result=execute_unit(unit) if execute_unit else (unit if isinstance(unit,dict) else unit.to_dict())
            store.save_unit(result); results.append(result)
        except BudgetExceeded as exc:
            reasons.append(exc.reason); skipped += 1; break
        except Exception as exc:
            failed += 1; reasons.append('UNIT_FAILED'); row={'plan_unit_id':pid,'execution_state':'FAILED','reason_codes':['UNIT_FAILED']}; store.save_unit(row); results.append(row)
    if skipped or failed: state=QualityRunState.PARTIAL
    else: state=QualityRunState.COMPLETED
    store.mark_stage('publish', run_state=state.value, planned=len(units), completed=len(results))
    marker=out/(request.run_id+'.complete')
    if state is QualityRunState.COMPLETED:
        marker.write_text('complete\n')
    return QualityRunSummary(request.run_id,state,len(units),len(results)-skipped,skipped,failed,out,tuple(reasons))
