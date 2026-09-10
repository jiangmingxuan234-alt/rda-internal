# Quality metric registry v1

`rda.quality.registry` is the single config/dispatch disposition and parameter
schema source (`quality-registry-v1`), independent of legacy metrics/scoring.
Unknown IDs and unimplemented parameters are input errors.

| Disposition | IDs |
| --- | --- |
| measurement | action_discontinuity, idle_ratio, velocity_acceleration, sampling_jitter, visual_quality, video_freeze |
| delegated to Robovet | joint_limit, timestamp_validity, video_stream_sync, video_timestamp_alignment, missing_dropout, invalid_values, schema_consistency, video_frame_integrity |
| deferred provider | temporal_sufficiency, sensor_synchronization, distribution, coverage |

Explicit delegated/deferred requests remain structured unassessed measurements;
they never instantiate legacy checks or contribute successful quality counts.

Implemented parameter names are `mad_tolerance` for action discontinuity,
`activity_epsilon` for activity, `smoothing: "none"` for state derivatives,
`preprocess` for visual quality/freeze, and `low_change_threshold` for image
change. Numeric parameters must be finite, nonnegative JSON numbers (not
booleans). `epsilon` is rejected because it did not control implemented behavior.
Other IDs accept no parameters. These are measurement algorithm parameters,
not calibrated acceptance thresholds.

Preprocessing supports only `roi: "full"` or `[y0,y1,x0,x1]`, half-open integer
pixel bounds with nonnegative origins and at least 3 by 3 pixels. Frame bounds
are validated against the actual image at measurement time. Fixed grayscale
conversion and interior-Laplacian behavior belong to the versioned visual
algorithm evidence; no resize or alternate grayscale options are accepted.
