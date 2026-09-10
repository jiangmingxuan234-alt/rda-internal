"""Versioned, verified input contract for RDA quality-mode reads.

Contract version 1 is JSON and deliberately contains no Robovet Python or
SQLite types.  ``producer.artifact_sha256`` binds the upstream sealed
evidence artifact consumed by the adapter; it is not a hash of this manifest,
which avoids a self-hash cycle.  ``snapshot_identity.digest`` is SHA-256 over
the canonical JSON array of source entries, sorted by ``relative_path`` and
containing exactly ``relative_path``, ``byte_size`` and ``sha256``.

Parquet ``row_start``/``row_end`` are zero-based, half-open offsets within the
declared physical row group (``row_coordinate_basis == 'row_group'``).  Media
times, row timestamps and mapped ``PTS * time_base`` share
``timestamp_clock.domain``.  Version 1 maps media time with the explicit
affine transform ``mapped = pts_time * scale + offset``; stream start time is
preserved as metadata and is never implicitly subtracted.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class QualityInputError(ValueError):
    """A stable, structured failure at the quality input boundary."""

    def __init__(self, code: str, message: str, *, location: str | None = None):
        super().__init__(message)
        self.code = code
        self.location = location

    def to_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": str(self)}
        if self.location is not None:
            result["location"] = self.location
        return result


@dataclass(frozen=True)
class SourceFile:
    relative_path: str
    path: Path
    byte_size: int
    sha256: str
    status: str


@dataclass(frozen=True)
class TaskBinding:
    task_index: int
    text: str


@dataclass(frozen=True)
class EpisodeSegment:
    episode_id: int
    order: int
    source_path: Path
    relative_path: str
    source_sha256: str
    row_group: int
    row_start: int
    row_end: int
    row_count: int
    global_from: int
    global_to: int
    frame_from: int
    frame_to: int
    task_indexes: tuple[int, ...]
    status: str


@dataclass(frozen=True)
class MediaRef:
    episode_id: int
    feature_key: str
    source_path: Path
    relative_path: str
    source_sha256: str
    stream_index: int
    from_timestamp: float
    to_timestamp: float
    clock_domain: str
    mapping_version: int
    pts_time_scale: float
    pts_time_offset: float
    stream_start_time: int | None
    stream_time_base: Fraction
    status: str
    overlap_disposition: str | None = None
    source_byte_size: int | None = None


@dataclass(frozen=True)
class EpisodeManifest:
    episode_id: int
    raw_id: str
    declared_length: int
    dataset_from: int
    dataset_to: int
    timestamp_from: float | None
    timestamp_to: float | None
    tasks: tuple[TaskBinding, ...]
    row_segments: tuple[EpisodeSegment, ...]
    media: tuple[MediaRef, ...]


@dataclass(frozen=True)
class QualityInputManifest:
    contract_version: int
    path: Path
    dataset_root: Path
    robovet_run_id: str
    producer_artifact_sha256: str
    snapshot_digest: str
    snapshot_guarantee_method: str
    clock_domain: str
    clock_mapping_version: int
    expected_episode_ids: tuple[int, ...]
    episodes: Mapping[int, EpisodeManifest]
    sources: Mapping[str, SourceFile]


def _error(code: str, message: str, location: str | None = None) -> QualityInputError:
    return QualityInputError(code, message, location=location)


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise _error("invalid_manifest", f"{location} must be an object", location)
    return value


def _list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error("invalid_manifest", f"{location} must be an array", location)
    return value


def _required(mapping: Mapping[str, Any], field: str, location: str) -> Any:
    if field not in mapping:
        field_location = f"{location}.{field}"
        raise _error("missing_field", f"missing required field {field_location}", field_location)
    return mapping[field]


def _integer(value: Any, location: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _error("invalid_manifest", f"{location} must be an integer >= {minimum}", location)
    return value


def _number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _error("invalid_manifest", f"{location} must be finite", location)
    return float(value)


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error("invalid_manifest", f"{location} must be a non-empty string", location)
    return value


def _sha256(value: Any, location: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise _error("invalid_manifest", f"{location} must be a lowercase SHA-256 hex digest", location)
    return value


def _relative_path(value: Any, location: str) -> str:
    value = _text(value, location)
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or value != candidate.as_posix():
        raise _error("unsafe_path", f"{location} must be a normalized safe relative path", location)
    return value


def _resolve_source(dataset_root: Path, relative_path: str, location: str) -> Path:
    root = dataset_root.resolve()
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise _error("unsafe_path", f"{location} escapes dataset_root", location) from None
    return resolved


def _canonical_snapshot(entries: list[dict[str, Any]]) -> bytes:
    protected = [
        {"relative_path": item["relative_path"], "byte_size": item["byte_size"], "sha256": item["sha256"]}
        for item in sorted(entries, key=lambda item: item["relative_path"])
    ]
    return json.dumps(protected, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source(source: SourceFile) -> None:
    try:
        stat = source.path.stat()
    except FileNotFoundError:
        raise _error("missing_source", f"protected source is missing: {source.relative_path}", source.relative_path) from None
    if not source.path.is_file() or stat.st_size != source.byte_size or file_sha256(source.path) != source.sha256:
        raise _error("source_changed", f"protected source identity changed: {source.relative_path}", source.relative_path)


def _validate_segment_intervals(segments: list[EpisodeSegment], location: str) -> None:
    """Reject physical row overlap using segment-sized, not row-sized, state."""
    by_source: dict[tuple[str, int], list[tuple[int, int]]] = {}
    for segment in segments:
        by_source.setdefault((segment.relative_path, segment.row_group), []).append((segment.row_start, segment.row_end))
    for intervals in by_source.values():
        previous_end = -1
        for start, end in sorted(intervals):
            if start < previous_end:
                raise _error("overlapping_segments", "row segments overlap or duplicate a physical row", location)
            previous_end = end


def load_quality_manifest(path: Path) -> QualityInputManifest:
    """Load and verify a producer-independent version 1 quality manifest."""
    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _error("invalid_manifest", f"cannot read manifest: {exc}") from exc
    root = _mapping(raw, "manifest")
    version = _integer(_required(root, "contract_version", "manifest"), "contract_version", minimum=1)
    if version != 1:
        raise _error("unsupported_contract", f"unsupported contract_version: {version}", "contract_version")
    root_value = _relative_path(_required(root, "dataset_root", "manifest"), "dataset_root")
    dataset_root = (path.parent / root_value).resolve()

    producer = _mapping(_required(root, "producer", "manifest"), "producer")
    run_id = _text(_required(producer, "robovet_run_id", "producer"), "producer.robovet_run_id")
    if _required(producer, "mode", "producer") != "full":
        raise _error("unsupported_mode", "producer.mode must be 'full'", "producer.mode")
    artifact_hash = _sha256(_required(producer, "artifact_sha256", "producer"), "producer.artifact_sha256")

    scope = _mapping(_required(root, "scope", "manifest"), "scope")
    expected_ids = tuple(_integer(value, f"scope.episode_ids[{index}]") for index, value in enumerate(_list(_required(scope, "episode_ids", "scope"), "scope.episode_ids")))
    if len(set(expected_ids)) != len(expected_ids):
        raise _error("duplicate_episode", "scope.episode_ids contains duplicates", "scope.episode_ids")

    clock = _mapping(_required(root, "timestamp_clock", "manifest"), "timestamp_clock")
    clock_domain = _text(_required(clock, "domain", "timestamp_clock"), "timestamp_clock.domain")
    mapping_version = _integer(_required(clock, "mapping_version", "timestamp_clock"), "timestamp_clock.mapping_version", minimum=1)
    if mapping_version != 1:
        raise _error("unsupported_clock_mapping", "only timestamp clock mapping version 1 is supported", "timestamp_clock.mapping_version")

    snapshot = _mapping(_required(root, "snapshot_identity", "manifest"), "snapshot_identity")
    if _required(snapshot, "hash_algorithm", "snapshot_identity") != "sha256":
        raise _error("unsupported_hash", "snapshot_identity.hash_algorithm must be sha256", "snapshot_identity.hash_algorithm")
    guarantee = _text(_required(snapshot, "guarantee_method", "snapshot_identity"), "snapshot_identity.guarantee_method")
    digest = _sha256(_required(snapshot, "digest", "snapshot_identity"), "snapshot_identity.digest")
    source_items = _list(_required(snapshot, "sources", "snapshot_identity"), "snapshot_identity.sources")
    normalized_sources: list[dict[str, Any]] = []
    sources: dict[str, SourceFile] = {}
    for index, value in enumerate(source_items):
        location = f"snapshot_identity.sources[{index}]"
        item = _mapping(value, location)
        relative = _relative_path(_required(item, "relative_path", location), f"{location}.relative_path")
        if relative in sources:
            raise _error("duplicate_source", f"duplicate protected source: {relative}", location)
        byte_size = _integer(_required(item, "byte_size", location), f"{location}.byte_size")
        source_hash = _sha256(_required(item, "sha256", location), f"{location}.sha256")
        status = _text(_required(item, "status", location), f"{location}.status")
        if status != "complete":
            raise _error("incomplete_source", f"protected source is not complete: {relative}", location)
        source = SourceFile(relative, _resolve_source(dataset_root, relative, location), byte_size, source_hash, status)
        sources[relative] = source
        normalized_sources.append({"relative_path": relative, "byte_size": byte_size, "sha256": source_hash})
    actual_digest = hashlib.sha256(_canonical_snapshot(normalized_sources)).hexdigest()
    if actual_digest != digest:
        raise _error("snapshot_digest_mismatch", "snapshot_identity.digest does not match canonical protected sources", "snapshot_identity.digest")
    for source in sources.values():
        verify_source(source)

    episodes: dict[int, EpisodeManifest] = {}
    for episode_index, value in enumerate(_list(_required(root, "episodes", "manifest"), "episodes")):
        location = f"episodes[{episode_index}]"
        item = _mapping(value, location)
        episode_id = _integer(_required(item, "episode_id", location), f"{location}.episode_id")
        if episode_id in episodes:
            raise _error("duplicate_episode", f"duplicate episode: {episode_id}", location)
        raw_id = _text(_required(item, "raw_id", location), f"{location}.raw_id")
        length = _integer(_required(item, "declared_length", location), f"{location}.declared_length")
        dataset_index = _mapping(_required(item, "dataset_index", location), f"{location}.dataset_index")
        dataset_from = _integer(_required(dataset_index, "from", f"{location}.dataset_index"), f"{location}.dataset_index.from")
        dataset_to = _integer(_required(dataset_index, "to", f"{location}.dataset_index"), f"{location}.dataset_index.to")
        if dataset_to < dataset_from or dataset_to - dataset_from != length:
            raise _error("invalid_episode_bounds", "episode dataset indexes must be half-open and match declared_length", f"{location}.dataset_index")
        timestamp = _mapping(_required(item, "timestamp", location), f"{location}.timestamp")
        timestamp_from = _number(_required(timestamp, "from", f"{location}.timestamp"), f"{location}.timestamp.from")
        timestamp_to = _number(_required(timestamp, "to", f"{location}.timestamp"), f"{location}.timestamp.to")
        if timestamp_to < timestamp_from:
            raise _error("invalid_episode_bounds", "episode timestamp interval must be half-open and ordered", f"{location}.timestamp")
        tasks = tuple(
            TaskBinding(
                _integer(_required(_mapping(task, f"{location}.tasks[{task_no}]"), "task_index", f"{location}.tasks[{task_no}]"), f"{location}.tasks[{task_no}].task_index"),
                _text(_required(_mapping(task, f"{location}.tasks[{task_no}]"), "text", f"{location}.tasks[{task_no}]"), f"{location}.tasks[{task_no}].text"),
            )
            for task_no, task in enumerate(_list(_required(item, "tasks", location), f"{location}.tasks"))
        )
        task_ids = {task.task_index for task in tasks}
        if len(task_ids) != len(tasks):
            raise _error("duplicate_task", "episode task bindings contain duplicate task indexes", f"{location}.tasks")

        segments: list[EpisodeSegment] = []
        previous_global = dataset_from
        previous_frame = 0
        for segment_no, segment_value in enumerate(_list(_required(item, "row_segments", location), f"{location}.row_segments")):
            segment_location = f"{location}.row_segments[{segment_no}]"
            segment = _mapping(segment_value, segment_location)
            if _integer(_required(segment, "episode_id", segment_location), f"{segment_location}.episode_id") != episode_id:
                raise _error("episode_mismatch", "row segment episode_id does not match its parent", segment_location)
            order = _integer(_required(segment, "order", segment_location), f"{segment_location}.order")
            if order != segment_no:
                raise _error("unordered_segments", "row segment order must be contiguous manifest order", f"{segment_location}.order")
            relative = _relative_path(_required(segment, "relative_path", segment_location), f"{segment_location}.relative_path")
            source = sources.get(relative)
            if source is None:
                raise _error("unprotected_source", f"row segment source is absent from snapshot: {relative}", segment_location)
            source_hash = _sha256(_required(segment, "source_sha256", segment_location), f"{segment_location}.source_sha256")
            if source_hash != source.sha256:
                raise _error("source_hash_mismatch", f"row segment hash differs from protected source: {relative}", segment_location)
            if _required(segment, "row_coordinate_basis", segment_location) != "row_group":
                raise _error("unsupported_layout", "row_coordinate_basis must be 'row_group'", f"{segment_location}.row_coordinate_basis")
            row_group = _integer(_required(segment, "row_group", segment_location), f"{segment_location}.row_group")
            row_start = _integer(_required(segment, "row_start", segment_location), f"{segment_location}.row_start")
            row_end = _integer(_required(segment, "row_end", segment_location), f"{segment_location}.row_end")
            row_count = _integer(_required(segment, "row_count", segment_location), f"{segment_location}.row_count")
            if row_end < row_start or row_end - row_start != row_count:
                raise _error("invalid_row_bounds", "row offsets must be half-open and match row_count", segment_location)
            bounds = _mapping(_required(segment, "index_bounds", segment_location), f"{segment_location}.index_bounds")
            global_from = _integer(_required(bounds, "global_from", f"{segment_location}.index_bounds"), f"{segment_location}.index_bounds.global_from")
            global_to = _integer(_required(bounds, "global_to", f"{segment_location}.index_bounds"), f"{segment_location}.index_bounds.global_to")
            frame_from = _integer(_required(bounds, "frame_from", f"{segment_location}.index_bounds"), f"{segment_location}.index_bounds.frame_from")
            frame_to = _integer(_required(bounds, "frame_to", f"{segment_location}.index_bounds"), f"{segment_location}.index_bounds.frame_to")
            if global_from != previous_global or frame_from != previous_frame or global_to - global_from != row_count or frame_to - frame_from != row_count:
                raise _error("unordered_segments", "segment index bounds must be contiguous and match row_count", segment_location)
            previous_global = global_to
            previous_frame = frame_to
            segment_tasks = tuple(_integer(task, f"{segment_location}.task_indexes") for task in _list(_required(segment, "task_indexes", segment_location), f"{segment_location}.task_indexes"))
            if any(task not in task_ids for task in segment_tasks):
                raise _error("task_mismatch", "segment task_indexes must resolve to episode task bindings", f"{segment_location}.task_indexes")
            status = _text(_required(segment, "status", segment_location), f"{segment_location}.status")
            if status != "complete":
                raise _error("incomplete_segment", "row segment status must be complete", f"{segment_location}.status")
            segments.append(EpisodeSegment(episode_id, order, source.path, relative, source_hash, row_group, row_start, row_end, row_count, global_from, global_to, frame_from, frame_to, segment_tasks, status))
        if sum(segment.row_count for segment in segments) != length or previous_global != dataset_to:
            raise _error("missing_segments", "row segments do not completely cover the declared episode", f"{location}.row_segments")
        _validate_segment_intervals(segments, f"{location}.row_segments")

        media_refs: list[MediaRef] = []
        for media_no, media_value in enumerate(_list(_required(item, "media", location), f"{location}.media")):
            media_location = f"{location}.media[{media_no}]"
            media = _mapping(media_value, media_location)
            if _integer(_required(media, "episode_id", media_location), f"{media_location}.episode_id") != episode_id:
                raise _error("episode_mismatch", "media episode_id does not match its parent", media_location)
            relative = _relative_path(_required(media, "relative_path", media_location), f"{media_location}.relative_path")
            source = sources.get(relative)
            if source is None:
                raise _error("unprotected_source", f"media source is absent from snapshot: {relative}", media_location)
            source_hash = _sha256(_required(media, "source_sha256", media_location), f"{media_location}.source_sha256")
            if source_hash != source.sha256:
                raise _error("source_hash_mismatch", f"media hash differs from protected source: {relative}", media_location)
            start = _number(_required(media, "from_timestamp", media_location), f"{media_location}.from_timestamp")
            end = _number(_required(media, "to_timestamp", media_location), f"{media_location}.to_timestamp")
            if end <= start:
                raise _error("invalid_media_interval", "media interval must be finite, nonempty and half-open", media_location)
            if _text(_required(media, "clock_domain", media_location), f"{media_location}.clock_domain") != clock_domain:
                raise _error("clock_domain_mismatch", "media clock domain differs from manifest timestamp clock", media_location)
            mapping = _mapping(_required(media, "clock_mapping", media_location), f"{media_location}.clock_mapping")
            if _integer(_required(mapping, "version", f"{media_location}.clock_mapping"), f"{media_location}.clock_mapping.version", minimum=1) != mapping_version:
                raise _error("unsupported_clock_mapping", "media clock mapping version differs from manifest", media_location)
            if _required(mapping, "kind", f"{media_location}.clock_mapping") != "affine":
                raise _error("unsupported_clock_mapping", "media clock mapping kind must be affine", media_location)
            scale = _number(_required(mapping, "scale", f"{media_location}.clock_mapping"), f"{media_location}.clock_mapping.scale")
            if scale <= 0:
                raise _error("invalid_manifest", "media clock_mapping.scale must be positive", f"{media_location}.clock_mapping.scale")
            offset = _number(_required(mapping, "offset", f"{media_location}.clock_mapping"), f"{media_location}.clock_mapping.offset")
            stream = _mapping(_required(media, "stream", media_location), f"{media_location}.stream")
            numerator = _integer(_required(stream, "time_base_numerator", f"{media_location}.stream"), f"{media_location}.stream.time_base_numerator", minimum=1)
            denominator = _integer(_required(stream, "time_base_denominator", f"{media_location}.stream"), f"{media_location}.stream.time_base_denominator", minimum=1)
            start_time_value = _required(stream, "start_time", f"{media_location}.stream")
            start_time = None if start_time_value is None else _integer(start_time_value, f"{media_location}.stream.start_time")
            status = _text(_required(media, "status", media_location), f"{media_location}.status")
            if status != "complete":
                raise _error("incomplete_media", "media reference status must be complete", f"{media_location}.status")
            overlap_disposition = media.get("overlap_disposition")
            if overlap_disposition is not None and overlap_disposition != "shared_source_bounded":
                raise _error("invalid_overlap_disposition", "overlap_disposition must be 'shared_source_bounded' when present", f"{media_location}.overlap_disposition")
            media_refs.append(MediaRef(episode_id, _text(_required(media, "feature_key", media_location), f"{media_location}.feature_key"), source.path, relative, source_hash, _integer(_required(media, "stream_index", media_location), f"{media_location}.stream_index"), start, end, clock_domain, mapping_version, scale, offset, start_time, Fraction(numerator, denominator), status, overlap_disposition, source.byte_size))

        episodes[episode_id] = EpisodeManifest(episode_id, raw_id, length, dataset_from, dataset_to, timestamp_from, timestamp_to, tasks, tuple(segments), tuple(media_refs))
    if tuple(episodes) != expected_ids:
        raise _error("episode_scope_mismatch", "episodes must exactly match scope.episode_ids in order", "episodes")
    _validate_segment_intervals(
        [segment for episode in episodes.values() for segment in episode.row_segments],
        "episodes.row_segments",
    )
    media_refs = [ref for episode in episodes.values() for ref in episode.media]
    for index, left in enumerate(media_refs):
        for right in media_refs[index + 1 :]:
            same_stream = (
                left.relative_path == right.relative_path
                and left.stream_index == right.stream_index
                and left.feature_key == right.feature_key
            )
            overlaps = max(left.from_timestamp, right.from_timestamp) < min(left.to_timestamp, right.to_timestamp)
            if same_stream and overlaps and (
                left.overlap_disposition != "shared_source_bounded"
                or right.overlap_disposition != "shared_source_bounded"
            ):
                raise _error(
                    "media_overlap_disposition_required",
                    "overlapping episode intervals on a shared media stream require shared_source_bounded disposition",
                    "episodes.media",
                )
    return QualityInputManifest(version, path.resolve(), dataset_root, run_id, artifact_hash, digest, guarantee, clock_domain, mapping_version, expected_ids, MappingProxyType(episodes), MappingProxyType(sources))


def iter_episode_segments(manifest: QualityInputManifest, episode_id: int) -> Iterator[EpisodeSegment]:
    """Yield every declared segment for an episode in manifest order."""
    try:
        episode = manifest.episodes[episode_id]
    except KeyError:
        raise _error("unknown_episode", f"episode {episode_id} is outside the verified scope") from None
    yield from episode.row_segments
