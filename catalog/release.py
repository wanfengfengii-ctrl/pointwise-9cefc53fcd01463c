from dataclasses import asdict, dataclass
import json

from catalog.intake import read_draft
from catalog.segments import SourceSegment, validate_segments
from museum_support import token, transaction


@dataclass(frozen=True)
class ReleasedSource:
    version_id: int
    recording_id: str
    revision: str
    source: str
    total_frames: int
    segments: tuple[SourceSegment, ...]


def init_releases(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS releases (
            version_id INTEGER PRIMARY KEY,
            recording_id TEXT NOT NULL,
            revision TEXT NOT NULL,
            source TEXT NOT NULL,
            total_frames TEXT NOT NULL,
            segments TEXT NOT NULL,
            UNIQUE (recording_id, revision),
            FOREIGN KEY (recording_id, revision) REFERENCES drafts (recording_id, revision)
        )
    ''')


def decode_release(row):
    version_id, recording_id, revision, source, total_frames, items = row
    segments = tuple(SourceSegment(**item) for item in json.loads(items))
    return ReleasedSource(version_id, recording_id, revision, source, int(total_frames), segments)


def release(db, recording_id, revision):
    recording_id, revision = token(recording_id), token(revision)
    with transaction(db, write=True):
        previous = db.execute('''
            SELECT version_id, recording_id, revision, source, total_frames, segments
            FROM releases WHERE recording_id = ? AND revision = ?
        ''', (recording_id, revision)).fetchone()
        if previous is not None:
            return decode_release(previous)
        draft = read_draft(db, recording_id, revision)
        segments = validate_segments(draft)
        result = db.execute('''
            INSERT INTO releases (recording_id, revision, source, total_frames, segments)
            VALUES (?, ?, ?, ?, ?)
        ''', (recording_id, revision, draft.source, str(draft.total_frames),
              json.dumps([asdict(segment) for segment in segments])))
        return ReleasedSource(result.lastrowid, recording_id, revision,
                              draft.source, draft.total_frames, segments)
