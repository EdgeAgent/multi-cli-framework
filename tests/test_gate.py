import unittest

from framework.gate import GateBlocked, require_approval


class TestGate(unittest.TestCase):
    def test_ship_blocked_without_approval(self):
        with self.assertRaises(GateBlocked):
            require_approval("ship", "candidate-a", approve=False)

    def test_ship_blocked_with_wrong_confirm(self):
        with self.assertRaises(GateBlocked):
            require_approval("ship", "candidate-a", approve=True, confirm="wrong", expected_confirm="candidate-a")

    def test_ship_allowed_with_approval_and_confirm(self):
        require_approval("ship", "candidate-a", approve=True, confirm="candidate-a", expected_confirm="candidate-a")


if __name__ == "__main__":
    unittest.main()
