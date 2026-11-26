from dataclasses import asdict, dataclass
import json

from catalog.segments import SourceSegment
from museum_support import BusinessError, identity
from program.session import ListeningSession


@dataclass(frozen=True)
class Lineup:
    lineup_id: int
    session_id: str
    version_id: int
    first: int
    last: int
    segments: tuple[SourceSegment, ...]


def init_lineups(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS lineups (
            lineup_id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            version_id INTEGER NOT NULL,
            first TEXT NOT NULL,
            last TEXT NOT NULL,
            segments TEXT NOT NULL,
            FOREIGN KEY (session_id, version_id) REFERENCES sessions (session_id, version_id)
        )
    ''')


def store_lineup(db, session: ListeningSession, window):
    values = (session.session_id, session.version_id, str(window.first), str(window.last),
              json.dumps([asdict(segment) for segment in window.segments]))
    result = db.execute('''
        INSERT INTO lineups (session_id, version_id, first, last, segments)
        VALUES (?, ?, ?, ?, ?)
    ''', values)
    return Lineup(result.lastrowid, session.session_id, session.version_id,
                  window.first, window.last, window.segments)


def read_lineup(db, lineup_id):
    lineup_id = identity(lineup_id)
    row = db.execute('''
        SELECT session_id, version_id, first, last, segments
        FROM lineups WHERE lineup_id = ?
    ''', (lineup_id,)).fetchone()
    if row is None:
        raise BusinessError(404, 'lineup_not_found')
    session_id, version_id, first, last, segments = row
    return Lineup(lineup_id, session_id, version_id, int(first), int(last),
                  tuple(SourceSegment(**item) for item in json.loads(segments)))
