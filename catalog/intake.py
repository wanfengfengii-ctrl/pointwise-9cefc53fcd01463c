from dataclasses import dataclass
import json

from museum_support import BusinessError, integer, token, transaction


@dataclass(frozen=True)
class SourceDraft:
    recording_id: str
    revision: str
    source: str
    total_frames: int
    segments: list


def init_intake(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS drafts (
            recording_id TEXT NOT NULL,
            revision TEXT NOT NULL,
            source TEXT NOT NULL,
            total_frames TEXT NOT NULL,
            segments TEXT NOT NULL,
            PRIMARY KEY (recording_id, revision)
        )
    ''')


def read_draft(db, recording_id, revision):
    row = db.execute('''
        SELECT source, total_frames, segments FROM drafts
        WHERE recording_id = ? AND revision = ?
    ''', (recording_id, revision)).fetchone()
    if row is None:
        raise BusinessError(404, 'draft_not_found')
    source, total_frames, segments = row
    return SourceDraft(recording_id, revision, source, int(total_frames), json.loads(segments))


def register_draft(db, payload):
    recording_id = token(payload.get('recording_id'))
    revision = token(payload.get('revision'))
    source = token(payload.get('source'))
    total_frames = integer(payload.get('total_frames'))
    segments = payload.get('segments')
    if total_frames <= 0 or type(segments) is not list or not segments:
        raise BusinessError(400, 'bad_source')
    encoded = json.dumps(segments, sort_keys=True, allow_nan=False)
    with transaction(db, write=True):
        db.execute('''
            INSERT INTO drafts VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (recording_id, revision) DO NOTHING
        ''', (recording_id, revision, source, str(total_frames), encoded))
        saved = read_draft(db, recording_id, revision)
        if (saved.source != source or saved.total_frames != total_frames
                or json.dumps(saved.segments, sort_keys=True) != encoded):
            raise BusinessError(409, 'revision_conflict')
    return saved
