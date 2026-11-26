from channel.takes import create_take, find_started_take, read_take
from museum_support import BusinessError, identity, token, transaction


def init_deck(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS deck (
            slot INTEGER PRIMARY KEY CHECK (slot = 1),
            take_id INTEGER REFERENCES takes (take_id)
        );
        INSERT OR IGNORE INTO deck (slot, take_id) VALUES (1, NULL);
    ''')


def current_take(db):
    take_id = db.execute('SELECT take_id FROM deck WHERE slot = 1').fetchone()[0]
    return None if take_id is None else read_take(db, take_id)


def take_start(db, lineup_id, request_id, load_lineup):
    lineup_id, request_id = identity(lineup_id), token(request_id)
    with transaction(db, write=True):
        original = find_started_take(db, request_id)
        if original is not None:
            if original.lineup_id != lineup_id:
                raise BusinessError(409, 'request_conflict')
            return original
        lineup = load_lineup(lineup_id)
        if current_take(db) is not None:
            raise BusinessError(409, 'channel_busy')
        take = create_take(db, lineup, request_id)
        db.execute('UPDATE deck SET take_id = ? WHERE slot = 1', (take.take_id,))
        return take


def release_occupancy(db, take_id):
    result = db.execute('UPDATE deck SET take_id = NULL WHERE slot = 1 AND take_id = ?', (take_id,))
    if result.rowcount != 1:
        raise BusinessError(409, 'take_not_current')
