from rda.quality.window_contract import TrainingWindow
from rda.quality.window_diagnostics import compute_window_diagnostics

def test_diagnostics_use_checked_denominators_and_unknown_when_unchecked():
    ws = [TrainingWindow(i, 1, (i,), (i,), (False,), (0.0,), 0.01) for i in range(2)]
    d = compute_window_diagnostics(ws, {0:{"activity_checked":True,"active":True,"risk_checked":True,"risk_detected":False}})
    assert d.structurally_available_windows == 2
    assert d.active_window_ratio == 1.0
    assert d.no_detected_risk_window_ratio == 1.0
    assert d.risk_check_unchecked_windows == 1
