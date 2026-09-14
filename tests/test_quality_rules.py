from rda.quality.rules import evaluate_measurement
from rda.quality.contracts import *

def rec(values, coverage=None):
    return MeasurementRecord("u", "m", "v1", "sha256:"+"a"*64, Applicability.APPLICABLE, coverage or {"planned_samples":1,"attempted_samples":1,"computed_samples":1}, values, ())

def test_config_version_adapter_and_missing_rule():
    assert evaluate_measurement(rec({"value": 1}), None).assessment is Assessment.UNASSESSED
    r=evaluate_measurement(rec({"value": 2}), {"name":"r","version":"1","thresholds":{"value":1},"kind":"calibrated","calibration_id":"c","calibration_hash":"sha256:"+"b"*64})
    assert r.rule_version == "1"
