"""Skills + MCP + Brain + Goals/Tasks/Deliverables + Environments + Cron/Loops."""
import tempfile
import unittest
from pathlib import Path

from framework import brain, goals, mcp, scheduler, skills, tui
from framework.gate import GateBlocked
from framework.orchestrator import MockAgent, run_parallel
from framework.state import StateStore


def fresh_store():
    return StateStore(tempfile.mkdtemp())


class TestSkillsMcpBrain(unittest.TestCase):
    def test_skill_load_and_use_recorded(self):
        store = fresh_store()
        names = [s["name"] for s in skills.list_skills(store)]
        self.assertIn("code-review", names)
        self.assertIn("battle-judge", names)
        skill = skills.use_skill(store, "agent-a", "code-review")
        self.assertTrue(skill["steps"])
        self.assertEqual(brain.events(store, "skill_use")[0]["skill"], "code-review")

    def test_skill_add_from_file(self):
        store = fresh_store()
        src = Path(store.root) / "custom.md"
        src.write_text("# Custom Skill\nDoes a custom thing.\nTools: read\n- Step one.\n")
        added = skills.add_skill(store, str(src))
        self.assertEqual(added["name"], "custom")
        self.assertIn("custom", [s["name"] for s in skills.list_skills(store)])

    def test_mcp_call_logged_and_allow_list_enforced(self):
        store = fresh_store()
        mcp.add_server(store, "fs", tools=["read", "list"])
        result = mcp.call_tool(store, "fs", "read")
        self.assertTrue(result["mock"])
        self.assertEqual(brain.events(store, "mcp_call")[0]["tool"], "read")
        with self.assertRaises(ValueError):
            mcp.call_tool(store, "fs", "write")

    def test_mcp_dangerous_tool_gated(self):
        store = fresh_store()
        mcp.add_server(store, "mailer", tools=["send_email"])
        with self.assertRaises(GateBlocked):
            mcp.call_tool(store, "mailer", "send_email")
        # Brain recorded the block, and nothing was "sent".
        self.assertEqual(brain.events(store, "mcp_call_blocked")[0]["tool"], "send_email")
        self.assertEqual(brain.events(store, "mcp_call"), [])

    def test_brain_search_finds_skill_mcp_battle_events(self):
        store = fresh_store()
        skills.use_skill(store, "agent-a", "research")
        mcp.add_server(store, "fs", tools=["read"])
        mcp.call_tool(store, "fs", "read")
        brain.record(store, "battle", {"battle_id": "b1", "winner": "agent-a"})
        self.assertTrue(brain.search(store, "research"))
        self.assertTrue(brain.search(store, "mcp_call"))
        self.assertTrue(brain.search(store, "battle", event_type="battle"))
        self.assertEqual(brain.show(store, 1)["type"], "skill_use")

    def test_agent_run_includes_skills_mcp_brain_context(self):
        store = fresh_store()
        mcp.add_server(store, "fs", tools=["read"])
        # A prior run gives the next run Brain context to consult.
        run_parallel(store, "hello", [MockAgent("agent-a", "local")], section="builder")
        agent = MockAgent("agent-a", "local", skills=["code-review"], mcp_tools=["fs/read"])
        results = run_parallel(store, "hello again", [agent], section="builder")
        self.assertIn("code-review", results[0]["skills"])
        self.assertIn("read", results[0]["mcp_tools"])
        self.assertTrue(results[0]["brain_context"])  # past run events consulted

    def test_goals_tasks_deliverables_crud_and_whats_next(self):
        store = fresh_store()
        g = goals.add_goal(store, "Ship v1", progress=40)
        self.assertEqual(goals.set_goal_progress(store, g["id"], 100)["status"], "done")
        t = goals.add_task(store, "Write tests", owner="builder/agent-a", section="builder")
        self.assertEqual(goals.set_task_status(store, t["id"], "doing")["status"], "doing")
        goals.add_deliverable(store, "First deliverable")
        goals.add_deliverable(store, "Second deliverable")
        nxt = goals.whats_next(store)
        self.assertEqual([d["title"] for d in nxt], ["First deliverable", "Second deliverable"])
        goals.set_deliverable_status(store, nxt[0]["id"], "done")
        self.assertEqual(goals.whats_next(store)[0]["title"], "Second deliverable")

    def test_tui_tabs_render_goals_tasks_deliverables_cron(self):
        store = fresh_store()
        goals.add_goal(store, "Ship v1", progress=40)
        goals.add_task(store, "Write tests", owner="builder/agent-a")
        goals.add_deliverable(store, "First deliverable")
        scheduler.add_job(store, "nightly", "daily", "run tests")
        rendered = tui.render_tabs(store.load())
        for needle in ("GOALS", "TASKS", "WHAT'S NEXT", "CRON & LOOPS", "Ship v1", "Write tests",
                       "First deliverable", "nightly"):
            self.assertIn(needle, rendered)

    def test_add_environment_creates_runnable_section(self):
        store = fresh_store()
        env = goals.add_environment(store, "scout-env", model="local",
                                    skills=["research"], mcp_tools=["fs/read"])
        self.assertEqual(env["section"], "scout-env")
        self.assertTrue(Path(env["sandbox"]).exists())
        self.assertIn("scout-env", store.load()["sections"])
        self.assertIn("scout-env/agent-1", store.load()["agents"])
        # The environment's agent can actually run.
        results = run_parallel(store, "hello", [MockAgent("agent-1", "local")], section="scout-env")
        self.assertEqual(results[0]["status"], "done")

    def test_cron_schedule_parsing_and_next_run(self):
        self.assertEqual(scheduler.parse_schedule("every 60 minutes")["minutes"], 60)
        self.assertEqual(scheduler.parse_schedule("daily")["minutes"], 1440)
        self.assertEqual(scheduler.parse_schedule("0 9 * * *")["hour"], 9)
        with self.assertRaises(ValueError):
            scheduler.parse_schedule("every 0 minutes")
        with self.assertRaises(ValueError):
            scheduler.parse_schedule("0 9 1 * *")  # day field not * in skeleton
        with self.assertRaises(ValueError):
            scheduler.parse_schedule("whenever")
        store = fresh_store()
        job = scheduler.add_job(store, "nightly", "daily", "run tests")
        self.assertTrue(job["next_run"])
        self.assertEqual(scheduler.list_jobs(store)[0]["name"], "nightly")
        scheduler.delete_job(store, job["id"])
        self.assertEqual(scheduler.list_jobs(store), [])

    def test_loop_until_success_stops_on_success(self):
        store = fresh_store()
        calls = []

        def task(i):
            calls.append(i)
            return {"status": "PASS" if i == 1 else "FAIL"}

        summary = scheduler.run_loop(store, task, mode="until_success", max_iterations=5)
        self.assertEqual(summary["outcome"], "success")
        self.assertEqual(calls, [0, 1])

    def test_loop_gated_blocks_auto_ship_each_iteration(self):
        store = fresh_store()
        summary = scheduler.run_loop(store, lambda i: {"status": "PASS"},
                                     mode="gated", max_iterations=3,
                                     gated_action="ship", approve=False)
        self.assertEqual(summary["outcome"], "gate_blocked")
        self.assertEqual(brain.events(store, "loop")[0]["outcome"], "gate_blocked")

    def test_kill_stops_loops(self):
        store = fresh_store()
        store.kill_all()
        summary = scheduler.run_loop(store, lambda i: {"status": "PASS"},
                                     mode="repeat", max_iterations=3)
        self.assertEqual(summary["outcome"], "killed")
        self.assertEqual(summary["iterations"], [])


if __name__ == "__main__":
    unittest.main()
