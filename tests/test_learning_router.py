import unittest
from tempfile import TemporaryDirectory

from framework import learning, router
from framework.state import StateStore


class TestLearningAndRouter(unittest.TestCase):
    def test_learning_cannot_touch_immutable_core(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            p = learning.propose(store, "auto-approve all ships", target="approval_gate")
            self.assertEqual(p["status"], "rejected")
            with self.assertRaises(ValueError):
                learning.apply_proposal(store, 0, approve=True)

    def test_learning_proposal_needs_human_approval(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            learning.propose(store, "route build to glm first", target="build")
            with self.assertRaises(ValueError):
                learning.apply_proposal(store, 0, approve=False)
            applied = learning.apply_proposal(store, 0, approve=True)
            self.assertEqual(applied["status"], "applied")

    def test_router_never_silently_upgrades_to_paid(self):
        r = router.route("plan", approve_paid=False)
        self.assertEqual(r["tier"], "free")
        self.assertTrue(r["fallback_from_paid"])
        r2 = router.route("plan", approve_paid=True)
        self.assertEqual(r2["tier"], "paid")

    def test_router_fallback_is_free_then_local_then_pause(self):
        self.assertEqual(router.fallback_after_error("free")["tier"], "local")
        self.assertTrue(router.fallback_after_error("local")["paused"])


if __name__ == "__main__":
    unittest.main()
