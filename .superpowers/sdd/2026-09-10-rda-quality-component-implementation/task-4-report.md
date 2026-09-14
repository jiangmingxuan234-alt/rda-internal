# Task 4 report: measurement-local rules and quality scoring

Implemented strict metric-local rule evaluation and a quality-only scorer.
`evaluate_measurement` consumes a completed `MeasurementRecord`; absent rules
produce `COMPUTED/UNASSESSED`, provisional rules produce explicit `REVIEW`,
and calibrated outcomes require rule version, calibration identity and
complete positive coverage. Applicability, missing values, incomplete samples,
scope mismatches and invalid provenance remain unassessed.

`score_measurements` consumes only current records and a strict
`QualityReference`; it never constructs legacy metrics or reads `EpisodeData`.
Missing groups, insufficient samples and zero/near-zero MAD and IQR return
explicit reason codes. Legacy `ReferenceProfile` and `BehavioralScorer` APIs
remain unchanged; the new wrapper is quality-only.

TDD/result:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_contracts.py -q
16 passed in 0.07s
```

