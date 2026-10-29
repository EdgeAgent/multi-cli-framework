"""Dashboard tests: localhost server, tabs page, state API, actions, kill, no approval bypass."""
import json, tempfile, threading, unittest, urllib.request, urllib.error
from framework import dashboard
from framework.state import StateStore

def _post(port, path, obj):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
        data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

class TestDashboard(unittest.TestCase):
    def setUp(self):
        self.store = StateStore(tempfile.mkdtemp())
        self.store.add_section("builder", role="builder", model="local")
        self.store.spawn_agent("builder", "agent-a", model="local")
        self.store.spawn_agent("builder", "agent-b", model="local")
        self.server = dashboard.create_server(self.store, port=0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close()

    def test_serves_tabs_page_localhost_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            html = r.read().decode()
        for tab in ("Watch", "Goals", "Tasks", "What's Next", "Cron", "Environments", "Help"):
            self.assertIn(tab, html)
        self.assertIn("127.0.0.1", html)
        self.assertIn("KILL SWITCH", html)
        self.assertIn("ship --approve --confirm", html)

    def test_state_endpoint_returns_agents_goals_tasks(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/state") as r:
            s = json.loads(r.read())
        self.assertIn("builder/agent-a", s["agents"])
        self.assertIn("goals", s); self.assertIn("tasks", s); self.assertIn("approvals", s)

    def test_agent_action_selected_only(self):
        code, _ = _post(self.port, "/api/agent/action", {"agent": "builder/agent-a", "action": "pause"})
        self.assertEqual(code, 200)
        agents = self.store.load()["agents"]
        self.assertEqual(agents["builder/agent-a"]["status"], "paused")
        self.assertEqual(agents["builder/agent-b"]["status"], "running")

    def test_kill_switch_endpoint_and_confirm(self):
        code, _ = _post(self.port, "/api/kill", {"confirm": "nope"})
        self.assertEqual(code, 400)
        self.assertEqual(self.store.load()["agents"]["builder/agent-a"]["status"], "running")
        code, _ = _post(self.port, "/api/kill", {"confirm": "KILL"})
        self.assertEqual(code, 200)
        self.assertTrue(all(a["status"] == "stopped" for a in self.store.load()["agents"].values()))

    def test_approval_never_bypassed_via_dashboard(self):
        code, body = _post(self.port, "/api/approve", {"candidate": "builder/agent-a"})
        self.assertEqual(code, 403)
        self.assertIn("ship --approve --confirm", json.dumps(body))

    def test_forms_create_environment_goal_task(self):
        code, env = _post(self.port, "/api/environment", {"title": "scout-env", "model": "local"})
        self.assertEqual(code, 200)
        self.assertIn("scout-env/agent-1", self.store.load()["agents"])
        code, _ = _post(self.port, "/api/goal", {"title": "Ship v1"})
        self.assertEqual(code, 200)
        self.assertEqual(self.store.load()["goals"][0]["title"], "Ship v1")
        code, _ = _post(self.port, "/api/task", {"title": "Write tests"})
        self.assertEqual(code, 200)

    def test_start_here_shown_when_empty(self):
        empty = StateStore(tempfile.mkdtemp())
        srv = dashboard.create_server(empty, port=0); port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
                html = r.read().decode()
            self.assertIn("Start Here", html)
        finally:
            srv.shutdown(); srv.server_close()

if __name__ == "__main__":
    unittest.main()
