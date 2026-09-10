from __future__ import annotations

import json

import pytest

from rda.quality.config import QualityConfig


def _config():
    return {
        "contract_version": 1,
        "quality": {
            "metrics": [
                {
                    "name": "idle_ratio",
                    "role": "informational",
                    "parameters": {"epsilon": 0.01},
                }
            ]
        },
    }


def test_config_requires_contract_version():
    value = _config()
    del value["contract_version"]
    with pytest.raises(ValueError, match="contract_version"):
        QualityConfig.from_mapping(value)


def test_config_rejects_unknown_metric():
    value = _config()
    value["quality"]["metrics"][0]["name"] = "made_up_metric"
    with pytest.raises(ValueError, match="unknown metric"):
        QualityConfig.from_mapping(value)


def test_quality_rule_requires_nonempty_scope():
    value = _config()
    value["quality"]["metrics"][0]["rule"] = {
        "rule_id": "idle-v1",
        "version": "1",
        "scope": {},
        "thresholds": {"max": 0.9},
    }
    with pytest.raises(ValueError, match="scope"):
        QualityConfig.from_mapping(value)


@pytest.mark.parametrize("missing", ["horizon", "stride"])
def test_declared_training_profile_requires_horizon_and_stride(missing):
    value = _config()
    value["training"] = {
        "policy_type": "act",
        "observation_history": 1,
        "horizon": 16,
        "stride": 1,
        "padding": "none",
        "required_modalities": ["observation.state"],
    }
    del value["training"][missing]
    with pytest.raises(ValueError, match=missing):
        QualityConfig.from_mapping(value)


def test_missing_robot_and_training_profiles_are_preserved():
    config = QualityConfig.from_mapping(_config())
    assert config.robot is None
    assert config.training is None
    assert "robot" not in config.effective_config
    assert "training" not in config.effective_config


def test_key_order_does_not_change_config_hash():
    first = _config()
    second = json.loads(json.dumps(first))
    second = {
        "quality": {
            "metrics": [
                {
                    "parameters": {"epsilon": 0.0100},
                    "role": "informational",
                    "name": "idle_ratio",
                }
            ]
        },
        "contract_version": 1,
    }
    assert QualityConfig.from_mapping(first).requested_config_hash == (
        QualityConfig.from_mapping(second).requested_config_hash
    )


def test_unknown_fields_and_conflicting_metric_roles_are_rejected():
    value = _config()
    value["unexpected"] = True
    with pytest.raises(ValueError, match="unknown field"):
        QualityConfig.from_mapping(value)

    value = _config()
    value["quality"]["metrics"].append(
        {"name": "idle_ratio", "role": "required_for_advice", "parameters": {}}
    )
    with pytest.raises(ValueError, match="duplicate metric"):
        QualityConfig.from_mapping(value)


def test_rule_cannot_be_both_calibrated_and_provisional():
    value = _config()
    value["quality"]["metrics"][0]["rule"] = {
        "rule_id": "idle-v1",
        "version": "1",
        "scope": {"tasks": ["pick"]},
        "thresholds": {"max": 0.9},
        "calibration_status": "calibrated",
        "provisional": True,
    }
    with pytest.raises(ValueError, match="provisional"):
        QualityConfig.from_mapping(value)
