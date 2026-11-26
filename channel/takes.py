from dataclasses import dataclass

from museum_support import BusinessError
from program.lineup import Lineup


@dataclass(frozen=True)
class Take:
    take_id: int
    lineup_id: int
    session_id: str
    version_id: int
    request_id: str
    status: str


_TAKE_FIELDS = 'take_id, lineup_id, session_id, version_id, request_id, status'


def init_takes(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS takes (
            take_id INTEGER PRIMARY KEY,
            lineup_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            version_id INTEGER NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('playing', 'finished', 'aborted'))
        );
        CREATE INDEX IF NOT EXISTS takes_by_session ON takes (session_id, take_id);
        CREATE INDEX IF NOT EXISTS takes_by_version ON takes (version_id, take_id);
    ''')


def create_take(db, lineup: Lineup, request_id):
    result = db.execute('''
        INSERT INTO takes (lineup_id, session_id, version_id, request_id, status)
        VALUES (?, ?, ?, ?, 'playing')
    ''', (lineup.lineup_id, lineup.session_id, lineup.version_id, request_id))
    return read_take(db, result.lastrowid)


def read_take(db, take_id):
    row = db.execute(f'SELECT {_TAKE_FIELDS} FROM takes WHERE take_id = ?', (take_id,)).fetchone()
    if row is None:
        raise BusinessError(404, 'take_not_found')
    return Take(*row)


def find_started_take(db, request_id):
    row = db.execute(f'SELECT {_TAKE_FIELDS} FROM takes WHERE request_id = ?', (request_id,)).fetchone()
    return Take(*row) if row is not None else None


def record_take_end(db, take_id, status):
    result = db.execute('''
        UPDATE takes SET status = ? WHERE take_id = ? AND status = 'playing'
    ''', (status, take_id))
    if result.rowcount != 1:
        raise BusinessError(409, 'take_ended')
    return read_take(db, take_id)
