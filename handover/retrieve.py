from handover.close import decode_archive
from museum_support import BusinessError, identity


def archive_read(ledger, archive_id):
    archive_id = identity(archive_id)
    row = ledger.execute('''
        SELECT archive_id, session_id, request_id, facts FROM archives WHERE archive_id = ?
    ''', (archive_id,)).fetchone()
    if row is None:
        raise BusinessError(404, 'archive_not_found')
    return decode_archive(row)
