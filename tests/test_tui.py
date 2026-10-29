"""TUI renderer tests — pane layout, status, tombstones, no crashes."""
import tempfile
import unittest
from pathlib import Path

from framework import tui
from framework.orchestrator import MockAgent, run_parallel
from framework.state import StateStore


def _store():
    tmp = tempfile.mkdtemp()
    store = StateStore(tmp)
    store.add_section("builder", role="builder", model="local")
    store.spawn_agent("builder", "agent-a", model="glm-5.3-flash:free")
    store.spawn_agent("builder", "agent-b", model="qwen3-coder:free")
    return store


class TestTui(unittest.TestCase):
    def test_panes_show_name_model_status_cost_time(self):
        store = _store()
        run_parallel(store, "hello", [MockAgent("agent-a", "glm-5.3-flash:free"), MockAgent("agent-b", "qwen3-coder:free")], section="builder")
        text = tui.render_panes(store.load())
        self.assertIn("agent-a", text)
        self.assertIn("glm-5.3-flash:free", text)
        self.assertIn("agent-b", text)
        self.assertIn("cost:", text)
        self.assertIn("time:", text)
        # Two agent panes side by side: both names appear on the same screen.
        self.assertIn("BOSS", text)
        self.assertIn("LOG", text)

    def test_tombstone_and_other_panes_keep_running_after_delete(self):
        """Deleting a section mid-run must not crash the watch screen:
        its pane becomes a tombstone, other panes stay."""
        store = _store()
        store.add_section("scout", role="researcher", model="local")
        store.spawn_agent("scout", "agent-s", model="local")
        run_parallel(store, "hello", [MockAgent("agent-a", "local")], section="builder")
        # Simulate a mid-run delete: registry removal + tombstone.
        store.delete_section("scout")
        text = tui.render_panes(store.load())
        self.assertIn("TOMBSTONE", text)
        self.assertIn("scout", text)
        self.assertIn("agent-a", text)  # other pane kept running
        self.assertIn("kept running", text)

    def test_empty_state_renders_without_crash(self):
        store = StateStore(tempfile.mkdtemp())
        text = tui.render_panes(store.load())
        self.assertIn("BOSS", text)
        self.assertIn("no agents", text)

    def test_long_names_and_models_are_truncated_not_wrapped_broken(self):
        store = StateStore(tempfile.mkdtemp())
        store.add_section("builder", role="builder", model="local")
        store.spawn_agent("builder", "a" * 80, model="m" * 80)
        text = tui.render_panes(store.load(), width=100)
        for line in text.splitlines():
            # Box rows stay bounded (header separators are exactly width).
            self.assertLessEqual(len(line), 102, line)

    def test_tui_keys_are_explicit_actions_not_agent_typing(self):
        for key in ("q", "p", "r", "t", "s", "k", "a"):
            self.assertIn(key, tui.TUI_KEYS)
        store = _store()
        self.assertIn("never auto-approves", tui.apply_tui_key(store, "a"))
        self.assertIn("paused", tui.apply_tui_key(store, "p"))
        self.assertIn("resumed", tui.apply_tui_key(store, "r"))
        self.assertIn("takeover", tui.apply_tui_key(store, "t"))
        self.assertIn("KILL SWITCH", tui.apply_tui_key(store, "k"))

    def test_panes_render_is_deterministic_and_plain_text(self):
        store = _store()
        a = tui.render_panes(store.load())
        b = tui.render_panes(store.load())
        self.assertEqual(a, b)
        self.assertNotIn("\x1b[", a)  # no ANSI escapes in the capturable render


if __name__ == "__main__":
    unittest.main()
