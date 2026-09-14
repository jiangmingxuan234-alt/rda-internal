"""Streaming, mergeable distribution summaries for quality mode."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from collections import defaultdict

@dataclass
class GroupedSummary:
    groups: dict[tuple, dict[str, Any]] = field(default_factory=dict)
    def merge(self, other: "GroupedSummary") -> "GroupedSummary":
        for key, value in other.groups.items():
            dst = self.groups.setdefault(key, {"episode_ids": set(), "episode_count": 0, "duration_sec": 0.0, "status_counts": defaultdict(int), "dimension_ranges": {}})
            dst["episode_ids"].update(value.get("episode_ids", set()))
            dst["duration_sec"] = max(dst.get("duration_sec", 0.0), value.get("duration_sec", 0.0)) if dst["episode_ids"] else value.get("duration_sec", 0.0)
            for state, count in value.get("status_counts", {}).items(): dst["status_counts"][state] += count
            for dim, bounds in value.get("dimension_ranges", {}).items():
                old = dst["dimension_ranges"].get(dim)
                dst["dimension_ranges"][dim] = [min(old[0], bounds[0]), max(old[1], bounds[1])] if old else list(bounds)
            dst["episode_count"] = len(dst["episode_ids"])
        return self
    def to_dict(self) -> dict[str, Any]:
        return {str(k): {**v, "episode_ids": sorted(v["episode_ids"]), "status_counts": dict(v["status_counts"])} for k, v in self.groups.items()}

def map_task(raw_task_index: Any, raw_task: Any, mapping: Mapping[str, Any] | None = None, version: str | None = None) -> dict[str, Any]:
    out = {"task_index": raw_task_index, "task": raw_task}
    if mapping and raw_task_index in mapping:
        out.update({"mapped_task": mapping[raw_task_index], "mapping_version": version})
    else:
        out.update({"mapped_task": None, "mapping_version": version})
    return out

def summarize_measurements(records: Iterable[Any], identities: Mapping[str, Mapping[str, Any]] | None = None) -> GroupedSummary:
    result = GroupedSummary(); identities = identities or {}
    for record in records:
        ident = identities.get(record.plan_unit_id, {})
        key = tuple((k, ident.get(k, "unknown")) for k in ("dataset", "episode_id", "task", "camera", "dimension_group", "metric_name", "algorithm_version", "effective_config_hash"))
        dst = result.groups.setdefault(key, {"episode_ids": set(), "episode_count": 0, "duration_sec": 0.0, "status_counts": defaultdict(int), "dimension_ranges": {}})
        ep = ident.get("episode_id", record.plan_unit_id)
        dst["episode_ids"].add(ep); dst["episode_count"] = len(dst["episode_ids"])
        dst["status_counts"][record.applicability.value] += 1
        value = record.values.get("duration_sec") if isinstance(record.values, Mapping) else None
        if isinstance(value, (int, float)): dst["duration_sec"] += float(value)
    return result

def merge_grouped_summaries(parts: Iterable[GroupedSummary]) -> GroupedSummary:
    out = GroupedSummary()
    for part in parts: out.merge(part)
    return out

# Short public names used by the quality API.
GroupSummary = GroupedSummary
summarize = summarize_measurements
merge_summaries = merge_grouped_summaries
