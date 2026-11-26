from dataclasses import dataclass

from channel.output import ActualPlay, actual_frontier, decode_play
from channel.takes import Take, read_take
from museum_support import BusinessError, transaction


@dataclass(frozen=True)
class TakeHistory:
    take: Take
    plays: tuple[ActualPlay, ...]


@dataclass(frozen=True)
class AdmissionBoundary:
    request_id: str
    version_id: int
    first: int
    last: int
    after_actual_id: int


def init_boundaries(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS admission_boundaries (
            request_id TEXT PRIMARY KEY,
            version_id INTEGER NOT NULL,
            first TEXT NOT NULL,
            last TEXT NOT NULL,
            after_actual_id INTEGER NOT NULL CHECK (after_actual_id >= 0)
        )
    ''')


def read_claim_boundary(db, request_id):
    row = db.execute('''
        SELECT version_id, first, last, after_actual_id FROM admission_boundaries
        WHERE request_id = ?
    ''', (request_id,)).fetchone()
    if row is None:
        return None
    version_id, first, last, after_actual_id = row
    return AdmissionBoundary(request_id, version_id, int(first), int(last), after_actual_id)


def register_claim_boundary(db, request_id, version_id, first, last):
    with transaction(db, write=True):
        original = read_claim_boundary(db, request_id)
        if original is not None:
            if (original.version_id, original.first, original.last) != (version_id, first, last):
                raise BusinessError(409, 'request_conflict')
            return original
        after_actual_id = actual_frontier(db)
        db.execute('''
            INSERT INTO admission_boundaries VALUES (?, ?, ?, ?, ?)
        ''', (request_id, version_id, str(first), str(last), after_actual_id))
        return AdmissionBoundary(request_id, version_id, first, last, after_actual_id)


def read_take_history(db, take_id):
    take = read_take(db, take_id)
    rows = db.execute('''
        SELECT actual_id, take_id, position, number, request_id
        FROM actuals WHERE take_id = ? ORDER BY position
    ''', (take_id,))
    return TakeHistory(take, tuple(decode_play(row) for row in rows))


def read_version_takes(db, version_id):
    rows = db.execute('SELECT take_id FROM takes WHERE version_id = ? ORDER BY take_id', (version_id,))
    return tuple(read_take_history(db, row[0]) for row in rows)


def read_session_takes(db, session_id):
    rows = db.execute('SELECT take_id FROM takes WHERE session_id = ? ORDER BY take_id', (session_id,))
    return tuple(read_take_history(db, row[0]) for row in rows)
