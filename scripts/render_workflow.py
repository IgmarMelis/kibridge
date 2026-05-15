"""
Render the KiBridge + KiRouter workflow diagram to docs/images/workflow.png.

This is used in the top-level README to give a one-glance picture of
what each piece does and where the data flows.
"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "docs", "images", "workflow.png"))

# Canvas
W, H = 1000, 520
BG = (13, 13, 13)
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# Try to use a nicer font
def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSansMono.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()

F_T   = font(20, bold=True)   # title
F_B   = font(14, bold=True)   # box label
F_M   = font(12)              # body
F_S   = font(10)              # subtle

# ---- Colors ---------------------------------------------------------------
BOX_KICAD     = (76, 175, 80)    # KiCad green
BOX_PLUGIN    = (33, 150, 243)   # plugin blue
BOX_ROUTER    = (255, 152, 0)    # router orange
BOX_COPILOT   = (156, 39, 176)   # copilot purple
TEXT_LIGHT    = (240, 240, 240)
TEXT_DIM      = (160, 160, 160)
LINE_COLOR    = (96, 96, 96)
ARROW_COLOR   = (212, 212, 212)


def box(x, y, w, h, color, title, lines):
    # Card shadow
    d.rectangle([x+3, y+3, x+w+3, y+h+3], fill=(0, 0, 0))
    # Card
    d.rectangle([x, y, x+w, y+h], fill=(20, 20, 22), outline=color, width=2)
    # Title bar
    d.rectangle([x, y, x+w, y+24], fill=color, outline=color)
    d.text((x+8, y+4), title, fill=(20, 20, 20), font=F_B)
    # Lines
    cy = y + 32
    for line, kind in lines:
        col = TEXT_LIGHT if kind == "label" else TEXT_DIM
        d.text((x+8, cy), line, fill=col, font=F_M if kind == "label" else F_S)
        cy += 17


def arrow(x1, y1, x2, y2, label=None, dashed=False, color=ARROW_COLOR):
    if dashed:
        # Dashed line
        dx, dy = x2 - x1, y2 - y1
        length = (dx*dx + dy*dy) ** 0.5
        steps = max(1, int(length / 8))
        for i in range(0, steps, 2):
            sx = x1 + dx * (i/steps)
            sy = y1 + dy * (i/steps)
            ex = x1 + dx * ((i+1)/steps)
            ey = y1 + dy * ((i+1)/steps)
            d.line([(sx, sy), (ex, ey)], fill=color, width=2)
    else:
        d.line([(x1, y1), (x2, y2)], fill=color, width=2)

    # Arrowhead
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    L = 9
    ax1 = x2 - L * math.cos(angle - math.pi/7)
    ay1 = y2 - L * math.sin(angle - math.pi/7)
    ax2 = x2 - L * math.cos(angle + math.pi/7)
    ay2 = y2 - L * math.sin(angle + math.pi/7)
    d.polygon([(x2, y2), (ax1, ay1), (ax2, ay2)], fill=color)

    if label:
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2
        bbox = d.textbbox((0, 0), label, font=F_S)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        # Background pad so it reads on the dark canvas
        d.rectangle([mx - tw/2 - 4, my - th/2 - 2,
                     mx + tw/2 + 4, my + th/2 + 2],
                    fill=BG)
        d.text((mx - tw/2, my - th/2 - 1), label, fill=TEXT_LIGHT, font=F_S)


# ---- Title ---------------------------------------------------------------
d.text((20, 18), "KiBridge + KiRouter — workflow",
       fill=TEXT_LIGHT, font=F_T)
d.text((20, 46), "Two independent tools that share a board JSON over localhost HTTP.",
       fill=TEXT_DIM, font=F_M)

# ---- Boxes ---------------------------------------------------------------
# Left: KiCad PCB
box(40, 90, 220, 140, BOX_KICAD, "KiCad PCB Editor", [
    ("the design source", "sub"),
    ("", "sub"),
    ("• your .kicad_pcb file", "label"),
    ("• footprints, nets, rules", "sub"),
    ("• KiCad's own DRC + save", "sub"),
])

# Middle-top: KiBridge plugin
box(310, 90, 240, 140, BOX_PLUGIN, "KiBridge plugin", [
    ("5 toolbar buttons", "sub"),
    ("", "sub"),
    ("• Inspect Board", "sub"),
    ("• Open / Apply Workspace", "sub"),
    ("• Send / Import KiRouter", "label"),
])

# Right: KiRouter web app
box(620, 90, 320, 140, BOX_ROUTER, "KiRouter (browser, localhost:8765)", [
    ("Flask server + Canvas UI", "sub"),
    ("", "sub"),
    ("• /api/board, /api/route, /api/drc", "label"),
    ("• Freerouting subprocess", "sub"),
    ("• live progress, DRC overlay", "sub"),
])

# Bottom-middle: VS Code + Copilot
box(310, 320, 240, 140, BOX_COPILOT, "VS Code + Copilot", [
    ("the AI assistant", "sub"),
    ("", "sub"),
    ("• reads kibridge_workspace/", "sub"),
    ("• writes findings.md", "sub"),
    ("• actions.json (sandboxed)", "label"),
])

# ---- Arrows --------------------------------------------------------------
# KiCad <-> KiBridge plugin (the plugin operates ON the open board)
arrow(260, 145, 305, 145, "reads board")
arrow(305, 175, 260, 175, "applies ops", dashed=True)

# KiBridge plugin -> KiRouter (Send)
arrow(550, 145, 615, 145, "POST /api/board")
arrow(615, 175, 550, 175, "GET /api/result", dashed=True)

# KiBridge plugin <-> Copilot (via workspace folder)
arrow(390, 235, 390, 315, "kibridge_workspace/")
arrow(470, 315, 470, 235, "review/actions.json", dashed=True)

# ---- Legend --------------------------------------------------------------
ly = 480
d.text((40, ly), "Legend:", fill=TEXT_LIGHT, font=F_B)
arrow(125, ly+8, 175, ly+8)
d.text((182, ly), "data/request", fill=TEXT_DIM, font=F_S)
arrow(270, ly+8, 320, ly+8, dashed=True)
d.text((327, ly), "response/result", fill=TEXT_DIM, font=F_S)

# Footer
d.text((W - 240, ly+3),
       "Apache 2.0  •  PSS Tools  •  v1.0.0",
       fill=TEXT_DIM, font=F_S)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT)
print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")
