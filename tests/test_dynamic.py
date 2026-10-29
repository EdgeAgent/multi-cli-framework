import unittest
from tempfile import TemporaryDirectory

from framework.sandbox import archive_sandbox, create_sandbox, wipe_sandbox
from framework.state import StateStore


class TestDynamic(unittest.TestCase):
    def test_delete_archives_not_wipes_by_default(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            store.add_section("builder")
            store.spawn_agent("builder", "a1")
            create_sandbox(store, "builder", "a1")
            archive = archive_sandbox(store, "builder", "a1", reason="test delete")
            self.assertTrue(archive.exists())
            # Original sandbox still exists until an explicit wipe — delete != wipe.
            self.assertTrue((store.dir / "sandboxes" / "builder" / "a1").exists())
            store.delete_section("builder")
            self.assertNotIn("builder", store.load()["sections"])

    def test_wipe_requires_exact_confirm(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            store.add_section("builder")
            create_sandbox(store, "builder", "a1")
            self.assertFalse(wipe_sandbox(store, "builder", confirm="wrong"))
            self.assertTrue((store.dir / "sandboxes" / "builder").exists())
            self.assertTrue(wipe_sandbox(store, "builder", confirm="builder"))
            self.assertFalse((store.dir / "sandboxes" / "builder").exists())

    def test_kill_switch_stops_all(self):
        with TemporaryDirectory() as tmp:
            store = StateStore(tmp)
            store.add_section("builder")
            store.spawn_agent("builder", "a1")
            store.kill_all()
            state = store.load()
            self.assertTrue(state["killed"])
            self.assertEqual(state["agents"]["builder/a1"]["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
