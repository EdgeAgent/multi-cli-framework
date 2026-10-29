"""Startup menu tests: brand, routing, safety, dashboard parity."""
import html
import tempfile
import unittest

from framework import dashboard, menu
from framework.state import StateStore


class MenuTest(unittest.TestCase):
    def setUp(self):
        self.store = StateStore(tempfile.mkdtemp())

    def test_menu_renders_brand_all_options_and_hermes_pattern_footer(self):
        text = menu.render_menu(self.store.load())
        self.assertIn("BATTLE COURT", text)
        self.assertIn("Parallel agents. Judged. Learned from. Never auto-shipped.", text)
        self.assertIn("skeleton v0.1.0-skeleton", text)
        self.assertIn("Local-only", text)
        for number, label, _action, _desc in menu.MENU_ITEMS:
            self.assertIn(label, text)
            self.assertIn(f"{number:>2}.", text)
        self.assertIn("Kill Switch", text)
        self.assertIn("Quit", text)
        # Hermes-pattern nod, honestly labelled — not a claim to be Hermes.
        self.assertIn("Powered by the Hermes pattern", text)
        self.assertIn("not Hermes itself", text)
        self.assertNotIn("Hermes logo", text.replace("no Hermes code or logo is used here", ""))

    def test_route_covers_all_numbers_and_quit(self):
        actions = {menu.route(n)["action"] for n, _l, _a, _d in menu.MENU_ITEMS}
        self.assertEqual(actions, {"watch", "dashboard", "goals", "tasks",
                                   "deliverables", "cron", "environments",
                                   "battle", "skills_mcp", "brain", "help"})
        self.assertEqual(menu.route("0")["action"], "quit")
        self.assertEqual(menu.route("99")["action"], "unknown")

    def test_choosing_a_number_routes_to_the_right_action(self):
        self.assertEqual(menu.dispatch(self.store, "3")["action"], "goals")
        self.assertEqual(menu.dispatch(self.store, "5")["action"], "deliverables")
        self.assertEqual(menu.dispatch(self.store, "8")["action"], "battle")
        self.assertEqual(menu.dispatch(self.store, "11")["action"], "help")
        self.assertIn("Watch", menu.dispatch(self.store, "1")["label"])
        dash = menu.dispatch(self.store, "2")
        self.assertEqual(dash["action"], "dashboard")
        self.assertIn("127.0.0.1:8767", dash["next_step"])

    def test_menu_loop_quits_cleanly_and_unknown_reprompts(self):
        inputs = iter(["99", "0"])
        out = []
        rc = menu.run_menu_loop(self.store, input_fn=lambda _p: next(inputs),
                                print_fn=lambda s: out.append(s))
        self.assertEqual(rc, 0)
        self.assertTrue(any("Unknown menu choice" in s for s in out))

    def test_menu_never_approves_or_ships(self):
        text = menu.render_menu(self.store.load())
        # The only ship mention is the safety note naming the CLI command.
        self.assertIn("never approves, ships", text)
        for choice in [str(i) for i in range(1, 12)]:
            result = menu.dispatch(self.store, choice)
            self.assertNotIn(result["action"], ("ship", "approve"))

    def test_kill_switch_needs_explicit_confirmation(self):
        self.store.add_section("builder")
        self.store.spawn_agent("builder", "agent-a")
        prompt = menu.dispatch(self.store, "K")
        self.assertIn("KILL", prompt["message"])
        self.assertNotEqual(self.store.load()["agents"]["builder/agent-a"]["status"], "stopped")
        done = menu.dispatch(self.store, "K", confirm="KILL")
        self.assertIn("confirmed", done["message"])
        self.assertEqual(self.store.load()["agents"]["builder/agent-a"]["status"], "stopped")

    def test_dashboard_home_shows_same_menu_options(self):
        self.assertIn("startup-menu", dashboard.PAGE)
        page = html.unescape(dashboard.PAGE)  # "&amp;" in HTML is "&" in the label
        for number, label, _action, _desc in menu.MENU_ITEMS:
            self.assertIn(f"{number}. {label}", page)
        state = dashboard.state_view(self.store)
        self.assertEqual(
            [(m["number"], m["label"]) for m in state["menu"]],
            [(n, l) for n, l, _a, _d in menu.MENU_ITEMS])


if __name__ == "__main__":
    unittest.main()
