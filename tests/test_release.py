from copy import deepcopy
import json

from tests.support import HttpCase, SOURCE


class ReleaseTests(HttpCase):
    def test_fixed_lineup(self):
        release = self.publish()
        version = release['version_id']
        lineup_id = self.issue(version, 2, 4)
        lineup = self.call(f'/lineups/{lineup_id}')
        self.assertEqual((lineup['session_id'], lineup['version_id'], lineup['first'], lineup['last']),
                         ('morning', version, 2, 4))
        actual = [[item['number'], item['start_frame'], item['stop_frame']]
                  for item in lineup['segments']]
        expected = [[2, 8, 20], [3, 22, 36], [4, 36, 48]]
        self.assertEqual(actual, expected)
        self.assertEqual(self.call(f'/releases/{version}'), release)
        take_id = self.start(lineup_id, 'open')
        play = self.step(take_id, 'step')
        self.assertEqual(play['number'], 2)
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v1', 'input': {'source': SOURCE, 'window': [2, 4]},
            'expected': expected, 'actual': actual,
            'downstream_expected': 2, 'downstream_actual': play['number'],
            'code_paths': ['catalog/segments.py', 'catalog/release.py', 'program/windows.py',
                           'program/issue.py', 'channel/output.py'],
            'oracle': '逐行抄录原稿第 2、3、4 段的帧界，现场首段应为 2。',
        }, ensure_ascii=False))

    def test_invalid_source(self):
        base = SOURCE['segments']
        for index, changes in enumerate(({'number': True}, {'number': 1}, {'number': 0},
                                         {'start_frame': 7}, {'start_frame': -1}, {'stop_frame': 8},
                                         {'stop_frame': 49}, {'start_frame': 8.0}, {'name': None})):
            with self.subTest(changes=changes):
                segments = deepcopy(base)
                segments[1].update(changes)
                revision = f'bad-{index}'
                self.draft(revision=revision, segments=segments)
                self.error('/releases', {'recording_id': 'river', 'revision': revision}, 400, 'bad_segments')
        self.error('/drafts', {'recording_id': 'river', 'revision': 'missing'}, 400, 'bad_input')
        self.error('/releases/1', None, 404, 'version_not_found')
        self.assertEqual(self.publish()['version_id'], 1)

    def test_version_origin(self):
        first = self.publish()
        old_id = first['version_id']
        old_lineup = self.issue(old_id, 2, 4)
        segments = deepcopy(SOURCE['segments'])
        segments[1].update(name='重记渡口', start_frame=9, stop_frame=21)
        second = self.publish(revision='r2', source='磁带乙面', segments=segments)
        self.assertNotEqual(old_id, second['version_id'])
        self.reopen()
        self.assertEqual(self.call(f'/releases/{old_id}'), first)
        self.assertEqual(self.call(f'/releases/{old_id}/segments/2'),
                         {'number': 2, 'name': '渡船', 'start_frame': 8, 'stop_frame': 20})
        new_old_lineup = self.issue(old_id, 2, 4)
        for lineup in (old_lineup, new_old_lineup):
            self.assertEqual(self.call(f'/lineups/{lineup}')['segments'][0]['start_frame'], 8)
        self.assertEqual(self.call(f'/releases/{second["version_id"]}/segments/2')['start_frame'], 9)

    def test_missing_end(self):
        version = self.publish()['version_id']
        payload = {'session_id': 'morning', 'version_id': version, 'first': 2, 'last': 5}
        self.error('/lineups', payload, 400, 'bad_window')
        self.error('/lineups', {**payload, 'first': 5, 'last': 2}, 400, 'bad_window')
        self.error('/lineups', {**payload, 'first': True, 'last': 4}, 400, 'bad_window')
        self.error('/lineups/1', None, 404, 'lineup_not_found')
        self.error('/sessions/morning/claims/open', None, 404, 'session_not_found')
        later = self.publish(revision='r2')['version_id']
        self.assertEqual(self.issue(later, 2, 4), 1)
        self.error('/lineups', {**payload, 'last': 4}, 409, 'session_version_conflict')
        self.error('/lineups/2', None, 404, 'lineup_not_found')

    def test_missing_middle(self):
        sparse = [item for item in SOURCE['segments'] if item['number'] != 3]
        old = self.publish(segments=sparse)['version_id']
        newer = self.publish(revision='r2')['version_id']
        self.error(f'/releases/{old}/segments/3', None, 404, 'segment_not_found')
        self.error('/lineups', {'session_id': 'morning', 'version_id': old, 'first': 2, 'last': 4},
                   400, 'bad_window')
        self.error('/lineups/1', None, 404, 'lineup_not_found')
        self.assertEqual(self.issue(newer, 2, 4), 1)
