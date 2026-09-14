import json
from pathlib import Path

import pytest

from rda.quality.evidence import to_fiftyone_records
from rda.quality.core_review import AppendOnlyReviewClient, new_review_event


def test_evidence_projection_from_report_is_ui_friendly_and_decision_free():
    records = to_fiftyone_records({"units": [{
        "plan_unit_id": "ep1:m1", "assessment": "REVIEW",
        "applicability": "APPLICABLE", "execution_state": "COMPUTED",
        "measurement": {"value": 1}, "evidence": [{"locator": {"episode": 1}}],
        "reason_codes": ["THRESHOLD"]
    }]}, run_id="run1")
    assert records[0].to_dict()["sample_id"] == "ep1:m1"
    assert records[0].to_dict()["run_id"] == "run1"
    assert "procurement_decision" not in records[0].to_dict()


def test_evidence_rejects_decision_fields():
    with pytest.raises(ValueError):
        to_fiftyone_records([{"plan_unit_id": "x", "procurement_decision": "ACCEPT"}])


def test_review_client_submits_append_only_event_without_persistence():
    sent = []
    client = AppendOnlyReviewClient(lambda event: sent.append(event) or {"accepted": True})
    event = new_review_event("r", "ep1", "alice", "ANNOTATION_ADDED", {"label": "blur"})
    assert client.submit(event) == {"accepted": True}
    assert sent[0]["event_id"] == event.event_id
    assert "procurement_decision" not in sent[0]


def test_review_client_rejects_final_decision_payload():
    client = AppendOnlyReviewClient(lambda event: event)
    event = new_review_event("r", "ep1", "alice", "DECISION", {"training_selection_decision": "USE"})
    with pytest.raises(ValueError):
        client.submit(event)
