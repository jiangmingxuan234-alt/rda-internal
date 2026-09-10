from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from rda.io.lerobot_loader import iter_quality_episode_batches
from rda.quality.input_manifest import QualityInputError, iter_episode_segments, load_quality_manifest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_digest(sources: list[dict]) -> str:
    protected = [
        {"relative_path": source["relative_path"], "byte_size": source["byte_size"], "sha256": source["sha256"]}
        for source in sorted(sources, key=lambda source: source["relative_path"])
    ]
    return hashlib.sha256(json.dumps(protected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _base_manifest(root: Path) -> tuple[dict, Path]:
    source = root / "data" / "rows.parquet"
    source.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table(
            {
                "episode_index": [4, 4],
                "timestamp": [2.0, 2.1],
                "frame_index": [0, 1],
                "index": [20, 21],
                "task_index": [6, 6],
            }
        ),
        source,
    )
    sources = [{"relative_path": "data/rows.parquet", "byte_size": source.stat().st_size, "sha256": _sha(source), "status": "complete"}]
    segment = {
        "episode_id": 4,
        "order": 0,
        "relative_path": "data/rows.parquet",
        "source_sha256": _sha(source),
        "row_group": 0,
        "row_coordinate_basis": "row_group",
        "row_start": 0,
        "row_end": 2,
        "row_count": 2,
        "index_bounds": {"global_from": 20, "global_to": 22, "frame_from": 0, "frame_to": 2},
        "task_indexes": [6],
        "status": "complete",
    }
    manifest = {
        "contract_version": 1,
        "dataset_root": ".",
        "producer": {"robovet_run_id": "rv-run-input", "mode": "full", "artifact_sha256": "b" * 64},
        "scope": {"episode_ids": [4]},
        "snapshot_identity": {
            "hash_algorithm": "sha256",
            "guarantee_method": "immutable_snapshot",
            "digest": _snapshot_digest(sources),
            "sources": sources,
        },
        "timestamp_clock": {"domain": "lerobot_timestamp_seconds", "mapping_version": 1},
        "episodes": [
            {
                "episode_id": 4,
                "raw_id": "producer-raw-4",
                "declared_length": 2,
                "dataset_index": {"from": 20, "to": 22},
                "timestamp": {"from": 2.0, "to": 2.2},
                "tasks": [{"task_index": 6, "text": "open drawer"}],
                "row_segments": [segment],
                "media": [],
            }
        ],
    }
    return manifest, source


def _write(root: Path, manifest: dict) -> Path:
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_manifest_exposes_source_task_and_stable_segment_identity(tmp_path):
    root = tmp_path / "dataset"
    raw, _ = _base_manifest(root)
    manifest = load_quality_manifest(_write(root, raw))

    assert manifest.robovet_run_id == "rv-run-input"
    assert manifest.expected_episode_ids == (4,)
    assert [(task.task_index, task.text) for task in manifest.episodes[4].tasks] == [(6, "open drawer")]
    segment = list(iter_episode_segments(manifest, 4))[0]
    assert (segment.relative_path, segment.row_group, segment.row_start, segment.row_end) == ("data/rows.parquet", 0, 0, 2)
    assert segment.task_indexes == (6,)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value["producer"].pop("robovet_run_id"), "missing_field"),
        (lambda value: value["producer"].update(mode="sampled"), "unsupported_mode"),
        (lambda value: value["episodes"][0]["row_segments"][0].update(row_coordinate_basis="scanner_batch"), "unsupported_layout"),
        (lambda value: value["episodes"][0]["row_segments"][0].update(status="partial"), "incomplete_segment"),
    ],
)
def test_required_contract_failures_are_structured(tmp_path, mutation, code):
    root = tmp_path / "dataset"
    raw, _ = _base_manifest(root)
    mutation(raw)
    with pytest.raises(QualityInputError) as caught:
        load_quality_manifest(_write(root, raw))
    assert caught.value.code == code
    assert caught.value.to_dict()["message"]


def test_explicit_empty_scope_and_empty_episode_are_supported(tmp_path):
    root = tmp_path / "dataset"
    root.mkdir()
    empty_scope = {
        "contract_version": 1,
        "dataset_root": ".",
        "producer": {"robovet_run_id": "rv-empty", "mode": "full", "artifact_sha256": "c" * 64},
        "scope": {"episode_ids": []},
        "snapshot_identity": {
            "hash_algorithm": "sha256",
            "guarantee_method": "final_consistency_pass",
            "digest": _snapshot_digest([]),
            "sources": [],
        },
        "timestamp_clock": {"domain": "lerobot_timestamp_seconds", "mapping_version": 1},
        "episodes": [],
    }
    assert load_quality_manifest(_write(root, empty_scope)).expected_episode_ids == ()

    empty_episode = copy.deepcopy(empty_scope)
    empty_episode["scope"]["episode_ids"] = [9]
    empty_episode["episodes"] = [
        {
            "episode_id": 9,
            "raw_id": "raw-empty",
            "declared_length": 0,
            "dataset_index": {"from": 22, "to": 22},
            "timestamp": {"from": 3.0, "to": 3.0},
            "tasks": [],
            "row_segments": [],
            "media": [],
        }
    ]
    manifest = load_quality_manifest(_write(root, empty_episode))
    assert list(iter_episode_segments(manifest, 9)) == []


def test_source_replacement_after_load_is_caught_before_row_read(tmp_path):
    root = tmp_path / "dataset"
    raw, source = _base_manifest(root)
    manifest = load_quality_manifest(_write(root, raw))
    source.write_bytes(b"replacement")

    with pytest.raises(QualityInputError) as caught:
        list(iter_quality_episode_batches(manifest, 4, columns=["timestamp"]))
    assert caught.value.code == "source_changed"


def test_public_source_paths_cannot_traverse_or_escape_through_symlinks(tmp_path):
    root = tmp_path / "dataset"
    raw, _ = _base_manifest(root)
    raw["snapshot_identity"]["sources"][0]["relative_path"] = "../outside.parquet"
    with pytest.raises(QualityInputError) as caught:
        load_quality_manifest(_write(root, raw))
    assert caught.value.code == "unsafe_path"

    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"outside")
    link = root / "data" / "escape.parquet"
    link.symlink_to(outside)
    raw, _ = _base_manifest(root)
    source = {"relative_path": "data/escape.parquet", "byte_size": outside.stat().st_size, "sha256": _sha(outside), "status": "complete"}
    raw["snapshot_identity"]["sources"] = [source]
    raw["snapshot_identity"]["digest"] = _snapshot_digest([source])
    raw["episodes"][0]["row_segments"][0].update(relative_path="data/escape.parquet", source_sha256=_sha(outside))
    with pytest.raises(QualityInputError) as caught:
        load_quality_manifest(_write(root, raw))
    assert caught.value.code == "unsafe_path"


def test_overlapping_or_missing_row_segments_fail_closed(tmp_path):
    root = tmp_path / "dataset"
    raw, _ = _base_manifest(root)
    duplicate = copy.deepcopy(raw["episodes"][0]["row_segments"][0])
    duplicate.update(order=1, index_bounds={"global_from": 22, "global_to": 24, "frame_from": 2, "frame_to": 4})
    raw["episodes"][0]["row_segments"].append(duplicate)
    raw["episodes"][0].update(declared_length=4, dataset_index={"from": 20, "to": 24})
    with pytest.raises(QualityInputError) as caught:
        load_quality_manifest(_write(root, raw))
    assert caught.value.code == "overlapping_segments"

    raw, _ = _base_manifest(root)
    raw["episodes"][0]["declared_length"] = 3
    raw["episodes"][0]["dataset_index"]["to"] = 23
    with pytest.raises(QualityInputError) as caught:
        load_quality_manifest(_write(root, raw))
    assert caught.value.code == "missing_segments"


def test_shared_media_overlap_requires_explicit_bounded_disposition(tmp_path):
    root = tmp_path / "dataset"
    raw, parquet = _base_manifest(root)
    video = root / "videos" / "shared.mp4"
    video.parent.mkdir()
    video.write_bytes(b"placeholder")
    video_source = {"relative_path": "videos/shared.mp4", "byte_size": video.stat().st_size, "sha256": _sha(video), "status": "complete"}
    raw["snapshot_identity"]["sources"].append(video_source)
    raw["snapshot_identity"]["digest"] = _snapshot_digest(raw["snapshot_identity"]["sources"])
    media = {
        "episode_id": 4,
        "feature_key": "observation.images.front",
        "relative_path": "videos/shared.mp4",
        "source_sha256": _sha(video),
        "stream_index": 0,
        "from_timestamp": 2.0,
        "to_timestamp": 2.2,
        "clock_domain": "lerobot_timestamp_seconds",
        "clock_mapping": {"kind": "affine", "version": 1, "scale": 1.0, "offset": 0.0},
        "stream": {"start_time": 0, "time_base_numerator": 1, "time_base_denominator": 10},
        "status": "complete",
    }
    raw["episodes"][0]["media"] = [media]
    second = copy.deepcopy(raw["episodes"][0])
    second.update(episode_id=5, raw_id="raw-5", declared_length=0, dataset_index={"from": 22, "to": 22}, timestamp={"from": 2.1, "to": 2.3}, row_segments=[], tasks=[])
    second_media = copy.deepcopy(media)
    second_media.update(episode_id=5, from_timestamp=2.1, to_timestamp=2.3)
    second["media"] = [second_media]
    raw["scope"]["episode_ids"] = [4, 5]
    raw["episodes"].append(second)

    with pytest.raises(QualityInputError) as caught:
        load_quality_manifest(_write(root, raw))
    assert caught.value.code == "media_overlap_disposition_required"

    raw["episodes"][0]["media"][0]["overlap_disposition"] = "shared_source_bounded"
    raw["episodes"][1]["media"][0]["overlap_disposition"] = "shared_source_bounded"
    manifest = load_quality_manifest(_write(root, raw))
    assert manifest.episodes[4].media[0].overlap_disposition == "shared_source_bounded"


def test_physical_row_cannot_be_claimed_by_two_episodes(tmp_path):
    root = tmp_path / "dataset"
    raw, _ = _base_manifest(root)
    second = copy.deepcopy(raw["episodes"][0])
    second.update(episode_id=5, raw_id="raw-5")
    second["row_segments"][0]["episode_id"] = 5
    raw["scope"]["episode_ids"] = [4, 5]
    raw["episodes"].append(second)

    with pytest.raises(QualityInputError) as caught:
        load_quality_manifest(_write(root, raw))
    assert caught.value.code == "overlapping_segments"
