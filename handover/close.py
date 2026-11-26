from dataclasses import asdict, dataclass
import json

from channel.deck import current_take
from handover.reconcile import reconcile_session
from museum_support import BusinessError, token, transaction


@dataclass(frozen=True)
class ArchiveItem:
    archive_id: int
    session_id: str
    request_id: str
    facts: dict


def init_archives(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS archives (
            archive_id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            facts TEXT NOT NULL
        )
    ''')


def decode_archive(row):
    archive_id, session_id, request_id, facts = row
    return ArchiveItem(archive_id, session_id, request_id, json.loads(facts))


def find_closed_archive(db, request_id):
    row = db.execute('''
        SELECT archive_id, session_id, request_id, facts FROM archives WHERE request_id = ?
    ''', (request_id,)).fetchone()
    return None if row is None else decode_archive(row)


def archive(library, field, ledger, session_id, request_id):
    session_id, request_id = token(session_id), token(request_id)
    with transaction(ledger, write=True):
        original = find_closed_archive(ledger, request_id)
        if original is not None:
            if original.session_id != session_id:
                raise BusinessError(409, 'request_conflict')
            return original
        # Hold the request ledger stable while taking a single field read snapshot.
        with transaction(field):
            if current_take(field) is not None:
                raise BusinessError(409, 'channel_busy')
            facts = reconcile_session(library, field, ledger, session_id)
            body = json.dumps(asdict(facts), ensure_ascii=False)
        result = ledger.execute('''
            INSERT INTO archives (session_id, request_id, facts) VALUES (?, ?, ?)
        ''', (session_id, request_id, body))
        return ArchiveItem(result.lastrowid, session_id, request_id, json.loads(body))
