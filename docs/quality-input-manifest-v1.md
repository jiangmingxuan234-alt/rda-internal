# Quality input manifest v1

This JSON document is the producer-independent boundary consumed by RDA
quality-mode readers.  It does not contain Robovet Python/SQLite objects or an
acceptance verdict.  All required source and segment/media `status` values are
`"complete"`; another value is a structured input error.

```json
{
  "contract_version": 1,
  "dataset_root": ".",
  "producer": {
    "robovet_run_id": "unique producer run id",
    "mode": "full",
    "artifact_sha256": "64 lowercase hexadecimal characters"
  },
  "scope": {"episode_ids": [7]},
  "snapshot_identity": {
    "hash_algorithm": "sha256",
    "guarantee_method": "final_consistency_pass",
    "digest": "sha256 of canonical protected source list",
    "sources": [{
      "relative_path": "data/chunk-000/file-000.parquet",
      "byte_size": 123,
      "sha256": "64 lowercase hexadecimal characters",
      "status": "complete"
    }]
  },
  "timestamp_clock": {
    "domain": "lerobot_timestamp_seconds",
    "mapping_version": 1
  },
  "episodes": []
}
```

`dataset_root` and every public `relative_path` are normalized relative paths.
Absolute paths, traversal, and paths resolving through a symlink outside the
dataset root are rejected.  `snapshot_identity.digest` is SHA-256 over UTF-8
canonical JSON (`sort_keys=True`, separators `(',', ':')`) of the list sorted
by `relative_path`, with each item exactly `{relative_path, byte_size, sha256}`.
It protects original dataset files; the producer artifact hash and a
reserialized Arrow/JSON snapshot hash are not substitutes.

Each episode, in exactly `scope.episode_ids` order, has:

```json
{
  "episode_id": 7,
  "raw_id": "producer source identity",
  "declared_length": 2,
  "dataset_index": {"from": 10, "to": 12},
  "timestamp": {"from": 1.0, "to": 1.2},
  "tasks": [{"task_index": 3, "text": "place item"}],
  "row_segments": [],
  "media": []
}
```

Index and timestamp `from`/`to` values are half-open.  `declared_length`
equals `dataset_index.to - dataset_index.from` and the total row-segment
count.  Task bindings preserve original `task_index` plus text; each segment
lists all original task indexes present in its rows.

Each `row_segments` entry, in zero-based contiguous `order`, is:

```json
{
  "episode_id": 7,
  "order": 0,
  "relative_path": "data/chunk-000/file-000.parquet",
  "source_sha256": "same hash as protected source",
  "row_group": 0,
  "row_coordinate_basis": "row_group",
  "row_start": 0,
  "row_end": 2,
  "row_count": 2,
  "index_bounds": {"global_from": 10, "global_to": 12, "frame_from": 0, "frame_to": 2},
  "task_indexes": [3],
  "status": "complete"
}
```

`row_start`/`row_end` are zero-based half-open offsets inside the physical
Parquet row group.  Segments are ordered and contiguous in global and frame
index coordinates, cannot overlap physical rows, and preserve the source
columns `timestamp`, `frame_index`, `index`, and `task_index` without timeline
synthesis.  RDA may stream row groups in bounded batches.

Each camera `media` entry is:

```json
{
  "episode_id": 7,
  "feature_key": "observation.images.front",
  "relative_path": "videos/chunk-000/file-000.mp4",
  "source_sha256": "same hash as protected source",
  "stream_index": 0,
  "from_timestamp": 1.0,
  "to_timestamp": 1.2,
  "clock_domain": "lerobot_timestamp_seconds",
  "clock_mapping": {"kind": "affine", "version": 1, "scale": 1.0, "offset": 0.0},
  "stream": {"start_time": 0, "time_base_numerator": 1, "time_base_denominator": 90000},
  "status": "complete",
  "overlap_disposition": "shared_source_bounded"
}
```

`clock_mapping.scale` must be finite and strictly greater than zero.
`overlap_disposition` is optional unless two episodes overlap on the same
path, stream, and feature key, when both entries must use
`"shared_source_bounded"`.  Version 1 authorizes H.264/MP4 only.  Media
intervals are finite, nonempty, half-open, and share `timestamp_clock.domain`
with row timestamps.  The mapping is `mapped_timestamp = (PTS * time_base) *
scale + offset`; `stream.start_time` is recorded and never implicitly
subtracted.  Decoded stream ordinal is separate from a LeRobot frame index.
Because bounded decoding seeks before decoding, the reported ordinal is local
to that seek/decode pass; cross-request frame identity is the protected source
hash together with stream index and PTS.
