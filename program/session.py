from dataclasses import dataclass

from museum_support import BusinessError, token


@dataclass(frozen=True)
class ListeningSession:
    session_id: str
    version_id: int


def init_sessions(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            version_id INTEGER NOT NULL REFERENCES releases (version_id),
            UNIQUE (session_id, version_id)
        )
    ''')


def read_session(db, session_id):
    session_id = token(session_id)
    row = db.execute('SELECT version_id FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
    if row is None:
        raise BusinessError(404, 'session_not_found')
    return ListeningSession(session_id, row[0])


def bind_session(db, session_id, version_id):
    session_id = token(session_id)
    db.execute('''
        INSERT INTO sessions (session_id, version_id) VALUES (?, ?)
        ON CONFLICT (session_id) DO NOTHING
    ''', (session_id, version_id))
    session = read_session(db, session_id)
    if session.version_id != version_id:
        raise BusinessError(409, 'session_version_conflict')
    return session
