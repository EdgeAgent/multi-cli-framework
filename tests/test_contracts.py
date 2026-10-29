import unittest
from tempfile import TemporaryDirectory

from framework import contracts
from framework.state import StateStore


class TestContracts(unittest.TestCase):
    def test_conflict_flagged_before_coding(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            contracts.declare(store, "agent-a", files=["src/app.py"], apis=["/users"])
            contracts.declare(store, "agent-b", files=["src/app.py"], apis=["/orders"])
            conflicts = contracts.check_before_coding(store)
            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0]["item"], "src/app.py")

    def test_no_conflict_when_disjoint(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            contracts.declare(store, "agent-a", files=["src/a.py"])
            contracts.declare(store, "agent-b", files=["src/b.py"])
            self.assertEqual(contracts.check_before_coding(store), [])


if __name__ == "__main__":
    unittest.main()
