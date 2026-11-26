from dataclasses import dataclass

from catalog.intake import SourceDraft
from museum_support import BusinessError, integer, token


@dataclass(frozen=True)
class SourceSegment:
    number: int
    name: str
    start_frame: int
    stop_frame: int


def validate_segments(draft: SourceDraft) -> tuple[SourceSegment, ...]:
    if not draft.segments:
        raise BusinessError(400, 'bad_segments')
    validated = []
    for raw in draft.segments:
        if type(raw) is not dict:
            raise BusinessError(400, 'bad_segments')
        segment = SourceSegment(
            integer(raw.get('number'), 'bad_segments'),
            token(raw.get('name'), 'bad_segments'),
            integer(raw.get('start_frame'), 'bad_segments'),
            integer(raw.get('stop_frame'), 'bad_segments'),
        )
        if not 0 <= segment.start_frame < segment.stop_frame <= draft.total_frames:
            raise BusinessError(400, 'bad_segments')
        if validated:
            previous = validated[-1]
            if segment.number <= previous.number or segment.start_frame < previous.stop_frame:
                raise BusinessError(400, 'bad_segments')
        validated.append(segment)
    return tuple(validated)
