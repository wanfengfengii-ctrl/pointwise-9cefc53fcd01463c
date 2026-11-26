"""Prepare a three-session listening day through the original HTTP routes."""
import json
import unittest

from tests.support import HttpCase


def prepare_day(case):
    version = case.publish()["version_id"]
    lineups = {session: case.issue(version, 2, 3, session=session)
               for session in ("morning", "afternoon", "outside")}
    lineups["morning-short"] = case.issue(version, 2, 2, session="morning")
    case.assert_pending(case.claim("short", version, 2, 2))
    case.assert_pending(case.claim("long", version, 2, 3))
    old = case.close_session("morning-copy")
    return version, lineups, old


def play_window(case, lineup, key, *numbers):
    take = case.start(lineup, key)
    plays = [case.step(take, f"{key}-{number}") for number in numbers]
    return take, plays


class TransferFixtureSmoke(HttpCase):
    def test_original_evidence(self):
        version, lineups, old = prepare_day(self)
        recorded = {claim["request_id"]: claim["status"] for claim in old["facts"]["claims"]}
        self.assertEqual(recorded, {"short": "pending", "long": "pending"})
        take, plays = play_window(self, lineups["morning-short"], "morning-short", 2)
        history = self.history(take)
        self.assertEqual(history["take"]["version_id"], version)
        self.assertEqual(history["take"]["session_id"], "morning")
        self.assertEqual(history["plays"], plays)
        self.assertEqual([play["number"] for play in plays], [2])
        archive_id = old["archive_id"]
        self.assertEqual(self.call(f"/archives/{archive_id}"), old)
        print(json.dumps({"archive_id": archive_id, "frozen_claims": recorded,
                          "later_morning_plays": plays}, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
