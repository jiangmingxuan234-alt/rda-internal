"""Evidence-only projections for FiftyOne or other review UIs.

FiftyOne is deliberately an optional consumer.  This module never imports it
and never persists a procurement or training decision.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


_FORBIDDEN = {"procurement_decision", "training_selection_decision", "training_manifest"}


@dataclass(frozen=True)
class EvidenceRecord:
    sample_id: str
    run_id: str | None
    episode_id: str | int | None
    advice: str
    measurement: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    fields: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"sample_id": self.sample_id, "run_id": self.run_id,
                "episode_id": self.episode_id, "rda_advice": self.advice,
                "measurement": dict(self.measurement), "evidence": [dict(x) for x in self.evidence],
                **dict(self.fields)}


def load_quality_advice(source: str | Path | Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Load report units or JSONL advice without requiring FiftyOne."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        source = json.loads(text)
    if isinstance(source, Mapping):
        source = source.get("units", source.get("records", []))
    return [dict(row) for row in source]


def to_fiftyone_records(source: Any, *, run_id: str | None = None) -> list[EvidenceRecord]:
    rows = load_quality_advice(source)
    output: list[EvidenceRecord] = []
    for row in rows:
        sample_id = row.get("plan_unit_id") or row.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id.strip():
            raise ValueError("quality advice row requires plan_unit_id/sample_id")
        if _FORBIDDEN.intersection(row):
            raise ValueError("decision fields are not allowed in evidence projection")
        evidence = tuple(x for x in row.get("evidence", ()) if isinstance(x, Mapping))
        measurement = row.get("measurement", {})
        if not isinstance(measurement, Mapping):
            raise ValueError("measurement must be a mapping")
        # Keep rule provenance and other review evidence available to the UI,
        # while filtering only fields that would turn this projection into a
        # second decision store.
        fields = {key: value for key, value in row.items()
                  if key not in {"plan_unit_id", "sample_id", "run_id", "episode_id",
                                 "measurement", "evidence", *_FORBIDDEN}}
        fields["reason_codes"] = list(row.get("reason_codes", ()))
        output.append(EvidenceRecord(sample_id, row.get("run_id", run_id),
                                     row.get("episode_id"), row.get("assessment", "UNASSESSED"),
                                     measurement, evidence, fields))
    return output
