from dataclasses import dataclass

from channel.deck import current_take, release_occupancy
from channel.history import read_take_history
from channel.takes import record_take_end
from museum_support import BusinessError, identity, token, transaction


@dataclass(frozen=True)
class StopReceipt:
    request_id: str
    take_id: int
    status: str
    played_count: int


def init_stops(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS stops (
            request_id TEXT PRIMARY KEY,
            take_id INTEGER NOT NULL UNIQUE REFERENCES takes (take_id),
            status TEXT NOT NULL CHECK (status = 'aborted'),
            played_count INTEGER NOT NULL
        )
    ''')


def read_stop_receipt(db, request_id):
    row = db.execute('''
        SELECT request_id, take_id, status, played_count FROM stops WHERE request_id = ?
    ''', (request_id,)).fetchone()
    return None if row is None else StopReceipt(*row)


def take_stop(db, take_id, request_id):
    take_id, request_id = identity(take_id), token(request_id)
    with transaction(db, write=True):
        original = read_stop_receipt(db, request_id)
        if original is not None:
            if original.take_id != take_id:
                raise BusinessError(409, 'request_conflict')
            return original
        history = read_take_history(db, take_id)
        if history.take.status != 'playing':
            raise BusinessError(409, 'take_ended')
        if current_take(db) != history.take:
            raise BusinessError(409, 'take_not_current')
        result = StopReceipt(request_id, take_id, 'aborted', len(history.plays))
        record_take_end(db, take_id, result.status)
        release_occupancy(db, take_id)
        db.execute('INSERT INTO stops VALUES (?, ?, ?, ?)',
                   (request_id, take_id, result.status, result.played_count))
        return result
