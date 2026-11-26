from museum_support import identity, token, transaction
from program.lineup import store_lineup
from program.session import bind_session
from program.windows import resolve_window


def program_issue(db, session_id, version_id, first, last):
    session_id = token(session_id)
    version_id = identity(version_id)
    with transaction(db, write=True):
        window = resolve_window(db, version_id, first, last)
        session = bind_session(db, session_id, version_id)
        return store_lineup(db, session, window)
