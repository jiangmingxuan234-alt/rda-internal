"""Bounded H.264/MP4 decoding for verified quality-mode media references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterator, Sequence

from rda.quality.input_manifest import MediaRef, file_sha256


@dataclass(frozen=True)
class MediaDecodeError:
    target_time: float | None
    reason: str
    detail: str


@dataclass(frozen=True)
class DecodedFrame:
    target_time: float
    pts: int
    time_base: Fraction
    decoded_frame_ordinal: int
    lerobot_frame_index: int | None
    mapped_timestamp: float
    sampling_error: float
    mapping_status: str
    frame: Any


class MediaDecodeResult(Iterator[DecodedFrame]):
    """Iterator whose terminal coverage remains inspectable after iteration."""

    def __init__(self, ref: MediaRef, target_times: Sequence[float], mode: str):
        self.ref = ref
        self.target_times = tuple(target_times)
        self.mode = mode
        self.errors: list[MediaDecodeError] = []
        self.coverage = {"attempted": len(self.target_times), "computed": 0, "error": 0}
        self._iterator: Iterator[DecodedFrame] | None = None

    def __iter__(self) -> "MediaDecodeResult":
        return self

    def __next__(self) -> DecodedFrame:
        if self._iterator is None:
            self._iterator = iter(self._decode())
        return next(self._iterator)

    def _record_error(self, target: float | None, reason: str, detail: str) -> None:
        self.errors.append(MediaDecodeError(target, reason, detail))
        self.coverage["error"] += 1

    def _record_event(self, reason: str, detail: str) -> None:
        """Record a source-wide failure without inventing a target outcome."""
        self.errors.append(MediaDecodeError(None, reason, detail))

    def _source_matches_manifest(self) -> bool:
        try:
            return (
                self.ref.source_path.is_file()
                and (self.ref.source_byte_size is None or self.ref.source_path.stat().st_size == self.ref.source_byte_size)
                and file_sha256(self.ref.source_path) == self.ref.source_sha256
            )
        except OSError:
            return False

    def _decode(self) -> Iterator[DecodedFrame]:
        if self.mode != "nearest":
            for target in self.target_times:
                self._record_error(target, "unsupported_sampling_mode", f"unsupported mode: {self.mode}")
            return
        valid_targets: list[float] = []
        for target in self.target_times:
            if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target):
                self._record_error(None, "invalid_target", "target time must be finite")
            elif not (self.ref.from_timestamp <= float(target) < self.ref.to_timestamp):
                self._record_error(float(target), "target_outside_interval", "target is outside the episode's half-open media interval")
            else:
                valid_targets.append(float(target))
        if not self.ref.source_path.is_file():
            for target in valid_targets:
                self._record_error(target, "missing_media", f"media file is missing: {self.ref.relative_path}")
            return
        if not self._source_matches_manifest():
            for target in valid_targets:
                self._record_error(target, "source_changed", f"media identity changed: {self.ref.relative_path}")
            return

        pending = sorted(valid_targets)
        previous: tuple[float, int, Fraction, int, Any] | None = None
        terminal_delta: float | None = None
        try:
            import av

            with av.open(str(self.ref.source_path)) as container:
                streams = list(container.streams.video)
                stream = next((value for value in streams if value.index == self.ref.stream_index), None)
                if stream is None:
                    for target in valid_targets:
                        self._record_error(target, "missing_stream", f"video stream {self.ref.stream_index} does not exist")
                    return
                codec_name = getattr(stream.codec_context, "name", None)
                if codec_name not in {"h264", "libx264"}:
                    for target in valid_targets:
                        self._record_error(target, "unsupported_codec", f"codec {codec_name!r} is outside the H.264 scope")
                    return
                actual_time_base = Fraction(stream.time_base)
                if actual_time_base != self.ref.stream_time_base or stream.start_time != self.ref.stream_start_time:
                    for target in valid_targets:
                        self._record_error(target, "stream_identity_mismatch", "stream time_base or start_time differs from the manifest")
                    return
                media_start = (self.ref.from_timestamp - self.ref.pts_time_offset) / self.ref.pts_time_scale
                seek_pts = math.floor(media_start / float(actual_time_base))
                container.seek(max(0, seek_pts), stream=stream, backward=True, any_frame=False)
                for ordinal, frame in enumerate(container.decode(stream)):
                    if frame.pts is None or frame.time_base is None:
                        continue
                    time_base = Fraction(frame.time_base)
                    mapped = float(frame.pts * time_base) * self.ref.pts_time_scale + self.ref.pts_time_offset
                    if mapped >= self.ref.to_timestamp:
                        break
                    if mapped < self.ref.from_timestamp:
                        continue
                    current = (mapped, int(frame.pts), time_base, ordinal, frame)
                    if previous is None:
                        previous = current
                        continue
                    if current[0] <= previous[0]:
                        continue
                    terminal_delta = current[0] - previous[0]
                    while pending and pending[0] <= current[0]:
                        target = pending.pop(0)
                        if target < previous[0] - terminal_delta / 2:
                            self._record_error(target, "target_not_covered", "target lies before actual decoded coverage")
                            continue
                        candidate = min((previous, current), key=lambda value: (abs(value[0] - target), value[0]))
                        mapped, pts, time_base, ordinal, decoded = candidate
                        self.coverage["computed"] += 1
                        yield DecodedFrame(target, pts, time_base, ordinal, None, mapped, mapped - target, "mapped", decoded)
                    previous = current
        except Exception as exc:
            for target in pending:
                self._record_error(target, "decode_failed", str(exc))
            return

        # The pre-read guard binds the opening bytes.  Recheck after the stream
        # closes so a replacement during read is explicit without retracting
        # samples already yielded from the verified stream.
        if not self._source_matches_manifest():
            if pending:
                for target in pending:
                    self._record_error(target, "source_changed", f"media identity changed during decode: {self.ref.relative_path}")
            else:
                self._record_event("source_changed", f"media identity changed during decode: {self.ref.relative_path}")
            return

        if previous is None:
            for target in pending:
                self._record_error(target, "target_not_covered", "no decodable frame covers the target")
            return
        for target in pending:
            if terminal_delta is None and target != previous[0]:
                self._record_error(target, "target_not_covered", "target has no neighboring decodable frame")
                continue
            if terminal_delta is not None and target > previous[0] + terminal_delta / 2:
                self._record_error(target, "target_not_covered", "target lies beyond actual decoded coverage")
                continue
            mapped, pts, time_base, ordinal, decoded = previous
            self.coverage["computed"] += 1
            yield DecodedFrame(target, pts, time_base, ordinal, None, mapped, mapped - target, "mapped", decoded)


def decode_media_interval(ref: MediaRef, target_times: Sequence[float], mode: str) -> MediaDecodeResult:
    """Return a lazy bounded decode with structured terminal coverage."""
    return MediaDecodeResult(ref, target_times, mode)
