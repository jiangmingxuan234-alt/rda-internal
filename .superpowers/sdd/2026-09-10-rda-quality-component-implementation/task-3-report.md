# Task 3 report: versioned quality measurements

## Implemented

- Added immutable `MeasurementRecord`, with algorithm/version/config identity,
  applicability, coverage, values and evidence but no verdict or score.
- Added pure shared numerical features: explicit selected action/state sources,
  raw dimension observations, semantic separation for action representations,
  wrapped periodic differences with declared periods, discrete transitions,
  valid-time state derivatives, and explicit MAD-degenerate evidence.
- Added bounded visual feature facts with actual PTS interval rejection,
  planned/attempted/computed coverage, preprocessing identity and observed
  low-change spans. Low change is evidence only; it does not claim camera
  failure or continuous-frame coverage.
- Added explicit `measure_unit` dispatch. Delegated Robovet and deferred
  provider metrics produce structured `UNKNOWN`/`UNASSESSED` facts and never
  instantiate legacy metric classes.
- Replaced legacy `ALL_METRICS` discovery with a quality-local registry; added
  finite positive periodic periods and optional content-addressed source
  binding (`profile_revision`, `profile_content_hash`, `mapping_version`,
  `mapping_hash`) to effective configuration provenance.

## TDD evidence

RED, before feature module:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_measurements.py tests/test_quality_visual_measurements.py -q
2 collection errors: ModuleNotFoundError: No module named 'rda.quality.features'
```

RED, before measurement unit module:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_measurements.py -q
1 collection error: ModuleNotFoundError: No module named 'rda.quality.measurements'
```

RED, before source-binding config support:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_config.py::test_source_binding_is_content_addressed_and_changes_effective_hash -q
1 failed: unknown field at robot: source_binding
```

GREEN focused:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_measurements.py tests/test_quality_visual_measurements.py tests/test_quality_config.py -q
32 passed in 0.08s
```

Final suite:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest -q
237 passed, 6 skipped in 0.70s
```

`git diff --check` produced no output and `py_compile` completed for all added
quality modules.

## Files changed

- `rda/quality/contracts.py`, `rda/quality/config.py`, `rda/quality/__init__.py`
- `rda/quality/features.py`, `rda/quality/measurements.py`
- `tests/test_quality_measurements.py`, `tests/test_quality_visual_measurements.py`, `tests/test_quality_config.py`
- `docs/quality-semantic-profile-schema-v1.md`

## Self-review

The code does not call legacy verdict/scoring classes or duplicate Robovet
integrity verdicts. No visual result implies unobserved frame coverage. Missing
bindings retain raw facts and leave semantic claims unknown. Task 5 trainer
window generation remains outside this implementation.

## Review correction

Before commit, controller review identified scaffold shortcuts. They were
removed: unbound configuration no longer selects an arbitrary action/state
array; it publishes all raw named sources only. Physical semantics require an
explicit source binding (including synthetic fixtures). Group units resolve by
the configured index mapping. Visual preprocessing now applies the declared
ROI, blur uses a discrete Laplacian, and freeze spans use consecutive pixel
difference. `measure_unit` returns UNKNOWN with zero computed coverage for
missing or malformed sources.

Corrected focused and full verification:

```text
32 passed in 0.08s
237 passed, 6 skipped in 0.69s
```

## Fix round 1 integration

The original eleven review findings are addressed by the follow-up commits:
registered metric dispatch uses selected metric parameters and produces
delegated/deferred UNKNOWN facts; visual units consume bounded Task 2 decoded
frames with terminal errors, actual PTS coverage, applied ROI, interior
Laplacian, exposure/clipping, pixel-change and PTS/time span evidence;
semantic features require independently supplied producer profile facts and
source-specific canonical mappings; numeric facts publish finite/missing
counts, timestamp intervals/duration, runs, wrapped derivatives, acceleration
locations and structured UNKNOWN coverage for invalid sources/timestamps.
Missing-profile input retains raw named per-dimension facts. Metric outputs are
scoped to their selected group and measurement type.

Focused integration verification:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_measurements.py tests/test_quality_motion_semantics.py tests/test_quality_visual_measurements.py tests/test_quality_config.py tests/test_quality_semantic_binding.py -q
72 passed in 0.12s
```

Final full-suite verification after binding integration:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest -q
289 passed, 6 skipped in 0.77s
```

## Fix round 2

Integrated binding/registry APIs without modifying their owned files. Dispatch now
uses `metric_spec` and `validate_parameters` as the single disposition source,
metric-local values are selected, and unsupported torque/force/unbound activity
claims are explicitly UNASSESSED. Nonfinite derivative facts retain finite and
missing counts and cannot be reported as successful derivatives. Bound activity
runs are emitted for absolute position as well as velocity/delta representations.

Focused verification:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_measurements.py tests/test_quality_motion_semantics.py tests/test_quality_visual_measurements.py tests/test_quality_config.py tests/test_quality_semantic_binding.py -q
54 passed in 0.13s
```

Final full-suite verification after fix round 2:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest -q
289 passed, 6 skipped in 1.08s
```

## Fix round 3

`measure_unit` now validates the plan unit episode identity and fails closed
with `sampling_range_requires_window_provider` when a nonvisual unit requests a
partial timestamp interval that no bounded window provider supplied.

Focused regression: `tests/test_quality_measurements.py` — 5 passed in 0.07s.
The real H264 decode-to-measurement test remains a runner-level integration
responsibility because this unit receives an already bounded Task 2 provider.

## Fix round 3/5

Nonfinite derivative and acceleration values are serialized as null with finite,
missing and location metadata; measurement dispatch returns UNKNOWN partial
coverage for nonfinite facts or missing semantic binding. Registry-validated
`activity_epsilon` and `smoothing` are now consumed by feature calculations.
Discrete and absolute-position activity facts include transition/run evidence,
and metric dispatch uses the registry disposition API.

Focused verification: 11 passed in 0.10s.

## Fix round 3/5 denominator correction

Absolute-position activity is now represented as an n-frame mask (first frame
explicitly idle, subsequent frames based on configured epsilon), so activity
counts/runs align with the idle-ratio denominator and remain bounded for
single-frame episodes.

Focused regression: `tests/test_quality_measurements.py` — 6 passed in 0.07s.
