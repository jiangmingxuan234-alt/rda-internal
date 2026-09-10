# Quality semantic profile binding v1

RDA validates a derived mapping; Robovet owns the original robot facts. No
configuration hash establishes provenance by itself. A missing robot or missing
source binding remains valid for raw per-field/per-dimension observations;
physical semantics remain `UNKNOWN`/`UNASSESSED`.

A bound robot retains the existing required robot keys and adds:

```json
{
  "source_binding": {
    "profile_revision": "3",
    "profile_content_hash": "sha256:<64 lowercase hex>",
    "mapping_version": "v1",
    "mapping_hash": "sha256:<64 lowercase hex>",
    "source_profile": {
      "status": "complete",
      "raw_sha256": "<64 lowercase hex, without prefix>",
      "schema_version": 1,
      "profile_id": "robot-1",
      "revision": "3",
      "robot_type": "declared original robot type",
      "signals": [
        {
          "name": "joint_command",
          "role": "action",
          "source_field": "action",
          "dtype": "float32",
          "shape": [2],
          "unit": "rad",
          "quantity": "angle",
          "reference_frame": "base",
          "joint_names": ["j0", "j1"]
        },
        {
          "name": "joint_state",
          "role": "state",
          "source_field": "observation.state",
          "dtype": "float32",
          "shape": [2],
          "unit": "rad",
          "quantity": "angle",
          "reference_frame": "base"
        }
      ]
    }
  },
  "signal_mappings": {
    "action": {
      "signal_name": "joint_command",
      "groups": {
        "arm": {
          "indices": [0, 1],
          "physical_quantity": "angle",
          "unit": "rad",
          "reference_frame": "base",
          "representation": "absolute_position",
          "periodic_dimensions": [{"index": 0, "period": 6.283185307179586}]
        }
      }
    },
    "state": {
      "signal_name": "joint_state",
      "groups": {
        "arm": {
          "indices": [0, 1],
          "physical_quantity": "angle",
          "unit": "rad",
          "reference_frame": "base",
          "representation": "absolute_position"
        }
      }
    }
  }
}
```

`source_profile` is the complete original serialized Task 13 `robot_profile`.
Signal order and all original optional `joint_names`, `min`, `max` are retained.
No role, field, dtype, shape, quantity, unit, frame, name or bound is inferred or
renamed. Unknown extra profile fields are rejected at this v1 boundary. The
original profile ID/revision and raw hash must agree with the parent robot and
binding. Producer raw hashes use bare hex; only RDA's content hash uses `sha256:`.

`mapping_hash(robot)` hashes UTF-8 JSON of exactly this noncircular payload:

```text
{"mapping_version": robot.source_binding.mapping_version,
 "robot": all robot fields except source_binding}
```

First recursively normalize JSON using the same numeric normalization as the
effective config: finite integral floats become integers, negative zero becomes
zero, and tuples become arrays. Encode with sorted object keys,
`ensure_ascii=False`, `allow_nan=False`, separators `(',', ':')`. Prefix the
SHA-256 hex digest with `sha256:`. Array order is significant. The hash excludes
itself and the entire source binding. The effective config hash includes the
complete source binding and derived mapping, so it includes both identities.
A mapping mutation without updating its canonical hash is rejected.

Both action and state must select one original signal with the matching role
and exact configured source field. Groups have unique nonnegative flattened
indices within the original signal shape; overlapping groups are rejected.
Partial mappings are allowed, but unmapped dimensions authorize only raw facts.
Group quantity/unit/frame must exactly match that original signal. Each group
has its own representation. Global periodic/discrete annotations are rejected
for bound robots because their meaning across independent sources is ambiguous.
The legacy top-level `dimension_groups` and `action_representation` stay in the
config/hash for compatibility; bound calculations use `signal_mappings`.

Supported v1 representation/quantity/unit combinations are:

| Representation | Quantity | Unit |
| --- | --- | --- |
| absolute_position, delta_position | angle | rad, deg |
| absolute_position, delta_position | position, length | m, mm |
| velocity | angular_velocity | rad/s, deg/s |
| velocity | velocity, linear_velocity | m/s, mm/s |
| torque | torque | N*m, Nm |
| force | force | N |
| discrete | discrete, boolean | 1, bool |

Other combinations are unsupported and cannot be used as a bound mapping.
Continuous groups require numeric integer or floating dtype; discrete groups
require boolean or integer dtype. Runtime consumers must also compare actual
array shape/dtype with the preserved original signal. Torque/force observations
do not establish physical activity. Discrete representation applies to the
entire group: count values, transitions and runs; never continuous norms or
derivatives. Optional `discrete_dimensions` must list every group index and is
accepted only for discrete representation. Periodic dimensions must be unique
group members in angle position/increment groups with an explicitly declared
finite positive period; there is no default period or implicit unit conversion.

`validate_robot_mapping(robot)` checks configuration consistency only.
`validate_semantic_binding(robot, producer_profile)` additionally compares the
entire source profile to independently bound producer facts, returning `None`
when either binding is absent. A complete mismatch raises `ValueError`; missing
or incomplete producer profiles authorize no semantic claims. Its immutable
result has `source_binding` plus `sources.action/state`, each with the original
`signal`, `source_field` and a `dimensions` mapping keyed by decimal index. Each
dimension retains group, index, representation, quantity, unit, frame, discrete
flag and declared period (or null). Applicable measurements retain the source
binding and producer artifact reference in evidence.

The independently supplied profile comes from verified manifest inputs, never
from copying config fields into a plan. Adapter 8 must copy the exact sealed
Task 13 artifact bytes into a separate read-only input staging area; the
manifest loader verifies and retains those facts as described in
[quality-input-manifest-v1.md](quality-input-manifest-v1.md). Task 6 must carry the
verified `manifest.robot_profile` and producer artifact hash into plan input
references and revalidate that staged artifact before publication. Synthetic
unit fixtures may explicitly supply synthetic producer facts to the helper;
this does not claim real robot provenance or calibration.
