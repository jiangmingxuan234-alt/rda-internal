"""Behavior probes for source identity and independently verified semantics."""
from copy import deepcopy
import hashlib
import json
import pytest
from rda.quality.config import QualityConfig


def profile_facts():
    return {"status": "complete", "raw_sha256": "a" * 64, "schema_version": 1,
            "profile_id": "robot-1", "revision": "3", "robot_type": "synthetic",
            "signals": [{"name": kind, "role": kind, "source_field": field,
                         "dtype": "float32", "shape": [2], "unit": "rad", "quantity": "angle",
                         "reference_frame": "base", "joint_names": ["j0", "j1"]}
                        for kind, field in (("action", "action"), ("state", "state"))]}


def bound_robot():
    robot = {"profile_id": "robot-1", "action_field": "action", "state_field": "state",
             "action_representation": "absolute_position", "coordinate_frame": "base",
             "dimension_groups": {"arm": {"indices": [0, 1], "physical_quantity": "angle", "unit": "rad"}},
             "cameras": [], "signal_mappings": {
                 kind: {"signal_name": kind, "groups": {"arm": {"indices": [0, 1],
                        "physical_quantity": "angle", "unit": "rad", "reference_frame": "base",
                        "representation": "absolute_position"}}} for kind in ("action", "state")},
             "source_binding": {"profile_revision": "3", "profile_content_hash": "sha256:" + "a" * 64,
                                "mapping_version": "v1", "source_profile": profile_facts()}}
    seal_mapping(robot)
    return robot


def seal_mapping(robot):
    # Independent contract encoding, deliberately not production hash helper.
    payload = {"mapping_version": "v1", "robot": {key: value for key, value in robot.items() if key != "source_binding"}}
    robot["source_binding"]["mapping_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def config_for(robot):
    return QualityConfig.from_mapping({"contract_version": 1, "robot": robot, "quality": {"metrics": []}})


def test_canonical_mapping_changes_require_matching_hash():
    robot = bound_robot()
    config_for(robot)
    robot["signal_mappings"]["action"]["groups"]["arm"]["indices"] = [1]
    with pytest.raises(ValueError, match="mapping_hash"):
        config_for(robot)


def test_config_facts_alone_never_authorize_semantics_and_independent_facts_must_match():
    from rda.quality import semantic_binding
    robot = bound_robot()
    config = config_for(robot)
    assert semantic_binding.validate_semantic_binding(config.robot) is None
    verified = semantic_binding.validate_semantic_binding(config.robot, profile_facts())
    assert verified["sources"]["state"]["dimensions"]["0"]["unit"] == "rad"
    changed = profile_facts()
    changed["signals"][0]["joint_names"] = ["different", "j1"]
    with pytest.raises(ValueError, match="source_profile"):
        semantic_binding.validate_semantic_binding(config.robot, changed)


@pytest.mark.parametrize("change", [
    lambda r: r["signal_mappings"]["action"].update(signal_name="state"),
    lambda r: r["signal_mappings"]["state"]["groups"]["arm"].update(indices=[2]),
    lambda r: r["signal_mappings"]["state"]["groups"].update(other=deepcopy(r["signal_mappings"]["state"]["groups"]["arm"])),
    lambda r: r["signal_mappings"]["state"]["groups"]["arm"].update(unit="m"),
    lambda r: r["signal_mappings"]["state"]["groups"]["arm"].update(reference_frame="tool"),
    lambda r: r["signal_mappings"]["state"]["groups"]["arm"].update(representation="velocity"),
    lambda r: r["signal_mappings"]["action"]["groups"]["arm"].update(periodic_dimensions=[{"index": 0, "period": 0}]),
    lambda r: r["signal_mappings"]["action"]["groups"]["arm"].update(discrete_dimensions=[0]),
])
def test_conflicting_or_unsupported_mapping_is_rejected(change):
    robot = bound_robot()
    config_for(robot)
    change(robot)
    seal_mapping(robot)
    with pytest.raises(ValueError):
        config_for(robot)


def test_original_profile_identity_cannot_be_relabelled():
    robot = bound_robot()
    robot["source_binding"]["profile_revision"] = "4"
    with pytest.raises(ValueError, match="revision"):
        config_for(robot)


def test_source_specific_periods_and_discrete_representation_are_explicit():
    robot = bound_robot()
    robot["signal_mappings"]["action"]["groups"]["arm"]["periodic_dimensions"] = [{"index": 0, "period": 6}]
    robot["signal_mappings"]["state"]["groups"]["arm"]["periodic_dimensions"] = [{"index": 1, "period": 7}]
    seal_mapping(robot)
    from rda.quality.semantic_binding import validate_semantic_binding
    views = validate_semantic_binding(config_for(robot).robot, profile_facts())["sources"]
    assert views["action"]["dimensions"]["0"]["period"] == 6
    assert views["state"]["dimensions"]["0"]["period"] is None
    assert views["state"]["dimensions"]["1"]["period"] == 7
    profile = robot["source_binding"]["source_profile"]
    for signal in profile["signals"]:
        signal.update(quantity="discrete", unit="bool", dtype="bool")
    for mapping in robot["signal_mappings"].values():
        mapping["groups"]["arm"].update(physical_quantity="discrete", unit="bool", representation="discrete")
        mapping["groups"]["arm"].pop("periodic_dimensions")
    seal_mapping(robot)
    views = validate_semantic_binding(config_for(robot).robot, profile)["sources"]
    assert all(d["discrete"] for source in views.values() for d in source["dimensions"].values())


@pytest.mark.parametrize("field,value", [("mapping_version", "v2"), ("profile_content_hash", "sha256:" + "b" * 64)])
def test_unknown_mapping_version_or_false_original_hash_is_rejected(field, value):
    robot = bound_robot()
    robot["source_binding"][field] = value
    with pytest.raises(ValueError):
        config_for(robot)


@pytest.mark.parametrize("mutation", [
    lambda r: r["signal_mappings"]["action"].update(signal_name=[]),
    lambda r: r["signal_mappings"]["action"]["groups"]["arm"].update(representation=[]),
    lambda r: r["source_binding"]["source_profile"]["signals"][0].update(dtype="string"),
    lambda r: r["signal_mappings"]["action"]["groups"]["arm"].update(indices=[True]),
])
def test_malformed_semantic_mapping_raises_input_value_error(mutation):
    robot = bound_robot()
    mutation(robot)
    seal_mapping(robot)
    with pytest.raises(ValueError):
        config_for(robot)
