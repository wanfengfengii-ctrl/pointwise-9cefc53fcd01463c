from catalog.release import decode_release
from museum_support import BusinessError, identity, integer


def read_release(db, version_id):
    version_id = identity(version_id)
    row = db.execute('''
        SELECT version_id, recording_id, revision, source, total_frames, segments
        FROM releases WHERE version_id = ?
    ''', (version_id,)).fetchone()
    if row is None:
        raise BusinessError(404, 'version_not_found')
    return decode_release(row)


def read_segments(db, version_id):
    return read_release(db, version_id).segments


def read_segment(db, version_id, number):
    number = integer(number)
    for segment in read_segments(db, version_id):
        if segment.number == number:
            return segment
    raise BusinessError(404, 'segment_not_found')
