import unittest
from tempfile import TemporaryDirectory

from framework.court import judge
from framework.orchestrator import MockAgent
from framework.state import StateStore


def _run(tmp, fail_a=False, fail_b=False, no_ev_a=False):
    store = StateStore(tmp)
    a = MockAgent("candidate-a", "m-a", fail=fail_a, no_evidence=no_ev_a)
    b = MockAgent("candidate-b", "m-b", fail=fail_b)
    ra = a.run(store, "battle", "task")
    rb = b.run(store, "battle", "task")
    return store, [ra, rb]


class TestCourt(unittest.TestCase):
    def test_failing_side_cannot_win(self):
        with TemporaryDirectory() as tmp:
            store, cands = _run(tmp, fail_a=True)
            with self.assertRaises(ValueError):
                judge(store, "b1", cands, pick="a")

    def test_no_evidence_means_no_win_fail_closed(self):
        with TemporaryDirectory() as tmp:
            store, cands = _run(tmp, no_ev_a=True)
            with self.assertRaises(ValueError):
                judge(store, "b1", cands, pick="a")

    def test_winner_staged_not_shipped_loser_archived(self):
        with TemporaryDirectory() as tmp:
            store, cands = _run(tmp)
            record = judge(store, "b1", cands, pick="a")
            self.assertEqual(record["winner"], "candidate-a")
            self.assertEqual(record["loser"], "candidate-b")
            self.assertFalse(record["shipped"])
            self.assertIsNotNone(record["staged"])
            self.assertEqual(len(record["archived"]), 1)

    def test_tie_archives_both(self):
        with TemporaryDirectory() as tmp:
            store, cands = _run(tmp)
            record = judge(store, "b1", cands, pick="none")
            self.assertEqual(record["outcome"], "no_winner")
            self.assertIsNone(record["winner"])
            self.assertEqual(len(record["archived"]), 2)


if __name__ == "__main__":
    unittest.main()
