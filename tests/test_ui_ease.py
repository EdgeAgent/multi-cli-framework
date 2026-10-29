"""UI ease tests: help, menu bar, selection, empty state, plain status, filter, static fallback."""
import tempfile, unittest
from framework import tui
from framework.state import StateStore

def _store():
    s = StateStore(tempfile.mkdtemp())
    s.add_section("builder", role="builder", model="local")
    s.spawn_agent("builder", "agent-a", model="glm-5.3-flash:free")
    s.spawn_agent("builder", "agent-b", model="qwen3-coder:free")
    return s

class TestUiEase(unittest.TestCase):
    def test_help_contains_all_keys_and_tabs(self):
        h = tui.HELP_TEXT
        for k in ("P = Pause", "R = Resume", "T = Take over", "S = Stop", "K = Kill Switch", "A = Approval", "?", "j/k", "1-9", "/"):
            self.assertIn(k, h)
        for tab in tui.MENU_TABS:
            self.assertIn(tab, h)
        self.assertIn("ship --approve --confirm", h)

    def test_menu_bar_contains_all_tabs_and_bottom_bar_plain_words(self):
        bar = tui.render_menu_bar("Watch")
        for tab in tui.MENU_TABS:
            self.assertIn(tab, bar)
        bottom = tui.render_bottom_bar("Watch")
        self.assertIn("Pause selected agent", bottom)
        self.assertIn("KILL SWITCH", bottom)
        self.assertIn("Help", bottom)

    def test_select_agent_acts_on_selected_only(self):
        store = _store()
        out = tui.apply_tui_key(store, "p", selected="builder/agent-a")
        self.assertIn("builder/agent-a", out)
        st = store.load()["agents"]
        self.assertEqual(st["builder/agent-a"]["status"], "paused")
        self.assertEqual(st["builder/agent-b"]["status"], "running")  # untouched
        # resume + takeover + stop, selected only
        tui.apply_tui_key(store, "r", selected="builder/agent-a")
        self.assertEqual(store.load()["agents"]["builder/agent-a"]["status"], "running")
        tui.apply_tui_key(store, "t", selected="builder/agent-b")
        self.assertEqual(store.load()["agents"]["builder/agent-b"]["status"], "takeover")
        self.assertEqual(store.load()["agents"]["builder/agent-a"]["status"], "running")
        tui.apply_tui_key(store, "s", selected="builder/agent-a")
        self.assertEqual(store.load()["agents"]["builder/agent-a"]["status"], "stopped")

    def test_pause_all_needs_confirmation(self):
        store = _store()
        out = tui.apply_tui_key(store, "P", confirm_all=False)
        self.assertIn("confirm", out.lower())
        self.assertEqual(store.load()["agents"]["builder/agent-a"]["status"], "running")
        tui.apply_tui_key(store, "P", confirm_all=True)
        self.assertEqual(store.load()["agents"]["builder/agent-a"]["status"], "paused")

    def test_select_by_number(self):
        store = _store()
        self.assertEqual(tui.select_agent(store.load(), 1), "builder/agent-a")
        self.assertEqual(tui.select_agent(store.load(), 2), "builder/agent-b")
        self.assertIsNone(tui.select_agent(store.load(), 9))

    def test_empty_state_shows_start_here(self):
        store = StateStore(tempfile.mkdtemp())
        text = tui.render_panes(store.load())
        self.assertIn("START HERE", text)
        self.assertIn("environment add scout-env", text)
        self.assertIn('run "hello"', text)
        self.assertIn("dashboard", text)

    def test_plain_language_status(self):
        self.assertIn("no action needed", tui.plain_status("running", "agent-a"))
        self.assertIn("press R to resume", tui.plain_status("paused"))
        self.assertIn("ship --approve --confirm", tui.APPROVAL_NOTE)
        store = _store()
        text = tui.render_panes(store.load())
        self.assertIn("no action needed", text)

    def test_filter_narrows_panes(self):
        store = _store()
        text = tui.render_panes(store.load(), filter_term="agent-a")
        self.assertIn("agent-a", text)
        self.assertNotIn("agent-b", text)
        panes = tui.build_panes(store.load())["agents"]
        self.assertEqual(len(tui.filter_panes(panes, "agent-b")), 1)

    def test_static_fallback_includes_menu_help_cli_actions(self):
        store = _store()
        text = tui.render_static_fallback(store.load())
        for tab in tui.MENU_TABS:
            self.assertIn(tab, text)
        self.assertIn("HELP", text)
        self.assertIn("run.py agent pause builder agent-a", text)
        self.assertIn("127.0.0.1:8767", text)
        self.assertIn("dashboard", text)

    def test_help_render_and_approval_never_bypasses(self):
        store = _store()
        self.assertIn("HELP", tui.render_panes(store.load(), show_help=True))
        self.assertIn("never auto-approves", tui.apply_tui_key(store, "a"))

if __name__ == "__main__":
    unittest.main()
