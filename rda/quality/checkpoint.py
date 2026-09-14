"""Durable checkpoint store for resumable quality runs."""
from pathlib import Path
import json, hashlib

class CheckpointStore:
    def __init__(self, root: Path, run_key: str):
        self.root=Path(root); self.run_key=run_key; self.root.mkdir(parents=True,exist_ok=True)
        self.units_path=self.root/'unit_results.jsonl'; self.state_path=self.root/'run_state.json'
    def _key(self, value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def load(self, run_key=None):
        if run_key is not None and run_key != self.run_key: return {}
        out={}
        if self.units_path.exists():
            for line in self.units_path.read_text().splitlines():
                try:
                    row=json.loads(line); out[row['plan_unit_id']]=row
                except Exception: continue
        return out
    def save_unit(self, unit_result):
        row = unit_result.to_dict() if hasattr(unit_result,'to_dict') else dict(unit_result)
        with self.units_path.open('a',encoding='utf-8') as f: f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
    def mark_stage(self, stage, **extra):
        payload={'run_key':self.run_key,'stage':stage,**extra}
        tmp=self.state_path.with_suffix('.tmp'); tmp.write_text(json.dumps(payload,sort_keys=True)); tmp.replace(self.state_path)
    def state(self):
        return json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
