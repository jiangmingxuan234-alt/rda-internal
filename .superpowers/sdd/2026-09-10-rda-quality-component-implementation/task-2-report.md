# Task 2 report: quality input and media boundaries

## Delivered

- Added the versioned, producer-independent JSON manifest reader in
  `rda.quality.input_manifest`.  It validates complete full-mode scope,
  protected-source snapshot digest and hashes, safe paths, exact expected
  episode order, task bindings, half-open Parquet segments, and per-camera
  H.264 media references.
- Added the explicit quality-only Parquet reader.  It streams manifest row
  groups in a caller-configurable bounded `batch_size` (default `65536`),
  slices half-open segment offsets across batches, preserves original
  `timestamp`, `frame_index`, `index`, and `task_index`, and reconciles each
  batch plus final task-set/source identity.  Legacy loaders were not changed.
- Added bounded MP4/H.264 decode.  It retains only the preceding and current
  decoded candidate while choosing nearest targets, filters mapped PTS to the
  half-open media interval, carries actual PTS/time base/stream ordinal, and
  reports missing media, unsupported streams/codecs, identity changes,
  undecodable tails, invalid targets, and decoder failures as structured
  errors.  A stream failure preserves samples emitted before the failure.

## Serialized schema

The exact v1 field names and coordinate/clock rules are documented in
`docs/quality-input-manifest-v1.md`.  The root fields are
`contract_version`, `dataset_root`, `producer`, `scope`,
`snapshot_identity`, `timestamp_clock`, and `episodes`.

`snapshot_identity.digest` is SHA-256 of canonical sorted source entries
containing exactly `relative_path`, `byte_size`, and `sha256`.  Segment row
coordinates are zero-based `[row_start, row_end)` offsets inside `row_group`.
All episode index/time and media time intervals are half-open.  Media mapping
is `mapped_timestamp = (PTS * time_base) * scale + offset` in the declared
`timestamp_clock.domain`; `stream.start_time` remains explicit metadata.

## Tests

## TDD record and coverage points

The controller verified the inherited Task 2 baseline before this recovery
turn with:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_input_manifest.py tests/test_quality_v30_boundaries.py tests/test_quality_media_pts.py -q
17 passed in 0.24s
```

That is a controller baseline, not a RED result produced in this recovery
turn.  No claim is made about the earlier interrupted agent's unsaved test
history.

The following RED commands and observed failures were executed during this
recovery before their corresponding implementation changes:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_media_pts.py::test_decode_stream_failure_preserves_samples_completed_before_failure -q
FAILED: expected completed target [5.01], received []
```

This covered an interrupted decoder retaining a sample that had become
mappable before the failure while marking only the remaining target as an
error.

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_v30_boundaries.py::test_quality_reader_streams_a_row_group_in_bounded_batches -q
FAILED: TypeError: iter_quality_episode_batches() got an unexpected keyword argument 'batch_size'
```

This covered bounded Parquet iteration across a five-row segment split into
`[2, 2, 1]` batches.

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_media_pts.py::test_decode_maps_an_exact_target_from_a_single_decodable_frame -q
FAILED: expected completed target [5.0], received []
```

This covered a single decodable frame whose mapped PTS exactly equals the
requested target.

Focused tests:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_v30_boundaries.py -q
3 passed in 0.19s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_input_manifest.py tests/test_quality_media_pts.py -q
16 passed in 0.22s
```

Those two focused invocations were run before the final single-frame test was
added: `3 + 16 = 19` tests at that point.  After the single-frame regression
was added and fixed, the final focused verification was:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_input_manifest.py tests/test_quality_v30_boundaries.py tests/test_quality_media_pts.py -q
20 passed in 0.27s
```

Full suite:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest -q
226 passed, 6 skipped in 0.72s
```

The full-suite count is 20 tests above the Task 1 baseline of 206 passing
tests; these 20 focused Task 2 tests were present at final verification.

## Concerns

- The contract deliberately fails closed for fields and layouts outside v1;
  later producers must emit the documented complete source and stream facts.
- A source replacement discovered after a streaming read cannot retract frames
  already yielded.  Completed frames remain observable and unfinished targets
  receive structured errors, so coverage reflects actual work rather than a
  fabricated all-or-nothing result.

## Review fix round 1

The review fixes reject nonpositive affine scales at manifest load, require an
MP4 path and actual MP4 container, validate raw timestamps as finite and
within their declared half-open episode interval, and replace row-by-row
overlap sets with sorted half-open segment intervals.  Decode stops after the
successor needed for the final target and still performs its terminal source
hash guard.  The schema now calls decoded ordinal seek-local and identifies
source hash, stream index, and PTS as the cross-request identity.

Observed RED checks in this round included:

```
... pytest tests/test_quality_input_manifest.py::test_manifest_rejects_nonpositive_media_clock_scale -q
2 failed: DID NOT RAISE QualityInputError

... pytest tests/test_quality_media_pts.py::test_decode_rejects_a_renamed_matroska_container -q
1 failed: expected unsupported_container, received stream_identity_mismatch
```

Final verification after the round:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_input_manifest.py tests/test_quality_v30_boundaries.py tests/test_quality_media_pts.py -q
24 passed in 0.25s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest -q
230 passed, 6 skipped in 0.69s
```

## Review minor follow-up

`iter_quality_episode_batches` now translates an out-of-scope episode lookup
into `QualityInputError(code="unknown_episode")`; the v1 schema explicitly
states that affine `clock_mapping.scale` is strictly positive.

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. /tmp/rda-quality-venv/bin/python -m pytest tests/test_quality_input_manifest.py tests/test_quality_v30_boundaries.py tests/test_quality_media_pts.py -q
25 passed in 0.25s
```
