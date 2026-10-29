"""Local web dashboard — the easy UI, especially on Windows.

`run.py dashboard` starts a stdlib-only HTTP server bound to
127.0.0.1 ONLY (no external access, no auth needed because it is
localhost-only — say so plainly on the page). It serves ONE static
HTML page (no build step, no JS framework) with:

- Tabs you can CLICK: Watch | Goals | Tasks | What's Next |
  Cron & Loops | Environments | Help
- Agent panes you can click to select, with buttons: Pause / Resume /
  Take over / Stop, per SELECTED agent only, plus a big red Kill
  Switch button with a two-step confirm (first click arms it, second
  click fires it — never one accidental click).
- Approval queue shown plainly, with the EXACT ship command. The
  dashboard NEVER approves anything: POST /api/approve always
  returns 403 with the CLI command. Approval is CLI-only, by design.
- Forms: Add Environment (name, model, skills, MCP tools) creating
  section + agent + sandbox in one click; Add Goal / Task /
  Deliverable / Cron, plain-language status, search/filter box.
- Start Here empty-state guide when no agents exist.

The dashboard reads/writes the SAME <root>/.framework/state.json
as the CLI and TUI — no second database, so all three stay in sync.
Refresh the page (or use the Refresh button) to see CLI/TUI changes.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import goals, menu, scheduler, tui
from .state import StateStore

DEFAULT_PORT = 8767
LOCAL_ONLY_NOTE = (
    "Local-only: this dashboard binds 127.0.0.1 only. Nothing leaves "
    "your machine, and no login is needed because only this computer "
    "can reach it. Never expose this port to the internet."
)

PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<title>Battle Court — Dashboard</title>
<style>
body{font-family:system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#111}
button{padding:8px 14px;margin:4px;cursor:pointer}
button.kill{background:#c00;color:#fff;font-weight:bold}
button.kill.armed{background:#600}
.tab{display:none}.tab.active{display:block}
.tabs button.active{font-weight:bold;text-decoration:underline}
.agent{border:2px solid #ccc;padding:10px;margin:8px 0;cursor:pointer}
.agent.selected{border-color:#000;background:#eef}
form{border:1px solid #ddd;padding:12px;margin:12px 0}
input,select{margin:4px;padding:6px}
.note{background:#fff8cc;padding:10px;border:1px solid #dd0}
</style></head><body>
<h1>Battle Court — Dashboard</h1>
<p class="note">LOCAL_ONLY_NOTE</p>
<p><strong>Approval rule:</strong> this dashboard NEVER approves a ship.
To approve, run in a terminal: <code>ship --approve --confirm &lt;candidate&gt;</code></p>
<div id="startup-menu"><h2>⚖ BATTLE COURT — Startup Menu</h2>
<p><strong>Parallel agents. Judged. Learned from. Never auto-shipped.</strong> &nbsp; Version: skeleton v0.1.0-skeleton &nbsp;·&nbsp; Local-only &nbsp;·&nbsp; Mock agents, $0 spend</p>
<p>Pick a section — same numbering and order as the <code>run.py menu</code> startup menu:</p>
<ol>
<li><button onclick="document.querySelector('[data-tab=watch]').click()">1. Watch live</button></li>
<li><button onclick="document.querySelector('[data-tab=watch]').click()">2. Dashboard</button> (you are here — this page)</li>
<li><button onclick="document.querySelector('[data-tab=goals]').click()">3. Goals</button></li>
<li><button onclick="document.querySelector('[data-tab=tasks]').click()">4. Tasks</button></li>
<li><button onclick="document.querySelector('[data-tab=next]').click()">5. What's Next</button></li>
<li><button onclick="document.querySelector('[data-tab=cron]').click()">6. Cron &amp; Loops</button></li>
<li><button onclick="document.querySelector('[data-tab=envs]').click()">7. Environments</button></li>
<li><button onclick="document.querySelector('[data-tab=watch]').click()">8. Battle Court</button> (run in a terminal: <code>battle --task &lt;task&gt; --pick a|b|none</code> — winner staged only, never auto-shipped)</li>
<li><button onclick="document.querySelector('[data-tab=help]').click()">9. Skills &amp; MCP</button> (see Help, and run <code>skill list</code> / <code>mcp list</code>)</li>
<li><button onclick="document.querySelector('[data-tab=help]').click()">10. Brain</button> (run <code>brain list</code> in a terminal)</li>
<li><button onclick="document.querySelector('[data-tab=help]').click()">11. Help</button></li>
<li><button class="kill" onclick="kill(this)">K. Kill Switch — stop everything (click twice to confirm)</button></li>
<li><button onclick="alert('Close this tab to leave the dashboard. Framework state is kept.')">0. Quit</button></li>
</ol>
<p class="note">Powered by the Hermes pattern — router + workers + Brain + approval gate. This is Battle Court, not Hermes itself: no Hermes code or logo is used here.</p>
<p><strong>Safety:</strong> this menu never approves, ships, sends, pays, deletes, or merges. Approval is CLI-only: <code>ship --approve --confirm &lt;candidate&gt;</code></p></div>
<div class="tabs">
<button data-tab="watch" class="active">Watch</button>
<button data-tab="goals">Goals</button>
<button data-tab="tasks">Tasks</button>
<button data-tab="next">What's Next</button>
<button data-tab="cron">Cron &amp; Loops</button>
<button data-tab="envs">Environments</button>
<button data-tab="help">Help</button>
</div>
<p><input id="search" placeholder="Search / filter agents and tasks by name or status">
<button onclick="load()">Refresh</button></p>
<div id="start-here" style="display:none" class="note"><h2>Start Here — nothing exists yet</h2>
<ol><li>Add an environment below (name, model, skills, MCP tools) — one click creates section + agent + sandbox.</li>
<li>Run something: <code>run "hello"</code></li>
<li>Come back here and click an agent to select it, then Pause / Resume / Take over / Stop.</li></ol></div>
<div id="watch" class="tab active"><h2>Watch — click an agent to select it</h2><div id="agents"></div>
<p>Selected: <b id="selected">none</b></p>
<button onclick="act('pause')">Pause selected agent</button>
<button onclick="act('resume')">Resume selected agent</button>
<button onclick="act('takeover')">Take over selected agent</button>
<button onclick="act('stop')">Stop selected agent</button>
<button id="killbtn" class="kill" onclick="kill(this)">KILL SWITCH — stop everything</button>
<h3>Approval queue</h3><div id="approvals"></div>
<h3>Log</h3><pre id="log"></pre></div>
<div id="goals" class="tab"><h2>Goals</h2><div id="goals-list"></div>
<form onsubmit="return addItem(event,'goal')"><input name="title" placeholder="Goal title" required><input name="progress" type="number" value="0" min="0" max="100"><button>Add Goal</button></form></div>
<div id="tasks" class="tab"><h2>Tasks</h2><div id="tasks-list"></div>
<form onsubmit="return addItem(event,'task')"><input name="title" placeholder="Task title" required><input name="owner" placeholder="Owner agent (optional)"><button>Add Task</button></form></div>
<div id="next" class="tab"><h2>What's Next — deliverables in due order</h2><div id="next-list"></div>
<form onsubmit="return addItem(event,'deliverable')"><input name="title" placeholder="Deliverable title" required><button>Add Deliverable</button></form></div>
<div id="cron" class="tab"><h2>Cron &amp; Loops</h2><div id="cron-list"></div>
<form onsubmit="return addItem(event,'cron')"><input name="title" placeholder="Job name" required><input name="schedule" placeholder="every 60 minutes" required><input name="task" placeholder="Task" required><button>Add Cron Job</button></form></div>
<div id="envs" class="tab"><h2>Environments — one click: section + agent + sandbox</h2><div id="envs-list"></div>
<form onsubmit="return addItem(event,'environment')"><input name="title" placeholder="Environment name" required><input name="model" placeholder="Model (default: local)"><input name="skills" placeholder="Skills, comma-separated"><input name="mcp" placeholder="MCP tools, comma-separated"><button>Add Environment</button></form></div>
<div id="help" class="tab"><h2>Help</h2><pre id="helptext"></pre></div>
<script>
let selected=null, killArmed=false;
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{
 document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));
 document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
 b.classList.add('active'); document.getElementById(b.dataset.tab).classList.add('active');});
document.getElementById('search').oninput=load;
async function api(path,body){
 const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
 const j=await r.json().catch(()=>({})); if(!r.ok) alert(j.error||('Error '+r.status)); return j;}
function plain(s){return {running:'Working — no action needed',paused:'Paused — press Resume to restart',stopped:'Stopped — sandbox frozen, not deleted',done:'Done — no action needed',failed:'Failed — check the log, then re-run',takeover:'You took over — waiting on you',waiting:'Waiting to start — no action needed yet'}[s]||s;}
async function load(){
 const s=await api('/api/state'); const q=(document.getElementById('search').value||'').toLowerCase();
 document.getElementById('start-here').style.display=Object.keys(s.agents||{}).length?'none':'block';
 document.getElementById('helptext').textContent=s.help||'';
 const agentsEl=document.getElementById('agents'); agentsEl.innerHTML='';
 Object.keys(s.agents||{}).sort().filter(k=>!q||k.toLowerCase().includes(q)||(s.agents[k].status||'').includes(q)).forEach(k=>{
  const a=s.agents[k], d=document.createElement('div'); d.className='agent'+(selected===k?' selected':'');
  d.innerHTML='<b>'+k+'</b> — '+a.model+' — '+plain(a.status);
  d.onclick=()=>{selected=k; document.getElementById('selected').textContent=k; load();}; agentsEl.appendChild(d);});
 document.getElementById('selected').textContent=selected||'none';
 document.getElementById('approvals').innerHTML=(s.approvals||[]).length? s.approvals.map(x=>'<p>'+x+' — approve ONLY with: <code>ship --approve --confirm '+x+'</code></p>').join('') : '<p>No candidates waiting for approval.</p>';
 document.getElementById('log').textContent=(s.log||[]).join('\\n');
 document.getElementById('goals-list').innerHTML=(s.goals||[]).map(g=>'#'+g.id+' '+g.title+' — '+g.progress+'% ['+g.status+']').join('<br>')||'(no goals yet)';
 document.getElementById('tasks-list').innerHTML=(s.tasks||[]).filter(t=>!q||t.title.toLowerCase().includes(q)).map(t=>'#'+t.id+' '+t.title+' — '+t.status).join('<br>')||'(no tasks yet)';
 document.getElementById('next-list').innerHTML=(s.deliverables||[]).map(d=>'#'+d.id+' '+d.title+' — '+d.status).join('<br>')||'(no deliverables yet)';
 document.getElementById('cron-list').innerHTML=(s.cron_jobs||[]).map(j=>'#'+j.id+' '+j.name+' — '+j.schedule+' · next: '+(j.next_run||'—')+' · '+j.status).join('<br>')||'(no cron jobs yet)';
 document.getElementById('envs-list').innerHTML=Object.keys(s.environments||{}).map(n=>n+': '+(s.environments[n].agent||'')).join('<br>')||'(no environments yet)';}
async function act(action){ if(!selected){alert('Click an agent first to select it.');return;}
 await api('/api/agent/action',{agent:selected,action}); load();}
async function kill(btn){ const b=btn||document.getElementById('killbtn');
 if(!killArmed){killArmed=true; b.textContent='Click again to CONFIRM Kill Switch'; b.classList.add('armed'); return;}
 await api('/api/kill',{confirm:'KILL'}); killArmed=false; b.textContent='KILL SWITCH — stop everything'; b.classList.remove('armed'); load();}
async function addItem(e,kind){ e.preventDefault(); const f=new FormData(e.target), o={};
 f.forEach((v,k)=>o[k]=v); const map={goal:'/api/goal',task:'/api/task',deliverable:'/api/deliverable',cron:'/api/cron',environment:'/api/environment'};
 await api(map[kind],o); e.target.reset(); load(); return false;}
load();
</script></body></html>
""".replace("LOCAL_ONLY_NOTE", LOCAL_ONLY_NOTE)


def approval_queue(state: dict) -> list[str]:
    """Staged battle winners waiting on the gate — never auto-shipped."""
    out = []
    for battle in state.get("battles", []):
        if battle.get("winner") and not battle.get("shipped"):
            out.append(battle["winner"])
    return out


def state_view(store: StateStore) -> dict:
    state = store.load()
    panes = tui.build_panes(state)
    return {
        "sections": state["sections"],
        "agents": state["agents"],
        "goals": state["goals"],
        "tasks": state["tasks"],
        "deliverables": tui.whats_next_state(state),
        "cron_jobs": state.get("cron_jobs", []),
        "environments": state.get("environments", {}),
        "approvals": approval_queue(state),
        "log": panes["log"],
        "killed": state.get("killed", False),
        "help": tui.HELP_TEXT,
        "menu": [{"number": n, "label": l, "action": a} for n, l, a, _d in menu.MENU_ITEMS],
    }


def make_handler(store: StateStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        def _send(self, code: int, obj) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except (json.JSONDecodeError, ValueError):
                return {}

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/state":
                self._send(200, state_view(store))
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            path = urlparse(self.path).path
            data = self._body()
            try:
                if path == "/api/agent/action":
                    agent = data.get("agent", "")
                    section, _, name = agent.partition("/")
                    action = data.get("action", "")
                    mapping = {"pause": "paused", "resume": "running",
                               "takeover": "takeover", "stop": "stopped"}
                    if agent not in store.load()["agents"] or action not in mapping:
                        return self._send(400, {"error": "unknown agent or action"})
                    store.set_agent_status(section, name, mapping[action])
                    return self._send(200, {"ok": True, "agent": agent, "status": mapping[action]})
                if path == "/api/kill":
                    if data.get("confirm") != "KILL":
                        return self._send(400, {"error": "kill switch needs confirm='KILL'"})
                    store.kill_all()
                    return self._send(200, {"ok": True, "killed": True})
                if path == "/api/approve":
                    # NEVER approve via the dashboard. The gate is CLI-only.
                    return self._send(403, {
                        "error": "Dashboard never approves. Run: ship --approve --confirm <candidate>",
                        "command": "ship --approve --confirm <candidate>",
                    })
                if path == "/api/environment":
                    env = goals.add_environment(
                        store, data.get("title") or data.get("name", ""),
                        model=data.get("model") or "local",
                        skills=[s.strip() for s in (data.get("skills") or "").split(",") if s.strip()],
                        mcp_tools=[s.strip() for s in (data.get("mcp") or "").split(",") if s.strip()])
                    return self._send(200, env)
                if path == "/api/goal":
                    return self._send(200, goals.add_goal(store, data.get("title", ""),
                                                          progress=int(data.get("progress") or 0)))
                if path == "/api/task":
                    return self._send(200, goals.add_task(store, data.get("title", ""),
                                                          owner=data.get("owner", "")))
                if path == "/api/deliverable":
                    return self._send(200, goals.add_deliverable(store, data.get("title", "")))
                if path == "/api/cron":
                    return self._send(200, scheduler.add_job(
                        store, data.get("title") or data.get("name", ""),
                        data.get("schedule", "daily"), data.get("task", "")))
                return self._send(404, {"error": "not found"})
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})

    return Handler


def create_server(store: StateStore, port: int = 0) -> ThreadingHTTPServer:
    """Bind 127.0.0.1 only. port=0 lets the OS pick a free port (tests)."""
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(store))


def run_dashboard(store: StateStore, port: int = DEFAULT_PORT) -> int:
    server = create_server(store, port)
    print(f"Battle Court dashboard: http://127.0.0.1:{server.server_address[1]}")
    print(LOCAL_ONLY_NOTE)
    print("Approval is CLI-only: ship --approve --confirm <candidate> (dashboard never approves).")
    print("Press Ctrl-C to stop the dashboard (the framework state stays on disk).")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
