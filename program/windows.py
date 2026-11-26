from dataclasses import dataclass

from catalog.lookup import read_segments
from catalog.segments import SourceSegment
from museum_support import BusinessError, integer


@dataclass(frozen=True)
class PlaybackWindow:
    first: int
    last: int
    segments: tuple[SourceSegment, ...]


def resolve_window(db, version_id, first, last):
    first = integer(first, 'bad_window')
    last = integer(last, 'bad_window')
    if first > last:
        raise BusinessError(400, 'bad_window')
    segments = tuple(segment for segment in read_segments(db, version_id)
                     if first <= segment.number <= last)
    # Released segments are unique integers. This count detects every gap.
    if len(segments) != last - first + 1:
        raise BusinessError(400, 'bad_window')
    return PlaybackWindow(first, last, segments)
