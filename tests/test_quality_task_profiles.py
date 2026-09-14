import copy
import json
from pathlib import Path

import pytest

from rda.quality.config import QualityConfig
from rda.quality.task_profiles import merge_task_profile


BASE = {
    "contract_version": 1,
    "quality": {
        "metrics": [
            {
                "name": "action_discontinuity",
                "role": "required_for_advice",
                "parameters": {"mad_tolerance": 5.0},
                "rule": {
                    "rule_id": "action-v1",
                    "version": "1",
                    "scope": {"all": True},
                    "thresholds": {"value": 0.2},
                    "provisional": True,
                },
            },
            {
                "name": "idle_ratio",
                "role": "informational",
                "parameters": {"activity_epsilon": 0.01},
            },
        ]
    },
}


def test_task_override_changes_only_metric_parameters_and_keeps_base_immutable():
    original = copy.deepcopy(BASE)
    merged = merge_task_profile(
        BASE,
        {
            "task_id": "pusht",
            "metrics": {"idle_ratio": {"parameters": {"activity_epsilon": 17.8}}},
        },
    )
    assert merged["quality"]["metrics"][1]["parameters"]["activity_epsilon"] == 17.8
    assert merged["quality"]["metrics"][0] == BASE["quality"]["metrics"][0]
    assert BASE == original


def test_unknown_metric_and_field_are_rejected():
    with pytest.raises(ValueError, match="unknown metric"):
        merge_task_profile(BASE, {"task_id": "x", "metrics": {"missing": {}}})
    with pytest.raises(ValueError, match="unknown task profile field"):
        merge_task_profile(BASE, {"task_id": "x", "bad": 1})


def test_duplicate_base_metrics_are_rejected():
    bad = copy.deepcopy(BASE)
    bad["quality"]["metrics"].append(copy.deepcopy(bad["quality"]["metrics"][0]))
    with pytest.raises(ValueError, match="duplicate metric"):
        merge_task_profile(bad, {"task_id": "x"})


def test_rule_thresholds_and_training_are_overridden():
    base = copy.deepcopy(BASE)
    base["training"] = {
        "policy_type": "act",
        "observation_history": 1,
        "horizon": 4,
        "stride": 1,
        "padding": "none",
        "required_modalities": ["observation.state"],
    }
    merged = merge_task_profile(
        base,
        {
            "task_id": "pick",
            "metrics": {
                "action_discontinuity": {
                    "rule": {"thresholds": {"value": 0.3}}
                }
            },
            "training": {"horizon": 10},
        },
    )
    action = merged["quality"]["metrics"][0]
    assert action["rule"]["thresholds"] == {"value": 0.3}
    assert merged["training"]["horizon"] == 10
    assert QualityConfig.from_mapping(merged).effective_config_hash.startswith("sha256:")


def test_checked_in_pusht_profile_merges_and_validates():
    project_root = Path(__file__).resolve().parents[5]
    base = json.loads((project_root / "configs/rda/base-quality.json").read_text(encoding="utf-8"))
    task = json.loads((project_root / "configs/rda/tasks/pusht.json").read_text(encoding="utf-8"))
    merged = merge_task_profile(base, task)
    config = QualityConfig.from_mapping(merged)
    assert config.effective_config_hash.startswith("sha256:")
    assert config.effective_config["quality"]["reference_set"]["task_profile_id"] == "pusht"
