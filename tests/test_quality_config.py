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


def test_config_rejects_unknown_contract_version():
    value = _config()
    value["contract_version"] = 2
    with pytest.raises(ValueError, match="unsupported contract_version"):
        QualityConfig.from_mapping(value)


def test_config_rejects_float_contract_version_equal_to_supported_integer():
    value = _config()
    value["contract_version"] = 1.0
    with pytest.raises(ValueError, match="contract_version must be an integer"):
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


@pytest.mark.parametrize(
    "robot",
    [
        {"profile_id": 7, "cameras": ["front"]},
        {"profile_id": "robot-1", "cameras": "front"},
    ],
)
def test_declared_robot_profile_has_strict_identity_and_container_types(robot):
    value = _config()
    value["robot"] = robot
    with pytest.raises(ValueError, match="robot"):
        QualityConfig.from_mapping(value)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("policy_type", ""),
        ("padding", {"left": True}),
        ("required_modalities", ["observation.state", 7]),
    ],
)
def test_declared_training_profile_validates_identity_enums_and_members(field, invalid):
    value = _config()
    value["training"] = {
        "policy_type": "act",
        "observation_history": 1,
        "horizon": 16,
        "stride": 1,
        "padding": "none",
        "required_modalities": ["observation.state"],
    }
    value["training"][field] = invalid
    with pytest.raises(ValueError, match=field):
        QualityConfig.from_mapping(value)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [("rule_id", ""), ("version", ""), ("calibration_status", "invented")],
)
def test_rule_identity_and_calibration_status_are_strict(field, invalid):
    value = _config()
    value["quality"]["metrics"][0]["rule"] = {
        "rule_id": "idle-v1",
        "version": "1",
        "scope": {"tasks": ["pick"]},
        "thresholds": {"max": 0.9},
        "calibration_status": "uncalibrated",
        "provisional": False,
    }
    value["quality"]["metrics"][0]["rule"][field] = invalid
    with pytest.raises(ValueError, match=field):
        QualityConfig.from_mapping(value)


def test_calibrated_rule_requires_content_bound_calibration_identity():
    value = _config()
    rule = {
        "rule_id": "idle-v1",
        "version": "1",
        "scope": {"tasks": ["pick"]},
        "thresholds": {"max": 0.9},
        "calibration_status": "calibrated",
        "provisional": False,
    }
    value["quality"]["metrics"][0]["rule"] = rule
    with pytest.raises(ValueError, match="calibration"):
        QualityConfig.from_mapping(value)

    rule["calibration"] = {
        "calibration_id": "gold-v1",
        "calibration_hash": "sha256:" + "a" * 64,
    }
    config = QualityConfig.from_mapping(value)
    assert config.quality["metrics"][0]["rule"]["calibration"]["calibration_id"] == "gold-v1"


def test_structurally_complete_robot_profile_is_preserved():
    value = _config()
    value["robot"] = {
        "profile_id": "robot-1",
        "action_field": "action",
        "state_field": "observation.state",
        "action_representation": "absolute_position",
        "coordinate_frame": "base",
        "dimension_groups": {
            "arm": {"indices": [0, 1], "physical_quantity": "angle", "unit": "rad"}
        },
        "cameras": ["observation.images.front"],
    }
    config = QualityConfig.from_mapping(value)
    assert config.robot["profile_id"] == "robot-1"


def test_source_binding_is_content_addressed_and_changes_effective_hash():
    value = _config()
    value["robot"] = {
        "profile_id": "robot-1", "action_field": "action", "state_field": "state",
        "action_representation": "velocity", "coordinate_frame": "base",
        "dimension_groups": {"arm": {"indices": [0], "physical_quantity": "angle", "unit": "rad"}}, "cameras": [],
        "source_binding": {"profile_revision": "3", "profile_content_hash": "sha256:" + "a" * 64, "mapping_version": "v1", "mapping_hash": "sha256:" + "b" * 64},
    }
    bound = QualityConfig.from_mapping(value)
    value["robot"]["source_binding"]["mapping_hash"] = "sha256:" + "c" * 64
    assert bound.effective_config_hash != QualityConfig.from_mapping(value).effective_config_hash


@pytest.mark.parametrize("field", ["reference_set", "sampling", "resource_budget"])
def test_quality_profile_containers_must_be_mappings(field):
    value = _config()
    value["quality"][field] = "invalid"
    with pytest.raises(ValueError, match=field):
        QualityConfig.from_mapping(value)


def test_rule_scope_members_are_strict_and_all_is_exclusive():
    value = _config()
    value["quality"]["metrics"][0]["rule"] = {
        "rule_id": "idle-v1",
        "version": "1",
        "scope": {"tasks": "pick"},
        "thresholds": {"max": 0.9},
    }
    with pytest.raises(ValueError, match="scope.tasks"):
        QualityConfig.from_mapping(value)

    value["quality"]["metrics"][0]["rule"]["scope"] = {
        "all": True,
        "tasks": ["pick"],
    }
    with pytest.raises(ValueError, match="scope.all"):
        QualityConfig.from_mapping(value)


def test_robot_dimension_group_members_are_structural():
    value = _config()
    value["robot"] = {
        "profile_id": "robot-1",
        "action_field": "action",
        "state_field": "observation.state",
        "action_representation": "absolute_position",
        "coordinate_frame": "base",
        "dimension_groups": {"arm": {}},
        "cameras": ["observation.images.front"],
    }
    with pytest.raises(ValueError, match="dimension_groups.arm"):
        QualityConfig.from_mapping(value)
