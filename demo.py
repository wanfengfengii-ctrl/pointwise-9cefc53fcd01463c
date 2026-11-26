from http.client import HTTPConnection, RemoteDisconnected
import json
from tempfile import TemporaryDirectory
from threading import Thread

from handover.runtime import build_server


RECORDING = {
    'recording_id': 'wharf', 'revision': 'r1', 'source': '河埠录音第 7 盘', 'total_frames': 64,
    'segments': [
        {'number': 1, 'name': '码头清晨', 'start_frame': 0, 'stop_frame': 12},
        {'number': 2, 'name': '摆渡路线', 'start_frame': 12, 'stop_frame': 28},
        {'number': 3, 'name': '量水标记', 'start_frame': 30, 'stop_frame': 52},
        {'number': 4, 'name': '最后一班', 'start_frame': 52, 'stop_frame': 64},
    ],
}


def request(address, route, body=None):
    connection = HTTPConnection(*address, timeout=10)
    try:
        if body is None:
            connection.request('GET', route)
        else:
            encoded = json.dumps(body, ensure_ascii=False).encode('utf-8')
            connection.request('POST', route, encoded, {'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = json.loads(response.read())
        if response.status != 200:
            raise RuntimeError(f'{route}: {response.status} {result}')
        return result
    finally:
        connection.close()


def equal(actual, expected):
    if actual != expected:
        raise AssertionError(f'Expected {expected!r}, got {actual!r}')


def run_day(address):
    def call(route, body=None):
        return request(address, route, body)

    draft = call('/drafts', RECORDING)
    release = call('/releases', {'recording_id': draft['recording_id'], 'revision': draft['revision']})
    version = release['version_id']

    def open_window(first, last, key):
        lineup = call('/lineups', {'session_id': 'wharf-morning', 'version_id': version,
                                   'first': first, 'last': last})
        return call('/takes', {'lineup_id': lineup['lineup_id'], 'request_id': key})['take_id']

    def step(take_id, key):
        return call(f'/takes/{take_id}/steps', {'request_id': key})

    first = open_window(1, 4, 'first')
    equal(step(first, 'first-1')['number'], 1)
    try:
        step(first, 'first-2')
    except RemoteDisconnected:
        history = call(f'/takes/{first}')
        equal([play['number'] for play in history['plays']], [1, 2])
    else:
        raise AssertionError('The second play response should have been lost')
    for key, start in (('A', 2), ('B', 3)):
        claim = call('/claims', {'request_id': key, 'version_id': version, 'first': start, 'last': 3})
        equal(claim['status'], 'pending')
    actual_three = step(first, 'first-3')
    stopped = call(f'/takes/{first}/stop', {'request_id': 'stop'})
    equal(stopped['played_count'], 3)
    a_after_stop, b = call('/claims/A'), call('/claims/B')
    equal(a_after_stop['status'], 'pending')
    equal(b['settlement'], {'request_id': 'B', 'take_id': first,
                            'actual_ids': [actual_three['actual_id']]})
    retry = open_window(2, 3, 'retry')
    replays = [step(retry, 'retry-2'), step(retry, 'retry-3')]
    equal([play['number'] for play in replays], [2, 3])
    a = call('/claims/A')
    equal(a['settlement'], {'request_id': 'A', 'take_id': retry,
                            'actual_ids': [play['actual_id'] for play in replays]})
    equal(call('/claims/B'), b)
    equal(call('/sessions/wharf-morning/claims/open'), [])
    archive = call('/archives', {'session_id': 'wharf-morning', 'request_id': 'handover'})
    equal(call(f'/archives/{archive["archive_id"]}'), archive)
    equal([history['take']['take_id'] for history in archive['facts']['takes']], [first, retry])
    elapsed = [[item['number'], item['start_frame'], item['stop_frame']]
               for item in archive['facts']['origins']]
    expected = [[1, 0, 12], [2, 12, 28], [3, 30, 52], [2, 12, 28], [3, 30, 52]]
    equal(elapsed, expected)
    print(json.dumps({'release': version, 'A_after_stop': a_after_stop['status'],
                      'A': a, 'B': b, 'archive': archive['archive_id']}, ensure_ascii=False))
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'v8', 'input': {'recording': RECORDING, 'first': [1, 2, 3], 'retry': [2, 3]},
        'expected': [[1, 2, 3], [2, 3]],
        'actual': [[item['number'] for item in history['plays']] for history in archive['facts']['takes']],
        'downstream_expected': expected, 'downstream_actual': elapsed,
        'code_paths': ['channel/history.py', 'handover/close.py', 'handover/reconcile.py',
                       'handover/provenance.py', 'handover/retrieve.py'],
        'oracle': '以节目执行顺序逐笔对应样例原帧，停在第 3 段，补播重复记录第 2、3 段。',
    }, ensure_ascii=False))


def main():
    def observer(phase, key):
        return (phase, key) == ('after_actual', 'first-2')

    with TemporaryDirectory(prefix='oral-history-example-') as directory:
        with build_server(directory, observer=observer) as server:
            thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02})
            thread.start()
            try:
                run_day(server.server_address)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                if thread.is_alive():
                    raise RuntimeError('Demo HTTP server did not shut down')


if __name__ == '__main__':
    main()
