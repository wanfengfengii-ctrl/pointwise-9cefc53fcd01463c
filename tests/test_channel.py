from http.client import RemoteDisconnected

from tests.support import HttpCase


class ChannelTests(HttpCase):
    def test_ordered_play(self):
        version = self.publish()['version_id']
        take = self.start(self.issue(version, 2, 4), 'open')
        second = self.step(take, 'step-2')
        third = self.step(take, 'step-3')
        self.assertEqual([second['number'], third['number']], [2, 3])
        self.assertNotEqual(second['actual_id'], third['actual_id'])
        self.assertEqual(self.step(take, 'step-3'), third)
        self.assertEqual(self.history(take)['plays'], [second, third])
        self.assertEqual(self.history(take)['take']['status'], 'playing')

    def test_busy_then_stop(self):
        version = self.publish()['version_id']
        lineup = self.issue(version)
        first = self.start(lineup, 'open-1')
        self.assertEqual(self.start(lineup, 'open-1'), first)
        self.error('/takes', {'lineup_id': lineup, 'request_id': 'open-2'}, 409, 'channel_busy')
        played = self.step(first, 'step-1')
        stopped = self.stop(first, 'stop-1')
        self.assertEqual(stopped, {'request_id': 'stop-1', 'take_id': first,
                                   'status': 'aborted', 'played_count': 1})
        second = self.start(lineup, 'open-2')
        self.assertNotEqual(second, first)
        self.assertEqual(self.start(lineup, 'open-1'), first)
        self.assertEqual(self.stop(first, 'stop-1'), stopped)
        self.error(f'/takes/{first}/stop', {'request_id': 'stale'}, 409, 'take_ended')
        self.error('/takes/999/stop', {'request_id': 'unknown'}, 404, 'take_not_found')
        self.error('/takes', {'lineup_id': lineup, 'request_id': 'open-3'}, 409, 'channel_busy')
        self.assertEqual(self.step(second, 'second-step')['number'], 1)
        self.assertEqual(self.history(first)['plays'], [played])
        self.assertEqual(self.history(first)['take']['status'], 'aborted')

    def test_replay_after_finish(self):
        version = self.publish()['version_id']
        take = self.start(self.issue(version, 2, 2), 'open')
        with self.gated_step(take, 'last', 'after_actual', drop=True) as future:
            history = self.history(take)
            self.assertEqual(history['take']['status'], 'finished')
            self.assertEqual([item['number'] for item in history['plays']], [2])
        with self.assertRaises(RemoteDisconnected):
            future.result()
        self.reopen()
        self.assertEqual(self.step(take, 'last'), history['plays'][0])
        self.error(f'/takes/{take}/steps', {'request_id': 'extra'}, 409, 'take_ended')
        self.assertEqual(self.history(take), history)
        next_take = self.start(self.issue(version, 3, 3), 'next')
        self.error(f'/takes/{next_take}/steps', {'request_id': 'last'}, 409, 'request_conflict')
        self.assertEqual(self.history(next_take)['plays'], [])
