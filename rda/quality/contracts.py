"""Immutable, JSON-safe contracts for RDA quality mode.

These types are intentionally separate from :mod:`rda.metrics.base`.  The
legacy metric result conflates compatibility verdicts with execution state;
quality mode records applicability, execution and assessment independently.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping


JSONScalar = None | bool | int | float | str
# Recursive aliases are not evaluated lazily on Python 3.10.  Runtime JSON
# validation is performed by ``freeze_json``; ``Any`` keeps this module
# importable on every supported Python version.
JSONValue = Any


class FrozenDict(dict):
    """A JSON-encoder-compatible dict that cannot be changed."""

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("frozen mapping cannot be modified")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


def freeze_json(value: Any, *, path: str = "value") -> JSONValue:
    """Validate and recursively freeze a value from the JSON data model."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        if value == 0:
            return 0
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} has a non-string mapping key")
            frozen[key] = freeze_json(item, path=f"{path}.{key}")
        return FrozenDict(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(
            freeze_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise TypeError(f"{path} is not JSON-safe: {type(value).__name__}")


def thaw_json(value: JSONValue) -> Any:
    """Return ordinary JSON containers suitable for serialization."""
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value


class Applicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class ExecutionState(str, Enum):
    COMPUTED = "COMPUTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Assessment(str, Enum):
    UNASSESSED = "UNASSESSED"
    PASS = "PASS"
    REVIEW = "REVIEW"
    EXCLUDE_CANDIDATE = "EXCLUDE_CANDIDATE"


class QualityRunState(str, Enum):
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class MeasurementRecord:
    """An immutable calculated fact, intentionally without an assessment."""
    plan_unit_id: str
    metric_name: str
    algorithm_version: str
    effective_config_hash: str
    applicability: Applicability
    coverage: Mapping[str, Any]
    values: Mapping[str, Any]
    evidence: Iterable[Mapping[str, Any]]

    def __post_init__(self) -> None:
        for name in ("plan_unit_id", "metric_name", "algorithm_version", "effective_config_hash"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not _SHA256_PATTERN.fullmatch(self.effective_config_hash):
            raise ValueError("effective_config_hash must be a sha256 content hash")
        object.__setattr__(self, "applicability", Applicability(self.applicability))
        coverage = freeze_json(self.coverage, path="coverage")
        values = freeze_json(self.values, path="values")
        evidence = freeze_json(tuple(self.evidence), path="evidence")
        if not isinstance(coverage, FrozenDict) or not isinstance(values, FrozenDict):
            raise TypeError("coverage and values must be mappings")
        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "evidence", evidence)

    def to_dict(self) -> dict[str, Any]:
        return {"plan_unit_id": self.plan_unit_id, "metric_name": self.metric_name,
                "algorithm_version": self.algorithm_version, "effective_config_hash": self.effective_config_hash,
                "applicability": self.applicability.value, "coverage": thaw_json(self.coverage),
                "values": thaw_json(self.values), "evidence": thaw_json(self.evidence)}


@dataclass(frozen=True)
class QualityRequest:
    dataset_root: Path
    input_manifest: Path
    config: Mapping[str, Any]
    output_root: Path
    run_id: str
    resume: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        for name in ("dataset_root", "input_manifest", "output_root"):
            value = getattr(self, name)
            if not isinstance(value, Path):
                raise TypeError(f"{name} must be a pathlib.Path")
        object.__setattr__(self, "config", freeze_json(self.config, path="config"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_root": str(self.dataset_root),
            "input_manifest": str(self.input_manifest),
            "config": thaw_json(self.config),
            "output_root": str(self.output_root),
            "run_id": self.run_id,
            "resume": self.resume,
        }


@dataclass(frozen=True)
class UnitResult:
    plan_unit_id: str
    applicability: Applicability
    execution_state: ExecutionState
    assessment: Assessment
    coverage: Mapping[str, Any]
    measurement: Mapping[str, Any]
    evidence: Iterable[Mapping[str, Any]]
    reason_codes: Iterable[str]
    rule_id: str | None = None
    rule_version: str | None = None
    rule_source: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan_unit_id, str) or not self.plan_unit_id.strip():
            raise ValueError("plan_unit_id must be a non-empty string")
        for name, enum_type in (
            ("applicability", Applicability),
            ("execution_state", ExecutionState),
            ("assessment", Assessment),
        ):
            value = getattr(self, name)
            try:
                value = enum_type(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid {name}: {value!r}") from exc
            object.__setattr__(self, name, value)

        coverage = freeze_json(self.coverage, path="coverage")
        measurement = freeze_json(self.measurement, path="measurement")
        evidence = freeze_json(tuple(self.evidence), path="evidence")
        reason_codes = tuple(self.reason_codes)
        rule_source = (
            None
            if self.rule_source is None
            else freeze_json(self.rule_source, path="rule_source")
        )
        if not isinstance(coverage, FrozenDict):
            raise TypeError("coverage must be a mapping")
        if not isinstance(measurement, FrozenDict):
            raise TypeError("measurement must be a mapping")
        if any(not isinstance(code, str) or not code.strip() for code in reason_codes):
            raise ValueError("reason_codes must contain non-empty strings")

        if self.execution_state is not ExecutionState.COMPUTED and measurement:
            raise ValueError("measurement is only valid for COMPUTED results")
        if self.execution_state is not ExecutionState.COMPUTED and not reason_codes:
            raise ValueError("non-computed results require reason_codes")
        if self.applicability is not Applicability.APPLICABLE and not reason_codes:
            raise ValueError("non-applicable or unknown results require reason_codes")
        if self.execution_state is not ExecutionState.COMPUTED and self.assessment is not Assessment.UNASSESSED:
            raise ValueError("non-computed results must be UNASSESSED")
        if self.assessment is not Assessment.UNASSESSED and (
            not isinstance(self.rule_version, str) or not self.rule_version.strip()
        ):
            raise ValueError("assessed results require rule_version")
        if self.assessment is not Assessment.UNASSESSED and (
            not isinstance(self.rule_id, str) or not self.rule_id.strip()
        ):
            raise ValueError("assessed results require rule_id")
        if self.applicability is not Applicability.APPLICABLE and self.assessment is not Assessment.UNASSESSED:
            raise ValueError("non-applicable or unknown results must be UNASSESSED")
        if self.applicability is Applicability.NOT_APPLICABLE and measurement:
            raise ValueError("NOT_APPLICABLE results cannot publish measurement")
        source = rule_source if isinstance(rule_source, Mapping) else {}
        if self.assessment is Assessment.PASS:
            _validate_assessed_coverage(coverage)
            _validate_calibrated_rule_source(source, self.rule_id, self.rule_version)
        if self.assessment is Assessment.EXCLUDE_CANDIDATE:
            _validate_assessed_coverage(coverage)
            _validate_calibrated_rule_source(source, self.rule_id, self.rule_version)

        object.__setattr__(self, "coverage", coverage)
        object.__setattr__(self, "measurement", measurement)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "rule_source", rule_source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_unit_id": self.plan_unit_id,
            "applicability": self.applicability.value,
            "execution_state": self.execution_state.value,
            "assessment": self.assessment.value,
            "coverage": thaw_json(self.coverage),
            "measurement": thaw_json(self.measurement),
            "evidence": thaw_json(self.evidence),
            "reason_codes": list(self.reason_codes),
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "rule_source": thaw_json(self.rule_source),
        }


_CALIBRATED_SOURCE_FIELDS = {
    "kind",
    "rule_id",
    "rule_version",
    "calibration_id",
    "calibration_hash",
    # Optional Task1 source identity fields used by quality mode.
    "profile_revision", "profile_content_hash", "mapping_version", "mapping_hash",
    "task", "camera", "dimensions", "units",
}
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _validate_assessed_coverage(coverage: Mapping[str, Any]) -> None:
    required = {
        "planned_samples",
        "attempted_samples",
        "computed_samples",
        "sampling_complete",
    }
    missing = sorted(required - set(coverage))
    if missing:
        raise ValueError(f"assessed result coverage missing fields: {missing}")
    planned = coverage["planned_samples"]
    attempted = coverage["attempted_samples"]
    computed = coverage["computed_samples"]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (planned, attempted, computed)
    ):
        raise ValueError("assessed result coverage counts must be non-negative integers")
    if planned == 0:
        raise ValueError("assessed result coverage requires planned_samples > 0")
    if coverage["sampling_complete"] is not True:
        raise ValueError("partial coverage cannot produce calibrated assessment")
    if not planned == attempted == computed:
        raise ValueError("partial coverage cannot produce calibrated assessment")


def _validate_calibrated_rule_source(
    source: Mapping[str, Any],
    rule_id: str | None,
    rule_version: str | None,
) -> None:
    missing = sorted(_CALIBRATED_SOURCE_FIELDS - set(source))
    unknown = sorted(set(source) - _CALIBRATED_SOURCE_FIELDS)
    if missing or unknown:
        raise ValueError(
            "calibrated rule_source requires exact provenance fields; "
            f"missing={missing}, unknown={unknown}"
        )
    if source["kind"] != "calibrated_rule":
        raise ValueError("calibrated rule_source.kind must be calibrated_rule")
    if source["rule_id"] != rule_id:
        raise ValueError("calibrated rule_source.rule_id must match result rule_id")
    if source["rule_version"] != rule_version:
        raise ValueError(
            "calibrated rule_source.rule_version must match result rule_version"
        )
    if not isinstance(source["calibration_id"], str) or not source["calibration_id"].strip():
        raise ValueError("calibrated rule_source.calibration_id must be non-empty")
    calibration_hash = source["calibration_hash"]
    if not isinstance(calibration_hash, str) or not _SHA256_PATTERN.fullmatch(calibration_hash):
        raise ValueError("calibrated rule_source.calibration_hash must be a sha256 content hash")
