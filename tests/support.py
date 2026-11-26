from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from http.client import HTTPConnection
import json
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest

from handover.runtime import build_server


SOURCE = {
    'recording_id': 'river',
    'revision': 'r1',
    'source': '磁带甲面',
    'total_frames': 48,
    'segments': [
        {'number': 1, 'name': '序言', 'start_frame': 0, 'stop_frame': 8},
        {'number': 2, 'name': '渡船', 'start_frame': 8, 'stop_frame': 20},
        {'number': 3, 'name': '水尺', 'start_frame': 22, 'stop_frame': 36},
        {'number': 4, 'name': '归岸', 'start_frame': 36, 'stop_frame': 48},
    ],
}


class HttpCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = directory.name
        self.server = None
        self.observer = None
        self.addCleanup(self.close_server)
        self.open_server()

    def open_server(self):
        self.server = build_server(self.directory, observer=self.observe)
        self.thread = Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()

    def observe(self, phase, key):
        if self.observer is not None:
            return self.observer(phase, key)
        return False

    def close_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=5)
            self.assertFalse(self.thread.is_alive())
            self.server = None

    def reopen(self):
        self.close_server()
        self.open_server()

    def call(self, path, body=None, *, status=200):
        connection = HTTPConnection(*self.server.server_address, timeout=15)
        try:
            if body is None:
                connection.request('GET', path)
            else:
                connection.request('POST', path, json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                   {'Content-Type': 'application/json'})
            response = connection.getresponse()
            result = json.loads(response.read())
            self.assertEqual(response.status, status, result)
            return result
        finally:
            connection.close()

    def error(self, path, body, status, code):
        self.assertEqual(self.call(path, body, status=status), {'error': code})

    @contextmanager
    def gated_step(self, take_id, key, phase, *, drop=False):
        reached, release = Event(), Event()

        def observer(event, request_id):
            if (event, request_id) != (phase, key):
                return False
            reached.set()
            if not release.wait(timeout=12):
                raise RuntimeError('HTTP step gate was not released')
            return drop

        previous = self.observer
        self.observer = observer
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.step, take_id, key)
                try:
                    self.assertTrue(reached.wait(timeout=8), f'{phase} was not reached')
                    yield future
                finally:
                    release.set()
        finally:
            self.observer = previous

    def draft(self, **changes):
        source = deepcopy(SOURCE)
        source.update(changes)
        return self.call('/drafts', source)

    def publish(self, **changes):
        draft = self.draft(**changes)
        return self.call('/releases', {key: draft[key] for key in ('recording_id', 'revision')})

    def issue(self, version, first=1, last=4, session='morning'):
        return self.call('/lineups', {'session_id': session, 'version_id': version,
                                      'first': first, 'last': last})['lineup_id']

    def start(self, lineup, key):
        return self.call('/takes', {'lineup_id': lineup, 'request_id': key})['take_id']

    def step(self, take, key):
        return self.call(f'/takes/{take}/steps', {'request_id': key})

    def stop(self, take, key):
        return self.call(f'/takes/{take}/stop', {'request_id': key})

    def history(self, take):
        return self.call(f'/takes/{take}')

    def claim(self, key, version, first, last):
        return self.call('/claims', {'request_id': key, 'version_id': version,
                                     'first': first, 'last': last})

    def get_claim(self, key):
        return self.call(f'/claims/{key}')

    def close_session(self, key, session='morning'):
        return self.call('/archives', {'session_id': session, 'request_id': key})

    def assert_pending(self, claim, status='pending'):
        self.assertEqual(claim['status'], status)
        self.assertIsNone(claim['settlement'])

    def assert_settlement(self, key, take, *actual_ids):
        claim = self.get_claim(key)
        self.assertEqual(claim['status'], 'settled')
        self.assertEqual(claim['settlement'], {'request_id': key, 'take_id': take,
                                               'actual_ids': list(actual_ids)})
        return claim
