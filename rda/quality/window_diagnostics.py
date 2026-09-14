"""Diagnostics over explicitly checked training windows."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from rda.quality.window_contract import TrainingWindow


@dataclass(frozen=True)
class WindowDiagnostics:
    structurally_available_windows: int
    active_window_ratio: float | None
    no_detected_risk_window_ratio: float | None
    activity_checked_windows: int
    risk_checked_windows: int
    risk_check_unchecked_windows: int
    alignment: str = "UNASSESSED"


def compute_window_diagnostics(windows: Iterable[TrainingWindow], findings: Mapping[int, Mapping[str, Any]] | None = None) -> WindowDiagnostics:
    ws = tuple(windows)
    findings = findings or {}
    available = len(ws)
    activity = [findings[w.index] for w in ws if w.index in findings and findings[w.index].get("activity_checked") is True]
    active = sum(1 for f in activity if f.get("active") is True)
    risk = [findings[w.index] for w in ws if w.index in findings and findings[w.index].get("risk_checked") is True]
    clean = sum(1 for f in risk if f.get("risk_detected") is False)
    return WindowDiagnostics(available, active / len(activity) if activity else None,
                             clean / len(risk) if risk else None, len(activity), len(risk), available - len(risk))
