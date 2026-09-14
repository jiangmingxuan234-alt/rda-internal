"""Resource limits for quality execution."""
from dataclasses import dataclass
import time
import resource

@dataclass(frozen=True)
class ResourceBudget:
    max_workers: int = 1
    max_rss_bytes: int | None = None
    max_cache_bytes: int | None = None
    max_decode_workers: int = 1
    max_runtime_seconds: float | None = None
    max_output_bytes: int | None = None
    max_evidence: int | None = None

    def __post_init__(self):
        for name in ("max_workers", "max_decode_workers"):
            if getattr(self, name) < 1: raise ValueError(f"{name} must be >= 1")
        for name in ("max_rss_bytes", "max_cache_bytes", "max_runtime_seconds", "max_output_bytes", "max_evidence"):
            value=getattr(self,name)
            if value is not None and value < 0: raise ValueError(f"{name} must be non-negative")

class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str): self.reason = reason; super().__init__(reason)

class BudgetGuard:
    def __init__(self, budget: ResourceBudget): self.budget=budget; self.started=time.monotonic(); self.evidence=0; self.output=0
    def check(self):
        if self.budget.max_runtime_seconds is not None and time.monotonic()-self.started > self.budget.max_runtime_seconds: raise BudgetExceeded("RUNTIME_BUDGET_EXCEEDED")
        if self.budget.max_rss_bytes is not None:
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1024 if __import__('sys').platform != 'darwin' else 1)
            if rss > self.budget.max_rss_bytes: raise BudgetExceeded("RSS_BUDGET_EXCEEDED")
    def check_cache(self, cache_bytes):
        if self.budget.max_cache_bytes is not None and cache_bytes > self.budget.max_cache_bytes: raise BudgetExceeded("CACHE_BUDGET_EXCEEDED")
    def add_evidence(self,n=1):
        self.evidence += n
        if self.budget.max_evidence is not None and self.evidence > self.budget.max_evidence: raise BudgetExceeded("EVIDENCE_BUDGET_EXCEEDED")
    def add_output(self,n):
        self.output += n
        if self.budget.max_output_bytes is not None and self.output > self.budget.max_output_bytes: raise BudgetExceeded("OUTPUT_BUDGET_EXCEEDED")
