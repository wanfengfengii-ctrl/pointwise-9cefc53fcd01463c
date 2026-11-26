from copy import deepcopy

from tests.support import HttpCase, SOURCE


class HandoverTests(HttpCase):
    def test_close_after_stop(self):
        release = self.publish()
        version = release['version_id']
        self.claim('ready', version, 2, 2)
        self.claim('missing', version, 2, 4)
        take = self.start(self.issue(version, 2, 4), 'open')
        played = self.step(take, 'step')
        self.error('/archives', {'session_id': 'morning', 'request_id': 'close'}, 409, 'channel_busy')
        self.error('/archives/1', None, 404, 'archive_not_found')
        self.stop(take, 'stop')
        item = self.close_session('close')
        self.assertEqual(item['facts']['takes'], [self.history(take)])
        self.assertEqual(item['facts']['release'], release)
        claims = {claim['request_id']: claim for claim in item['facts']['claims']}
        self.assert_pending(claims['missing'])
        self.assertEqual(claims['ready']['settlement'], {'request_id': 'ready', 'take_id': take,
                                                         'actual_ids': [played['actual_id']]})
        self.assertEqual(item['facts']['origins'], [{
            'actual_id': played['actual_id'], 'take_id': take, 'version_id': version,
            'recording_id': 'river', 'revision': 'r1', 'source': '磁带甲面',
            'number': 2, 'name': '渡船', 'start_frame': 8, 'stop_frame': 20,
        }])
        self.reopen()
        self.assertEqual(self.call(f'/archives/{item["archive_id"]}'), item)
        self.assertEqual(self.close_session('close'), item)

    def test_open_without_actual(self):
        version = self.publish()['version_id']
        self.issue(version)
        take = self.start(self.issue(version, session='afternoon'), 'open')
        self.error('/archives', {'session_id': 'morning', 'request_id': 'other-close'}, 409, 'channel_busy')
        self.error('/archives', {'session_id': 'afternoon', 'request_id': 'close'}, 409, 'channel_busy')
        self.error('/archives/1', None, 404, 'archive_not_found')
        self.stop(take, 'stop')
        archived = self.close_session('close', 'afternoon')
        self.assertEqual(archived['facts']['takes'], [self.history(take)])
        self.assertEqual(archived['facts']['takes'][0]['take']['status'], 'aborted')
        self.assertEqual(archived['facts']['takes'][0]['plays'], [])
        self.assertEqual(archived['facts']['origins'], [])
        self.error('/archives', {'session_id': 'morning', 'request_id': 'close'}, 409, 'request_conflict')

    def test_fixed_snapshot(self):
        release = self.publish()
        version = release['version_id']
        self.claim('later', version, 2, 3)
        self.observer = lambda phase, key: (phase, key) == ('before_admission', 'unresolved')
        self.assert_pending(self.claim('unresolved', version, 2, 2), 'pending_review')
        first = self.start(self.issue(version, 2, 4), 'first')
        played = self.step(first, 'first-2')
        self.stop(first, 'stop-first')
        original = self.close_session('close')
        states = {item['request_id']: item['status'] for item in original['facts']['claims']}
        self.assertEqual(states, {'later': 'pending', 'unresolved': 'pending_review'})
        self.assertEqual(original['facts']['release'], release)
        self.assertEqual(original['facts']['origins'][0]['start_frame'], 8)
        self.assertEqual(original['facts']['takes'][0]['plays'], [played])
        self.observer = None
        self.assert_pending(self.get_claim('unresolved'))
        retry = self.start(self.issue(version, 2, 3, 'afternoon'), 'retry')
        second = self.step(retry, 'retry-2')
        third = self.step(retry, 'retry-3')
        self.assert_settlement('later', retry, second['actual_id'], third['actual_id'])
        segments = deepcopy(SOURCE['segments'])
        segments[1]['start_frame'] = 9
        new_release = self.publish(revision='r2', segments=segments, source='另一磁带')
        self.assertNotEqual(new_release['version_id'], version)
        self.reopen()
        self.assertEqual(self.call(f'/archives/{original["archive_id"]}'), original)
        self.assertEqual(self.close_session('close'), original)
        fresh = self.close_session('new-close')
        self.assertNotEqual(fresh['archive_id'], original['archive_id'])
        self.assertEqual([history['take']['take_id'] for history in fresh['facts']['takes']], [first])
        self.assertEqual([origin['actual_id'] for origin in fresh['facts']['origins']],
                         [played['actual_id'], second['actual_id'], third['actual_id']])
        self.assertEqual([item['status'] for item in fresh['facts']['claims']], ['settled', 'settled'])
        self.assertEqual(fresh['facts']['release'], release)
        self.assertEqual(fresh['facts']['origins'][1]['start_frame'], 8)

    def test_unknown_archive(self):
        self.error('/archives/404', None, 404, 'archive_not_found')
        self.error('/archives', {'session_id': 'unknown', 'request_id': 'close'}, 404, 'session_not_found')
        self.error('/archives/1', None, 404, 'archive_not_found')
