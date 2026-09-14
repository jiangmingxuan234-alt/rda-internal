"""Append-only review-event client for the company core.

The client submits events to an injected transport and retains no decision
state.  A production transport is responsible for durable, authoritative
procurement/training decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from .evidence import _FORBIDDEN


@dataclass(frozen=True)
class ReviewEvent:
    run_id: str
    sample_id: str
    reviewer_id: str
    event_type: str
    payload: Mapping[str, Any]
    event_id: str = ""
    occurred_at: str = ""
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "event_id": self.event_id,
                "occurred_at": self.occurred_at, "run_id": self.run_id,
                "sample_id": self.sample_id, "reviewer_id": self.reviewer_id,
                "event_type": self.event_type, "payload": dict(self.payload)}


class AppendOnlyReviewClient:
    def __init__(self, transport: Callable[[Mapping[str, Any]], Any]):
        self._transport = transport

    def submit(self, event: ReviewEvent) -> Any:
        if event.schema_version != 1:
            raise ValueError("unsupported review event schema_version")
        if not all(isinstance(x, str) and x.strip() for x in (event.run_id, event.sample_id, event.reviewer_id, event.event_type)):
            raise ValueError("review event identity fields must be non-empty")
        if _FORBIDDEN.intersection(event.payload):
            raise ValueError("final company-core decisions cannot be stored in RDA events")
        return self._transport(event.to_dict())


def new_review_event(run_id: str, sample_id: str, reviewer_id: str, event_type: str,
                     payload: Mapping[str, Any], *, event_id: str | None = None,
                     occurred_at: str | None = None) -> ReviewEvent:
    return ReviewEvent(run_id, sample_id, reviewer_id, event_type, dict(payload),
                       event_id or str(uuid4()), occurred_at or datetime.now(timezone.utc).isoformat())
