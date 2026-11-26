from dataclasses import dataclass
import json

from museum_support import BusinessError
from requests.range_check import ClaimWindow


@dataclass(frozen=True)
class Settlement:
    request_id: str
    take_id: int
    actual_ids: tuple[int, ...]


@dataclass(frozen=True)
class Transfer:
    transfer_id: str
    archive_id: int
    claim_request_id: str
    from_session_id: str
    to_session_id: str
    after_actual_id: int


@dataclass(frozen=True)
class Claim:
    request_id: str
    window: ClaimWindow
    admitted_after: int | None
    settlement: Settlement | None
    transfer: Transfer | None


def init_claims(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS claims (
            request_id TEXT PRIMARY KEY,
            version_id INTEGER NOT NULL,
            first TEXT NOT NULL,
            last TEXT NOT NULL,
            admitted_after INTEGER CHECK (admitted_after >= 0)
        );
        CREATE INDEX IF NOT EXISTS claims_by_version ON claims (version_id, request_id);
        CREATE TABLE IF NOT EXISTS settlements (
            request_id TEXT PRIMARY KEY REFERENCES claims (request_id),
            take_id INTEGER NOT NULL,
            actual_ids TEXT NOT NULL
        );
    ''')


def init_transfers(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS transfers (
            transfer_id TEXT PRIMARY KEY,
            archive_id INTEGER NOT NULL,
            claim_request_id TEXT NOT NULL UNIQUE REFERENCES claims (request_id),
            from_session_id TEXT NOT NULL,
            to_session_id TEXT NOT NULL,
            after_actual_id INTEGER NOT NULL CHECK (after_actual_id >= 0)
        )
    ''')


_CLAIM_QUERY = '''
    SELECT c.request_id, c.version_id, c.first, c.last, c.admitted_after,
           s.take_id, s.actual_ids,
           t.transfer_id, t.archive_id, t.from_session_id, t.to_session_id, t.after_actual_id
    FROM claims AS c
    LEFT JOIN settlements AS s USING (request_id)
    LEFT JOIN transfers AS t ON t.claim_request_id = c.request_id
'''


def _decode_claim(row):
    (request_id, version_id, first, last, admitted_after, take_id, actual_ids,
     transfer_id, archive_id, from_session_id, to_session_id, after_actual_id) = row
    settlement = None
    if take_id is not None:
        settlement = Settlement(request_id, take_id, tuple(json.loads(actual_ids)))
    transfer = None
    if transfer_id is not None:
        transfer = Transfer(transfer_id, archive_id, request_id,
                            from_session_id, to_session_id, after_actual_id)
    return Claim(request_id, ClaimWindow(version_id, int(first), int(last)),
                 admitted_after, settlement, transfer)


def read_claim(db, request_id):
    row = db.execute(_CLAIM_QUERY + ' WHERE c.request_id = ?', (request_id,)).fetchone()
    if row is None:
        raise BusinessError(404, 'claim_not_found')
    return _decode_claim(row)


def save_pending_review(db, request_id, window):
    db.execute('''
        INSERT INTO claims (request_id, version_id, first, last) VALUES (?, ?, ?, ?)
        ON CONFLICT (request_id) DO NOTHING
    ''', (request_id, window.version_id, str(window.first), str(window.last)))
    claim = read_claim(db, request_id)
    if claim.window != window:
        raise BusinessError(409, 'request_conflict')
    return claim


def save_admission(db, request_id, after_actual_id):
    db.execute('''
        UPDATE claims SET admitted_after = ? WHERE request_id = ? AND admitted_after IS NULL
    ''', (after_actual_id, request_id))
    result = read_claim(db, request_id)
    if result.admitted_after != after_actual_id:
        raise RuntimeError('Conflicting official admission evidence')
    return result


def scan_version_claims(db, version_id):
    rows = db.execute(_CLAIM_QUERY + ' WHERE c.version_id = ? ORDER BY c.request_id', (version_id,))
    return tuple(_decode_claim(row) for row in rows)


def save_settlement(db, result):
    db.execute('''
        INSERT INTO settlements (request_id, take_id, actual_ids) VALUES (?, ?, ?)
        ON CONFLICT (request_id) DO NOTHING
    ''', (result.request_id, result.take_id, json.dumps(result.actual_ids)))
    return read_claim(db, result.request_id)


_TRANSFER_FIELDS = 'transfer_id, archive_id, claim_request_id, from_session_id, to_session_id, after_actual_id'


def find_transfer(db, transfer_id):
    row = db.execute(f'''
        SELECT {_TRANSFER_FIELDS} FROM transfers WHERE transfer_id = ?
    ''', (transfer_id,)).fetchone()
    return None if row is None else Transfer(*row)


def find_claim_transfer(db, claim_request_id):
    row = db.execute(f'''
        SELECT {_TRANSFER_FIELDS} FROM transfers WHERE claim_request_id = ?
    ''', (claim_request_id,)).fetchone()
    return None if row is None else Transfer(*row)


def save_transfer(db, transfer):
    db.execute('''
        INSERT INTO transfers (transfer_id, archive_id, claim_request_id,
                               from_session_id, to_session_id, after_actual_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (transfer.transfer_id, transfer.archive_id, transfer.claim_request_id,
          transfer.from_session_id, transfer.to_session_id, transfer.after_actual_id))
    return transfer
