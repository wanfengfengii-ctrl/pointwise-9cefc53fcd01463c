from dataclasses import dataclass

from channel.deck import current_take, release_occupancy
from channel.takes import read_take, record_take_end
from museum_support import BusinessError, identity, token, transaction


@dataclass(frozen=True)
class ActualPlay:
    actual_id: int
    take_id: int
    position: int
    number: int
    request_id: str


def init_actuals(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS actuals (
            actual_id INTEGER PRIMARY KEY AUTOINCREMENT,
            take_id INTEGER NOT NULL REFERENCES takes (take_id),
            position INTEGER NOT NULL CHECK (position >= 1),
            number TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            UNIQUE (take_id, position)
        )
    ''')


def decode_play(row):
    actual_id, take_id, position, number, request_id = row
    return ActualPlay(actual_id, take_id, position, int(number), request_id)


def read_step_receipt(db, request_id):
    row = db.execute('''
        SELECT actual_id, take_id, position, number, request_id
        FROM actuals WHERE request_id = ?
    ''', (request_id,)).fetchone()
    return None if row is None else decode_play(row)


def actual_frontier(db):
    return db.execute('SELECT COALESCE(MAX(actual_id), 0) FROM actuals').fetchone()[0]


def take_step(db, take_id, request_id, load_lineup):
    take_id, request_id = identity(take_id), token(request_id)
    with transaction(db, write=True):
        previous = read_step_receipt(db, request_id)
        if previous is not None:
            if previous.take_id != take_id:
                raise BusinessError(409, 'request_conflict')
            return previous
        take = read_take(db, take_id)
        if take.status != 'playing':
            raise BusinessError(409, 'take_ended')
        if current_take(db) != take:
            raise BusinessError(409, 'take_not_current')
        lineup = load_lineup(take.lineup_id)
        position = db.execute('''
            SELECT COALESCE(MAX(position), 0) + 1 FROM actuals WHERE take_id = ?
        ''', (take_id,)).fetchone()[0]
        segment = lineup.segments[position - 1]
        result = db.execute('''
            INSERT INTO actuals (take_id, position, number, request_id) VALUES (?, ?, ?, ?)
        ''', (take_id, position, str(segment.number), request_id))
        if position == len(lineup.segments):
            record_take_end(db, take_id, 'finished')
            release_occupancy(db, take_id)
        return ActualPlay(result.lastrowid, take_id, position, segment.number, request_id)
