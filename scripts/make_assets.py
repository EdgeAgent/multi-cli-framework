"""Original assets only: no Jarvis face, no Robot Orchestra head, no copied art.
Hero: dark panel, scales/court motif + parallel panes motif, drawn with PIL.
Icon: same motif simplified. Architecture: six boxes + arrows, drawn with PIL.
Run from repo root: python3 scripts/make_assets.py"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"; OUT.mkdir(parents=True, exist_ok=True)
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
def font(p, s): return ImageFont.truetype(p, s)
BG=(13,17,23); ACC=(88,166,255); GOLD=(255,214,90); GREEN=(63,185,80); FG=(230,237,243); MUT=(139,148,158)

def hero():
    img = Image.new("RGB", (1200, 400), BG); d = ImageDraw.Draw(img)
    d.rectangle([0,0,1200,400], outline=(48,54,61), width=2)
    # parallel panes motif: three small panes
    for i, col in enumerate([ACC, GOLD, GREEN]):
        x = 60 + i*150
        d.rectangle([x, 90, x+120, 260], outline=col, width=3)
        d.line([x, 130, x+120, 130], fill=col, width=2)
        for j in range(4):
            d.line([x+12, 150+j*24, x+108-j*18, 150+j*24], fill=FG, width=3)
    # scales / court beam
    d.line([760, 90, 760, 260], fill=GOLD, width=4)
    d.line([680, 110, 840, 110], fill=GOLD, width=4)
    for cx in (700, 820):
        d.line([cx, 110, cx-28, 170], fill=FG, width=2); d.line([cx, 110, cx+28, 170], fill=FG, width=2)
        d.arc([cx-28, 150, cx+28, 205], 0, 180, fill=FG, width=3)
    d.text((60, 290), "BATTLE COURT", font=font(BOLD, 56), fill=FG)
    d.text((60, 352), "Multi-CLI Agent Framework  ·  judge, don't just merge", font=font(REG, 22), fill=MUT)
    d.text((760, 290), "VERDICT", font=font(BOLD, 40), fill=GOLD)
    img.save(OUT/"hero.png"); print("hero", img.size)

def icon(size, path):
    img = Image.new("RGBA", (size, size), (0,0,0,0)); d = ImageDraw.Draw(img)
    d.rounded_rectangle([4,4,size-4,size-4], radius=size//5, fill=BG, outline=ACC, width=max(2, size//32))
    # beam + two pans
    cx = size//2; d.line([cx, size//4, cx, size*3//4], fill=GOLD, width=max(2, size//24))
    d.line([size//4, size//3, size*3//4, size//3], fill=GOLD, width=max(2, size//24))
    for px in (size//4+size//16, size*3//4-size//16):
        d.arc([px-size//8, size//2, px+size//8, size//2+size//4], 0, 180, fill=FG, width=max(2, size//32))
    img.save(path); print(path, img.size)

def architecture():
    img = Image.new("RGB", (1200, 620), (255,255,255)); d = ImageDraw.Draw(img)
    d.text((40, 20), "Multi-CLI Agent Framework — Architecture", font=font(BOLD, 30), fill=(13,17,23))
    boxes = [
        ("CLI Core", "run / spawn / watch\nbattle / kill"), ("Orchestrator", "DAG waves\nparallel runner"),
        ("Sandbox", "one worktree\nper agent"), ("Watch / TUI", "one pane\nper agent"),
        ("Model Router", "Ollama · free\nfrontier = judge"), ("Brain + Gate", "memory · approval\nkill switch"),
    ]
    for i, (t, body) in enumerate(boxes):
        x = 40 + (i % 3)*390; y = 90 + (i//3)*230
        d.rounded_rectangle([x, y, x+350, y+180], radius=16, outline=(13,17,23), width=3)
        d.text((x+20, y+16), t, font=font(BOLD, 24), fill=(13,17,23))
        d.text((x+20, y+70), body, font=font(REG, 20), fill=(60,60,60))
        if i < 5:
            nx = 40 + ((i+1) % 3)*390; ny = 90 + ((i+1)//3)*230
            # simple arrow to next box (wrap handled by position)
            d.line([x+350, y+90, nx-10 if (i+1)%3 else x+175, y+90 if (i+1)%3 else ny-10], fill=ACC, width=3)
    d.text((40, 570), "Learning (always-on, proposal-only) runs under every box. Immutable core: gate · safety · keys · kill switch.", font=font(REG, 18), fill=(90,90,90))
    img.save(OUT/"architecture.png"); print("architecture", img.size)

hero(); icon(512, OUT/"icon.png"); icon(64, OUT/"favicon.png"); architecture()
