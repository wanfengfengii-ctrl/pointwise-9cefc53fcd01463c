from http.client import RemoteDisconnected
import json

from handover.runtime import initialize_data
from tests.support import HttpCase, SOURCE


class ClaimTests(HttpCase):
    def test_join_after_start(self):
        version = self.publish()['version_id']
        take = self.start(self.issue(version), 'open')
        self.step(take, 's1')
        self.assert_pending(self.claim('listener', version, 2, 3))
        second = self.step(take, 's2')
        self.assert_pending(self.get_claim('listener'))
        third = self.step(take, 's3')
        self.assert_settlement('listener', take, second['actual_id'], third['actual_id'])
        self.assertEqual(self.history(take)['take']['status'], 'playing')
        self.assertEqual(self.call('/sessions/morning/claims/open'), [])

    def test_invalid_claim(self):
        segments = [item for item in SOURCE['segments'] if item['number'] != 3]
        version = self.publish(segments=segments)['version_id']
        payload = {'request_id': 'bad', 'version_id': version, 'first': 2, 'last': 4}
        self.error('/claims', payload, 400, 'bad_window')
        self.error('/claims', {**payload, 'first': 4, 'last': 2}, 400, 'bad_window')
        self.error('/claims', {**payload, 'first': True}, 400, 'bad_window')
        self.error('/claims', {**payload, 'version_id': 999}, 404, 'version_not_found')
        self.error('/claims/bad', None, 404, 'claim_not_found')
        self.assert_pending(self.claim('bad', version, 2, 2))

    def test_stop_with_partial_coverage(self):
        version = self.publish()['version_id']
        self.assert_pending(self.claim('short', version, 2, 2))
        self.assert_pending(self.claim('long', version, 2, 3))
        first = self.start(self.issue(version, 2, 4), 'first')
        second = self.step(first, 'first-2')
        self.stop(first, 'stop')
        original = self.assert_settlement('short', first, second['actual_id'])
        self.assert_pending(self.get_claim('long'))
        suffix = self.start(self.issue(version, 3, 3), 'suffix')
        self.step(suffix, 'suffix-3')
        self.assert_pending(self.get_claim('long'))
        self.assertEqual(self.get_claim('short'), original)
        self.assertEqual(self.history(first)['plays'], [second])
        self.assertEqual([item['request_id'] for item in self.call('/sessions/morning/claims/open')], ['long'])

    def test_full_retry_after_partial_takes(self):
        version = self.publish()['version_id']
        self.claim('listener', version, 2, 4)
        first = self.start(self.issue(version, 2, 4), 'first')
        before = [self.step(first, 'first-2'), self.step(first, 'first-3')]
        self.stop(first, 'stop')
        self.assert_pending(self.get_claim('listener'))
        second = self.start(self.issue(version, 4, 4), 'second')
        suffix = self.step(second, 'second-4')
        self.assert_pending(self.get_claim('listener'))
        third = self.start(self.issue(version, 2, 4), 'third')
        full = [self.step(third, f'third-{number}') for number in (2, 3, 4)]
        self.assert_settlement('listener', third, *(play['actual_id'] for play in full))
        self.assertEqual(self.history(first)['plays'], before)
        self.assertEqual(self.history(second)['plays'], [suffix])
        self.assertEqual(self.history(third)['plays'], full)

    def test_lost_actual_reply(self):
        version = self.publish()['version_id']
        first = self.start(self.issue(version), 'first')
        one = self.step(first, 'first-1')
        with self.gated_step(first, 'first-2', 'after_actual', drop=True) as future:
            before = self.history(first)['plays']
            self.assertEqual([item['number'] for item in before], [1, 2])
            self.assert_pending(self.claim('A', version, 2, 3))
            self.assert_pending(self.claim('B', version, 3, 3))
            three = self.step(first, 'first-3')
            self.stop(first, 'stop-first')
            self.assert_pending(self.get_claim('A'))
            b = self.assert_settlement('B', first, three['actual_id'])
        with self.assertRaises(RemoteDisconnected):
            future.result()
        self.reopen()
        self.assertEqual(self.step(first, 'first-2'), before[1])
        self.assertEqual(self.history(first)['plays'], [one, before[1], three])
        a_pending = self.claim('A', version, 2, 3)
        self.assert_pending(a_pending)
        self.error('/claims', {'request_id': 'A', 'version_id': version, 'first': 2, 'last': 4},
                   409, 'request_conflict')
        self.assertEqual(self.get_claim('A'), a_pending)
        retry = self.start(self.issue(version, 2, 3), 'retry')
        plays = [self.step(retry, 'retry-2'), self.step(retry, 'retry-3')]
        a = self.assert_settlement('A', retry, *(play['actual_id'] for play in plays))
        self.assertEqual(self.claim('B', version, 3, 3), b)
        self.assertEqual(self.history(first)['plays'], [one, before[1], three])
        self.assertEqual(self.history(retry)['plays'], plays)
        self.assertEqual([item['number'] for item in plays], [2, 3])
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v7.mixed_claims',
            'input': {'first_take': first, 'retry_take': retry, 'A': [2, 3], 'B': [3, 3],
                      'order': ['actual-2', 'admit-A', 'admit-B', 'actual-3', 'stop', 'retry-2', 'retry-3']},
            'expected': {'A': 'pending', 'B_take': first, 'B_actuals': [three['actual_id']]},
            'actual': {'A': a_pending['status'], 'B_take': b['settlement']['take_id'],
                       'B_actuals': b['settlement']['actual_ids']},
            'downstream_expected': {'take': retry, 'actuals': [item['actual_id'] for item in plays]},
            'downstream_actual': {'take': a['settlement']['take_id'], 'actuals': a['settlement']['actual_ids']},
            'code_paths': ['channel/output.py', 'channel/history.py', 'requests/admission.py',
                           'requests/fulfillment.py'],
            'oracle': '甲晚于第 2 段而乙早于第 3 段。只有第二遍能给甲完整履约。',
        }, ensure_ascii=False))

    def test_opposite_order(self):
        version = self.publish()['version_id']
        take = self.start(self.issue(version), 'open')
        first = self.step(take, 'first')
        with self.gated_step(take, 'second', 'before_actual') as future:
            self.assertEqual(self.history(take)['plays'], [first])
            self.assert_pending(self.claim('A', version, 2, 3))
        second = future.result()
        third = self.step(take, 'third')
        self.stop(take, 'stop')
        self.reopen()
        self.assert_settlement('A', take, second['actual_id'], third['actual_id'])

    def test_pending_recovery(self):
        version = self.publish()['version_id']
        lineup = self.issue(version, 2, 2)
        self.observer = lambda phase, key: (phase, key) in {
            ('after_admission', 'early'), ('before_admission', 'late'),
        }
        self.assert_pending(self.claim('early', version, 2, 2), 'pending_review')
        self.assert_pending(self.claim('late', version, 2, 2), 'pending_review')
        queue = self.call('/sessions/morning/claims/open')
        self.assertEqual([(item['request_id'], item['status']) for item in queue],
                         [('early', 'pending_review'), ('late', 'pending_review')])
        first = self.start(lineup, 'one')
        past = self.step(first, 'first-2')
        self.observer = None
        self.reopen()
        self.assert_settlement('early', first, past['actual_id'])
        self.assert_pending(self.claim('late', version, 2, 2))
        self.assertEqual(self.history(first)['plays'], [past])
        second = self.start(lineup, 'two')
        future = self.step(second, 'second-2')
        self.assert_settlement('late', second, future['actual_id'])
        self.assert_settlement('early', first, past['actual_id'])
        self.assertEqual(self.call('/sessions/morning/claims/open'), [])

    def test_argument_conflict_and_unknown_claim(self):
        version = self.publish()['version_id']
        other = self.publish(revision='r2')['version_id']
        original = self.claim('original', version, 2, 3)
        take = self.start(self.issue(version, 2, 3), 'open')
        actual = self.step(take, 'second')
        self.reopen()
        self.error('/claims/unknown', None, 404, 'claim_not_found')
        for wrong_version, wrong_last in ((version, 4), (other, 3)):
            self.error('/claims', {'request_id': 'original', 'version_id': wrong_version,
                                   'first': 2, 'last': wrong_last}, 409, 'request_conflict')
        self.assertEqual(self.claim('original', version, 2, 3), original)
        self.assertEqual(self.history(take)['plays'], [actual])
        self.assertEqual([item['request_id'] for item in self.call('/sessions/morning/claims/open')], ['original'])

    def test_init_resume(self):
        version = self.publish()['version_id']
        self.draft(revision='user-edit', source='接班人整理稿')
        take = self.start(self.issue(version, 2, 3), 'open')
        self.claim('listener', version, 2, 3)
        second = self.step(take, 'second')
        self.close_server()
        initialize_data(self.directory)
        initialize_data(self.directory)
        self.open_server()
        release = self.call('/releases', {'recording_id': 'river', 'revision': 'user-edit'})
        self.assertEqual(release['source'], '接班人整理稿')
        self.assertNotEqual(release['version_id'], version)
        self.assertEqual(self.step(take, 'second'), second)
        third = self.step(take, 'third')
        self.assert_settlement('listener', take, second['actual_id'], third['actual_id'])
        self.assertEqual(self.history(take)['plays'], [second, third])
