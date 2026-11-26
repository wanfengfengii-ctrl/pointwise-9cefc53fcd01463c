import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import unquote, urlsplit

from catalog.intake import init_intake
from catalog.release import init_releases
from channel.deck import init_deck, take_start
from channel.history import init_boundaries, read_take_history, read_version_takes, register_claim_boundary
from channel.http_api import build_channel_handler
from channel.output import init_actuals, take_step
from channel.stop import init_stops, take_stop
from channel.takes import init_takes
from handover.close import init_archives
from handover.http_api import build_desk_handler
from museum_support import BusinessError, EvidenceUnavailable, Reply, Request, storage_busy, transaction
from program.lineup import init_lineups, read_lineup
from program.session import init_sessions
from requests.admission import admit
from requests.http_api import build_claim_handler
from requests.ledger import init_claims
from requests.pending import claim_read, list_open_claims, refresh_claim


@contextmanager
def _connect(path):
    db = sqlite3.connect(path, timeout=5, isolation_level=None)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        yield db
    finally:
        db.close()


class _Application:
    def __init__(self, directory, observer=None):
        self.directory = Path(directory)
        self.observer = observer

    def library(self):
        return _connect(self.directory / 'library.sqlite3')

    def field(self):
        return _connect(self.directory / 'channel.sqlite3')

    def ledger(self):
        return _connect(self.directory / 'desk.sqlite3')

    def observe(self, phase, request_id):
        if self.observer is not None:
            return self.observer(phase, request_id)
        return False

    def lineup(self, lineup_id):
        with self.library() as library:
            return read_lineup(library, lineup_id)

    def start(self, lineup_id, request_id):
        with self.field() as db:
            return take_start(db, lineup_id, request_id, self.lineup)

    def step(self, take_id, request_id):
        with self.field() as db:
            return take_step(db, take_id, request_id, self.lineup)

    def stop(self, take_id, request_id):
        with self.field() as db:
            return take_stop(db, take_id, request_id)

    def take_history(self, take_id):
        with self.field() as db, transaction(db):
            return read_take_history(db, take_id)

    @contextmanager
    def _field_evidence(self):
        try:
            with self.field() as db:
                yield db
        except sqlite3.OperationalError as exc:
            if storage_busy(exc):
                raise EvidenceUnavailable('Field evidence temporarily busy') from exc
            raise

    def register_boundary(self, claim):
        request_id = claim.request_id
        if self.observe('before_admission', request_id):
            raise EvidenceUnavailable('Admission delivery unavailable')
        window = claim.window
        with self._field_evidence() as db:
            result = register_claim_boundary(db, request_id, window.version_id, window.first, window.last)
        if self.observe('after_admission', request_id):
            raise EvidenceUnavailable('Admission response unavailable')
        return result

    def version_history(self, version_id):
        with self._field_evidence() as db, transaction(db):
            return read_version_takes(db, version_id)

    def admit_claim(self, request_id, version_id, first, last):
        with self.library() as library:
            claim = admit(library, self.ledger, self.register_boundary, request_id, version_id, first, last)
        return refresh_claim(self.ledger, self.version_history, claim)

    def read_claim(self, request_id):
        return claim_read(self.ledger, self.register_boundary, self.version_history, request_id)

    def open_claims(self, session_id):
        with self.library() as library:
            return list_open_claims(library, self.ledger, self.register_boundary,
                                    self.version_history, session_id)


def initialize_data(directory):
    app = _Application(directory)
    app.directory.mkdir(parents=True, exist_ok=True)
    with app.library() as db:
        for initialize in (init_intake, init_releases, init_sessions, init_lineups):
            initialize(db)
    with app.field() as db:
        for initialize in (init_takes, init_deck, init_actuals, init_stops, init_boundaries):
            initialize(db)
    with app.ledger() as db:
        for initialize in (init_claims, init_archives):
            initialize(db)


def _reject_constant(_value):
    raise ValueError('Nonfinite JSON number')


def _read_body(handler):
    try:
        size = int(handler.headers.get('Content-Length', '0'))
        if not 1 <= size <= 1024 * 1024:
            raise ValueError('Unexpected JSON body length')
        body = json.loads(handler.rfile.read(size).decode('utf-8'), parse_constant=_reject_constant)
        if type(body) is not dict:
            raise ValueError('Expected a JSON object')
        # Escaped surrogates are not Unicode scalar values and cannot be stored as UTF-8 text.
        json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        return body
    except (ValueError, RecursionError) as exc:
        raise BusinessError(400, 'bad_json') from exc


def build_server(directory, port=0, *, observer=None):
    initialize_data(directory)
    app = _Application(directory, observer)
    routes = (build_channel_handler(app), build_claim_handler(app), build_desk_handler(app))

    class HttpHandler(BaseHTTPRequestHandler):
        def _handle(self, method):
            try:
                path = urlsplit(self.path).path
                parts = tuple(unquote(part) for part in path.split('/')[1:] if part)
                body = _read_body(self) if method == 'POST' else {}
                request = Request(method, parts, body)
                for route in routes:
                    reply = route(request)
                    if reply is not None:
                        break
                else:
                    reply = Reply({'error': 'route_not_found'}, 404)
            except BusinessError as exc:
                reply = Reply({'error': exc.code}, exc.status)
            except EvidenceUnavailable:
                reply = Reply({'error': 'evidence_unavailable'}, 503)
            except sqlite3.OperationalError as exc:
                if not storage_busy(exc):
                    raise
                reply = Reply({'error': 'storage_busy'}, 503)
            except ValueError:
                reply = Reply({'error': 'bad_input'}, 400)
            if reply.drop:
                self.close_connection = True
                return
            encoded = json.dumps(reply.payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
            try:
                self.send_response(reply.status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except ConnectionError:
                self.close_connection = True

        def do_GET(self):
            self._handle('GET')

        def do_POST(self):
            self._handle('POST')

        def log_message(self, _format, *args):
            pass

    return ThreadingHTTPServer(('127.0.0.1', port), HttpHandler)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Oral history listening desk')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init')
    init.add_argument('--data-dir', required=True)
    serve = commands.add_parser('serve')
    serve.add_argument('--data-dir', required=True)
    serve.add_argument('--port', type=int, default=8765)
    options = parser.parse_args(argv)
    if options.command == 'init':
        initialize_data(options.data_dir)
        return 0
    with build_server(options.data_dir, options.port) as server:
        host, port = server.server_address
        print(f'Listening on http://{host}:{port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
