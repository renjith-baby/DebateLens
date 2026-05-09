from __future__ import annotations

from debatelens.models import Segment, Transcript, Window


def to_windows(transcript: Transcript, target_seconds: float = 60.0) -> list[Window]:
    if not transcript.segments:
        return []

    windows: list[Window] = []
    current: list[Segment] = []
    current_start: float | None = None
    idx = 0

    for seg in transcript.segments:
        if current_start is None:
            current_start = seg.start_time
        current.append(seg)
        if seg.end_time - current_start >= target_seconds:
            windows.append(Window(
                index=idx,
                start_time=current_start,
                end_time=seg.end_time,
                segments=current,
            ))
            idx += 1
            current = []
            current_start = None

    if current:
        windows.append(Window(
            index=idx,
            start_time=current_start if current_start is not None else current[0].start_time,
            end_time=current[-1].end_time,
            segments=current,
        ))

    return windows
