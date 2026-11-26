from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3


class BusinessError(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


class EvidenceUnavailable(Exception):
    pass


def token(value, code='bad_input'):
    if type(value) is not str or not value.strip():
        raise BusinessError(400, code)
    return value


def integer(value, code='bad_input'):
    if type(value) is not int:
        raise BusinessError(400, code)
    return value


def identity(value):
    value = integer(value)
    if not 1 <= value <= (1 << 63) - 1:
        raise BusinessError(400, 'bad_input')
    return value


def path_integer(value):
    try:
        return int(value)
    except ValueError as exc:
        raise BusinessError(400, 'bad_input') from exc


def storage_busy(exc):
    code = getattr(exc, 'sqlite_errorcode', 0) & 255
    return code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}


@contextmanager
def transaction(db, *, write=False):
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


@dataclass(frozen=True)
class Request:
    method: str
    parts: tuple[str, ...]
    body: dict


@dataclass(frozen=True)
class Reply:
    payload: object
    status: int = 200
    drop: bool = False
