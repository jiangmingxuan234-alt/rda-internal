# Quality semantic profile schema v1

`robot.source_binding` is optional provenance for RDA quality measurements. It
does not replace the Robovet robot profile or import Robovet types. When it is
absent, RDA may publish raw per-dimension observations but marks physical and
semantic claims `UNKNOWN` or `UNASSESSED`.

```json
{
  "profile_revision": "3",
  "profile_content_hash": "sha256:<producer-verified profile document hash>",
  "mapping_version": "v1",
  "mapping_hash": "sha256:<canonical derived mapping hash>"
}
```

The parent `robot.profile_id`, source binding, selected action/state fields,
dimension groups, units, representations, periodic periods, discrete indices,
and cameras are included in the quality effective configuration hash. A
periodic dimension is represented as `{"index": 0, "period": 360.0}`; the
period must be finite and positive. RDA never assumes a period from a name.

Adapters that produce this binding must preserve the Robovet profile identity,
revision, producer-verified raw-document hash, normalized signal identity and
the versioned source-to-RDA dimension mapping. Future Task 8 and Task 13
producers use the same serialized fields when creating plan input references.
