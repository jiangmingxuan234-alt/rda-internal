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
]


def __getattr__(name):
    # Lazy imports keep legacy ``rda.metrics`` import order cycle-free.
    if name in {"RuleContext", "evaluate_measurement"}:
        from rda.quality.rules import RuleContext, evaluate_measurement
        return {"RuleContext": RuleContext, "evaluate_measurement": evaluate_measurement}[name]
    if name in {"ScoredMeasurement", "score_measurements"}:
        from rda.quality.scoring import ScoredMeasurement, score_measurements
        return {"ScoredMeasurement": ScoredMeasurement, "score_measurements": score_measurements}[name]
    raise AttributeError(name)
