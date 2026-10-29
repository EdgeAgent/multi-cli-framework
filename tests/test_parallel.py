import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from framework.orchestrator import MockAgent, run_parallel
from framework.state import StateStore


class TestParallelIsolation(unittest.TestCase):
    def test_agents_do_not_overwrite_each_other(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            agents = [MockAgent("agent-a", "model-a"), MockAgent("agent-b", "model-b")]
            results = run_parallel(store, "hello", agents, section="default")
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r["status"] == "done" for r in results))
            a = Path(results[0]["sandbox"]) / "output.txt"
            b = Path(results[1]["sandbox"]) / "output.txt"
            self.assertNotEqual(results[0]["sandbox"], results[1]["sandbox"])
            self.assertIn("agent-a", a.read_text())
            self.assertIn("agent-b", b.read_text())
            self.assertNotIn("agent-b", a.read_text())

    def test_one_dead_agent_does_not_kill_wave(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            agents = [MockAgent("good", "m", fail=False), MockAgent("bad", "m", fail=True)]
            results = run_parallel(store, "hello", agents, section="default")
            statuses = {r["agent"]: r["status"] for r in results}
            self.assertEqual(statuses["good"], "done")
            self.assertEqual(statuses["bad"], "failed")


if __name__ == "__main__":
    unittest.main()
