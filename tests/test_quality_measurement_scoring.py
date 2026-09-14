import pytest
from rda.quality.scoring import score_measurements
from rda.calibration.reference import QualityReference, MetricStats
from rda.quality.contracts import *

def test_degenerate_mad_and_strict_reference():
    rec=MeasurementRecord("u","m","v","sha256:"+"a"*64,Applicability.APPLICABLE,{"planned_samples":1,"attempted_samples":1,"computed_samples":1},{"value":2},())
    ref=QualityReference("c","sha256:"+"b"*64,"r","sha256:"+"c"*64,"v",{"dimension":"x"},3,{"robot":"r"},{"m":MetricStats(1,0,1,0,2,2)})
    out=score_measurements((rec,),ref,{"u":{"robot":"r"}})
    assert "REFERENCE_DEGENERATE" in out[0].reason_codes and out[0].score is None
    with pytest.raises(TypeError): score_measurements((rec,), {"metrics":{}}, {})

def test_reference_profile_hash_is_strict_and_mappings_frozen():
    with pytest.raises(ValueError):
        QualityReference("c", "sha256:"+"b"*64, "r", "bad", "v", {"d":"x"}, 2, {}, {"m":MetricStats(1,1,0,0,2,2)})
    ref = QualityReference("c", "sha256:"+"b"*64, "r", "sha256:"+"c"*64, "v", {"d":"x"}, 2, {}, {"m":MetricStats(1,1,0,0,2,2)})
    with pytest.raises(TypeError): ref.dimensions["x"] = 1
