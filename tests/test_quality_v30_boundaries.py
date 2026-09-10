from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from rda.io.lerobot_loader import iter_quality_episode_batches
from rda.quality.input_manifest import load_quality_manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_manifest(root: Path, segments: list[dict]) -> Path:
    declared_length = sum(segment["row_count"] for segment in segments)
    dataset_from = segments[0]["index_bounds"]["global_from"] if segments else 0
    sources = []
    for relative_path in sorted({segment["relative_path"] for segment in segments}):
        source = root / relative_path
        sources.append(
            {
                "relative_path": relative_path,
                "byte_size": source.stat().st_size,
                "sha256": _sha256(source),
                "status": "complete",
            }
        )
    snapshot_payload = [
        {"relative_path": item["relative_path"], "byte_size": item["byte_size"], "sha256": item["sha256"]}
        for item in sources
    ]
    snapshot_digest = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    manifest = {
        "contract_version": 1,
        "dataset_root": ".",
        "producer": {
            "robovet_run_id": "rv-run-boundaries",
            "mode": "full",
            "artifact_sha256": "a" * 64,
        },
        "scope": {"episode_ids": [7]},
        "snapshot_identity": {
            "hash_algorithm": "sha256",
            "guarantee_method": "final_consistency_pass",
            "digest": snapshot_digest,
            "sources": sources,
        },
        "timestamp_clock": {"domain": "lerobot_timestamp_seconds", "mapping_version": 1},
        "episodes": [
            {
                "episode_id": 7,
                "raw_id": "raw-7",
                "declared_length": declared_length,
                "dataset_index": {"from": dataset_from, "to": dataset_from + declared_length},
                "timestamp": {"from": 1.0, "to": 1.4},
                "tasks": [{"task_index": 3, "text": "place item"}],
                "row_segments": segments,
                "media": [],
            }
        ],
    }
    path = root / "quality-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_quality_reader_consumes_all_half_open_segments_without_neighbor_rows(tmp_path):
    root = tmp_path / "dataset"
    (root / "data").mkdir(parents=True)
    first = root / "data" / "first.parquet"
    second = root / "data" / "second.parquet"
    pq.write_table(
        pa.table(
            {
                "episode_index": [6, 7, 7, 8],
                "timestamp": [0.9, 1.0, 1.1, 1.4],
                "frame_index": [9, 0, 1, 0],
                "index": [9, 10, 11, 14],
                "task_index": [9, 3, 3, 8],
                "action": [[0.0], [1.0], [2.0], [9.0]],
            }
        ),
        first,
        row_group_size=4,
    )
    pq.write_table(
        pa.table(
            {
                "episode_index": [7, 7, 8],
                "timestamp": [1.2, 1.3, 1.5],
                "frame_index": [2, 3, 1],
                "index": [12, 13, 15],
                "task_index": [3, 3, 8],
                "action": [[3.0], [4.0], [10.0]],
            }
        ),
        second,
        row_group_size=3,
    )
    segments = [
        {
            "episode_id": 7,
            "order": 0,
            "relative_path": "data/first.parquet",
            "source_sha256": _sha256(first),
            "row_group": 0,
            "row_coordinate_basis": "row_group",
            "row_start": 1,
            "row_end": 3,
            "row_count": 2,
            "index_bounds": {"global_from": 10, "global_to": 12, "frame_from": 0, "frame_to": 2},
            "task_indexes": [3],
            "status": "complete",
        },
        {
            "episode_id": 7,
            "order": 1,
            "relative_path": "data/second.parquet",
            "source_sha256": _sha256(second),
            "row_group": 0,
            "row_coordinate_basis": "row_group",
            "row_start": 0,
            "row_end": 2,
            "row_count": 2,
            "index_bounds": {"global_from": 12, "global_to": 14, "frame_from": 2, "frame_to": 4},
            "task_indexes": [3],
            "status": "complete",
        },
    ]
    manifest = load_quality_manifest(_write_manifest(root, segments))

    batches = list(
        iter_quality_episode_batches(
            manifest,
            7,
            columns=["timestamp", "frame_index", "index", "task_index", "action"],
        )
    )
    combined = pa.Table.from_batches(batches).to_pydict()

    assert combined == {
        "timestamp": [1.0, 1.1, 1.2, 1.3],
        "frame_index": [0, 1, 2, 3],
        "index": [10, 11, 12, 13],
        "task_index": [3, 3, 3, 3],
        "action": [[1.0], [2.0], [3.0], [4.0]],
    }
    assert [batch.num_rows for batch in batches] == [2, 2]


def test_quality_reader_does_not_synthesize_missing_timestamp(tmp_path):
    root = tmp_path / "dataset"
    (root / "data").mkdir(parents=True)
    source = root / "data" / "rows.parquet"
    pq.write_table(pa.table({"episode_index": [7], "frame_index": [0], "index": [10], "task_index": [3]}), source)
    segment = {
        "episode_id": 7,
        "order": 0,
        "relative_path": "data/rows.parquet",
        "source_sha256": _sha256(source),
        "row_group": 0,
        "row_coordinate_basis": "row_group",
        "row_start": 0,
        "row_end": 1,
        "row_count": 1,
        "index_bounds": {"global_from": 10, "global_to": 11, "frame_from": 0, "frame_to": 1},
        "task_indexes": [3],
        "status": "complete",
    }
    manifest = load_quality_manifest(_write_manifest(root, [segment]))

    try:
        list(iter_quality_episode_batches(manifest, 7, columns=["timestamp", "frame_index"]))
    except Exception as exc:
        assert getattr(exc, "code", None) == "unsupported_layout"
    else:
        raise AssertionError("missing timestamp must fail closed")


def test_quality_reader_streams_a_row_group_in_bounded_batches(tmp_path):
    """Removing batch iteration would collapse this five-row segment into one batch."""
    root = tmp_path / "dataset"
    source = root / "data" / "rows.parquet"
    source.parent.mkdir(parents=True)
    pq.write_table(
        pa.table(
            {
                "episode_index": [7] * 5,
                "timestamp": [1.0, 1.1, 1.2, 1.3, 1.4],
                "frame_index": [0, 1, 2, 3, 4],
                "index": [10, 11, 12, 13, 14],
                "task_index": [3, 3, 3, 3, 3],
            }
        ),
        source,
        row_group_size=5,
    )
    segment = {
        "episode_id": 7,
        "order": 0,
        "relative_path": "data/rows.parquet",
        "source_sha256": _sha256(source),
        "row_group": 0,
        "row_coordinate_basis": "row_group",
        "row_start": 0,
        "row_end": 5,
        "row_count": 5,
        "index_bounds": {"global_from": 10, "global_to": 15, "frame_from": 0, "frame_to": 5},
        "task_indexes": [3],
        "status": "complete",
    }
    manifest = load_quality_manifest(_write_manifest(root, [segment]))

    batches = list(
        iter_quality_episode_batches(
            manifest,
            7,
            columns=["timestamp", "frame_index", "index", "task_index"],
            batch_size=2,
        )
    )

    assert [batch.num_rows for batch in batches] == [2, 2, 1]
    assert pa.Table.from_batches(batches).column("index").to_pylist() == [10, 11, 12, 13, 14]
