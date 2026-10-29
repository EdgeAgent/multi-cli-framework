"""Regenerate honest screenshots: run the real CLI in /tmp, capture
`watch --panes` text, render it to PNG with a monospace font.
Mock agents only, $0 spend, no real model calls. Run from repo root:
  python3 scripts/capture_screenshots.py
Outputs: docs/screenshots/*.txt + *.png (and docs/assets/hero.png,
docs/assets/architecture.png via scripts/make_assets.py, run first)."""
import subprocess, sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DEMO = Path("/tmp/multi-cli-demo")
OUT = ROOT / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

def run(*args, cwd=DEMO):
    return subprocess.run([sys.executable, str(ROOT/"run.py"), "--root", str(DEMO), *args],
                          capture_output=True, text=True, cwd=str(ROOT))

import shutil
if DEMO.exists(): shutil.rmtree(DEMO)
DEMO.mkdir(parents=True)
print(run("section", "add", "builder", "--role", "builder").stdout)
print(run("agent", "spawn", "builder", "agent-a", "--model", "glm-5.3-flash:free").stdout)
print(run("agent", "spawn", "builder", "agent-b", "--model", "qwen3-coder:free").stdout)
print(run("run", "hello").stdout[-500:])
print(run("battle", "--task", "Build hello", "--pick", "a").stdout[-500:])
print(run("section", "add", "scout", "--role", "researcher").stdout)
print(run("section", "delete", "scout").stdout)
panes = run("watch", "--panes").stdout
(OUT/"tui-watch.txt").write_text(panes)
# battle panes: fresh demo, battle only
DEMO2 = Path("/tmp/multi-cli-demo-battle")
if DEMO2.exists(): shutil.rmtree(DEMO2)
DEMO2.mkdir(parents=True)
subprocess.run([sys.executable, str(ROOT/"run.py"), "--root", str(DEMO2), "battle", "--task", "Build hello", "--pick", "a"], capture_output=True, text=True, cwd=str(ROOT))
panes2 = subprocess.run([sys.executable, str(ROOT/"run.py"), "--root", str(DEMO2), "watch", "--panes"], capture_output=True, text=True, cwd=str(ROOT)).stdout
(OUT/"tui-battle.txt").write_text(panes2)

# PNG render
from PIL import Image, ImageDraw, ImageFont
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
def render_png(text, path, title):
    font = ImageFont.truetype(FONT, 15)
    bfont = ImageFont.truetype(BOLD, 16)
    lines = text.splitlines()
    # measure
    tmp = Image.new("RGB", (10,10)); d = ImageDraw.Draw(tmp)
    cw = max(d.textlength(l, font=font) for l in lines) if lines else 100
    w = int(cw + 80); h = 44 + len(lines)*20 + 30
    img = Image.new("RGB", (w, h), (13, 17, 23))
    d = ImageDraw.Draw(img)
    d.rectangle([0,0,w,36], fill=(22, 27, 34))
    d.text((16, 9), title, font=bfont, fill=(88, 166, 255))
    y = 44
    for l in lines:
        col = (230, 237, 243)
        if l.startswith("  BATTLE") or "TOMBSTONE" in l: col = (255, 214, 90)
        if "✗" in l or "failed" in l: col = (255, 123, 114)
        if "✓" in l or "done" in l: col = (63, 185, 80)
        d.text((16, y), l, font=font, fill=col)
        y += 20
    d.text((16, h-24), "Skeleton capture — mock agents, $0 spend, no real model calls.", font=font, fill=(139, 148, 158))
    img.save(path); print("wrote", path, img.size)
render_png(panes, OUT/"tui-watch.png", "●  BATTLE COURT — LIVE WATCH")
render_png(panes2, OUT/"tui-battle.png", "●  BATTLE COURT — AFTER BATTLE")
print("done")
