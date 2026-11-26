from dataclasses import dataclass

from catalog.lookup import read_release


@dataclass(frozen=True)
class OriginReference:
    actual_id: int
    take_id: int
    version_id: int
    recording_id: str
    revision: str
    source: str
    number: int
    name: str
    start_frame: int
    stop_frame: int


def resolve_play_origins(library, version_id, plays):
    release = read_release(library, version_id)
    segments = {segment.number: segment for segment in release.segments}
    references = []
    for play in plays:
        segment = segments.get(play.number)
        if segment is None:
            raise RuntimeError('Actual play has no source segment in its fixed release')
        references.append(OriginReference(
            play.actual_id, play.take_id, release.version_id, release.recording_id,
            release.revision, release.source, segment.number, segment.name,
            segment.start_frame, segment.stop_frame,
        ))
    return tuple(references)
