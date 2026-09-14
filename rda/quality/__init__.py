"""Public contracts for RDA's versioned quality mode."""
from rda.quality.config import QualityConfig, canonical_json, config_hash
from rda.quality.contracts import (
    Applicability,
    Assessment,
    ExecutionState,
    MeasurementRecord,
    QualityRequest,
    QualityRunState,
    UnitResult,
)
from rda.quality.execution_plan import (
    AttemptRecord,
    ExecutionPlan,
    PlanUnit,
    build_plan,
    coverage_summary,
    validate_terminal_results,
)
from rda.quality.window_contract import TrainingWindow, WindowParityReport, compare_window_indices, load_training_windows
from rda.quality.window_diagnostics import WindowDiagnostics, compute_window_diagnostics
from rda.quality.evidence import EvidenceRecord, load_quality_advice, to_fiftyone_records
from rda.quality.core_review import AppendOnlyReviewClient, ReviewEvent, new_review_event

__all__ = [
    "Applicability",
    "Assessment",
    "AttemptRecord",
    "ExecutionPlan",
    "ExecutionState",
    "MeasurementRecord",
    "PlanUnit",
    "QualityConfig",
    "QualityRequest",
    "QualityRunState",
    "UnitResult",
    "RuleContext",
    "evaluate_measurement",
    "ScoredMeasurement",
    "score_measurements",
    "build_plan",
    "canonical_json",
    "config_hash",
    "coverage_summary",
    "validate_terminal_results",
    "TrainingWindow",
    "WindowParityReport",
    "WindowDiagnostics",
    "compare_window_indices",
    "load_training_windows",
    "compute_window_diagnostics",
    "EvidenceRecord",
    "load_quality_advice",
    "to_fiftyone_records",
    "AppendOnlyReviewClient",
    "ReviewEvent",
    "new_review_event",
    "GroupSummary",
    "summarize",
    "merge_summaries",
    "map_task",
    "GridConfig",
    "fixed_grid_coverage",
]


def __getattr__(name):
    # Lazy imports keep legacy ``rda.metrics`` import order cycle-free.
    if name in {"RuleContext", "evaluate_measurement"}:
        from rda.quality.rules import RuleContext, evaluate_measurement
        return {"RuleContext": RuleContext, "evaluate_measurement": evaluate_measurement}[name]
    if name in {"ScoredMeasurement", "score_measurements"}:
        from rda.quality.scoring import ScoredMeasurement, score_measurements
        return {"ScoredMeasurement": ScoredMeasurement, "score_measurements": score_measurements}[name]
    if name in {"GroupSummary", "summarize", "merge_summaries", "map_task"}:
        from rda.quality.distribution import GroupSummary, summarize, merge_summaries, map_task
        return locals()[name]
    if name in {"GridConfig", "fixed_grid_coverage"}:
        from rda.quality.coverage import GridConfig, fixed_grid_coverage
        return {"GridConfig": GridConfig, "fixed_grid_coverage": fixed_grid_coverage}[name]
    raise AttributeError(name)
