from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import hashlib
from pathlib import Path
import sys
import types

import av
import numpy as np

from rda.quality.input_manifest import MediaRef
from rda.quality.media import decode_media_interval


def _write_video(path: Path, *, frames: int = 8, fps: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=fps)
        stream.width = 32
        stream.height = 32
        stream.pix_fmt = "yuv420p"
        stream.gop_size = 4
        for index in range(frames):
            pixels = np.full((32, 32, 3), index * 20, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, fps)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def _ref(path: Path, *, start: float = 5.2, end: float = 5.6) -> MediaRef:
    return MediaRef(
        episode_id=7,
        feature_key="observation.images.front",
        source_path=path,
        relative_path="videos/shared.mp4",
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "a" * 64,
        stream_index=0,
        from_timestamp=start,
        to_timestamp=end,
        clock_domain="lerobot_timestamp_seconds",
        mapping_version=1,
        pts_time_scale=1.0,
        pts_time_offset=5.0,
        stream_start_time=0,
        stream_time_base=Fraction(1, 10240),
        status="complete",
        source_byte_size=path.stat().st_size if path.is_file() else None,
    )


def test_decode_filters_seek_preroll_and_preserves_real_pts(tmp_path):
    video = tmp_path / "videos" / "shared.mp4"
    _write_video(video)

    result = decode_media_interval(_ref(video), [5.21, 5.39, 5.49], mode="nearest")
    frames = list(result)

    assert result.coverage == {"attempted": 3, "computed": 3, "error": 0}
    assert [frame.target_time for frame in frames] == [5.21, 5.39, 5.49]
    assert all(5.2 <= frame.mapped_timestamp < 5.6 for frame in frames)
    assert [frame.pts for frame in frames] == [2048, 4096, 5120]
    assert all(frame.time_base == Fraction(1, 10240) for frame in frames)
    assert [frame.decoded_frame_ordinal for frame in frames] == [2, 4, 5]
    assert all(frame.lerobot_frame_index is None for frame in frames)
    assert [round(frame.sampling_error, 3) for frame in frames] == [-0.01, 0.01, 0.01]


def test_decode_reports_missing_file_and_out_of_interval_targets(tmp_path):
    result = decode_media_interval(_ref(tmp_path / "missing.mp4"), [5.3], mode="nearest")
    assert list(result) == []
    assert result.coverage == {"attempted": 1, "computed": 0, "error": 1}
    assert result.errors[0].reason == "missing_media"

    video = tmp_path / "videos" / "shared.mp4"
    _write_video(video)
    result = decode_media_interval(_ref(video), [5.1, 5.3, 5.7], mode="nearest")
    frames = list(result)
    assert [frame.target_time for frame in frames] == [5.3]
    assert result.coverage == {"attempted": 3, "computed": 1, "error": 2}
    assert [error.reason for error in result.errors] == ["target_outside_interval", "target_outside_interval"]


def test_decode_undecodable_tail_is_explicit_partial_result(tmp_path):
    video = tmp_path / "videos" / "short.mp4"
    _write_video(video, frames=4)
    result = decode_media_interval(_ref(video, start=5.0, end=5.8), [5.2, 5.7], mode="nearest")
    frames = list(result)
    assert [frame.target_time for frame in frames] == [5.2]
    assert result.coverage == {"attempted": 2, "computed": 1, "error": 1}
    assert result.errors[0].reason == "target_not_covered"


def test_decode_maps_an_exact_target_from_a_single_decodable_frame(tmp_path):
    """Requiring a second frame would reject the one real PTS at 5.0."""
    video = tmp_path / "videos" / "single.mp4"
    _write_video(video, frames=1)

    result = decode_media_interval(_ref(video, start=5.0, end=5.1), [5.0], mode="nearest")
    frames = list(result)

    assert [frame.target_time for frame in frames] == [5.0]
    assert frames[0].mapped_timestamp == 5.0
    assert result.coverage == {"attempted": 1, "computed": 1, "error": 0}


def test_decode_rechecks_source_identity_when_iteration_begins(tmp_path):
    video = tmp_path / "videos" / "shared.mp4"
    _write_video(video)
    result = decode_media_interval(_ref(video), [5.3], mode="nearest")
    video.write_bytes(b"replaced after MediaRef creation")

    assert list(result) == []
    assert result.coverage == {"attempted": 1, "computed": 0, "error": 1}
    assert result.errors[0].reason == "source_changed"


def test_decode_stream_failure_preserves_samples_completed_before_failure(tmp_path, monkeypatch):
    """A decoder exception must only fail targets that have not been mapped yet."""
    # Removing the stream-error branch would turn this partial result into an
    # all-error result, losing the observable sample at 5.01.
    source = tmp_path / "videos" / "interrupted.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"verified synthetic source")

    class Frame:
        def __init__(self, pts):
            self.pts = pts
            self.time_base = Fraction(1, 10)

    class Stream:
        index = 0
        time_base = Fraction(1, 10)
        start_time = 0
        codec_context = types.SimpleNamespace(name="h264")

    class Container:
        streams = types.SimpleNamespace(video=[Stream()])

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def seek(self, *_args, **_kwargs):
            pass

        def decode(self, _stream):
            yield Frame(0)
            yield Frame(1)
            raise RuntimeError("decoder stopped")

    monkeypatch.setitem(sys.modules, "av", types.SimpleNamespace(open=lambda _: Container()))
    ref = replace(_ref(source, start=5.0, end=5.4), stream_time_base=Fraction(1, 10))
    result = decode_media_interval(ref, [5.01, 5.25], mode="nearest")

    frames = list(result)

    assert [frame.target_time for frame in frames] == [5.01]
    assert result.coverage == {"attempted": 2, "computed": 1, "error": 1}
    assert [(error.target_time, error.reason) for error in result.errors] == [(5.25, "decode_failed")]
