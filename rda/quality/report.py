"""Quality-mode report and output bundle.

This layer serializes RDA advice and evidence. Procurement and training
decisions remain the responsibility of the company core.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import UnitResult


def _row(result: UnitResult) -> dict[str, Any]:
    return result.to_dict()


def build_quality_report(results: Iterable[UnitResult], *, run_id: str | None = None,
                         run_state: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rows = [_row(r) for r in results]
    counts = {"total": len(rows), "pass": 0, "review": 0,
              "exclude_candidate": 0, "unassessed": 0, "failed": 0, "skipped": 0}
    for row in rows:
        assessment = row["assessment"].lower()
        if assessment in counts:
            counts[assessment] += 1
        if row["execution_state"] in {"FAILED", "CANCELLED"}:
            counts["failed"] += 1
        elif row["execution_state"] == "SKIPPED":
            counts["skipped"] += 1
    report: dict[str, Any] = {
        "schema_version": 1,
        "report_type": "rda_quality_advice",
        "run_id": run_id,
        "run_state": run_state,
        "summary": counts,
        "units": rows,
        "decision_authority": "company_core",
        "advice_artifact": "quality_advice.jsonl",
    }
    if metadata:
        report["metadata"] = dict(metadata)
    return report


def write_quality_bundle(output_root: Path, run_id: str, results: Iterable[UnitResult], *,
                         run_state: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Path]:
    """Write a deterministic, inspectable quality advice bundle."""
    bundle = Path(output_root) / run_id
    bundle.mkdir(parents=True, exist_ok=True)
    rows = list(results)
    advice = bundle / "quality_advice.jsonl"
    advice.write_text("".join(json.dumps(_row(r), sort_keys=True, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    report = bundle / "report.json"
    report.write_text(json.dumps(build_quality_report(rows, run_id=run_id, run_state=run_state, metadata=metadata),
                                  sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = {}
    for path in (advice, report):
        checksums[path.name] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    checksum_path = bundle / "checksums.json"
    checksum_path.write_text(json.dumps(checksums, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"bundle": bundle, "advice": advice, "report": report, "checksums": checksum_path}
