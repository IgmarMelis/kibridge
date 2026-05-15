"""
Render the sample board to PNG using Pillow, matching the look of
kirouter/static/canvas.js. This is for documentation screenshots
(docs/images/sample_board.png) — NOT used at runtime.
"""
from PIL import Image, ImageDraw, ImageFont
import json
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SAMPLE = os.path.join(REPO_ROOT, "router", "kirouter", "static", "sample_board.json")
OUT    = os.path.join(REPO_ROOT, "docs", "images", "sample_board.png")

WIDTH, HEIGHT = 900, 600
BG = (13, 13, 13)
PALETTE = [
    "#ff6b6b","#feca57","#48dbfb","#ff9ff3","#54a0ff",
    "#5f27cd","#00d2d3","#ff6348","#1dd1a1","#c8d6e5",
]

def hex_to_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))

def dim(rgb, k=0.55):
    return tuple(max(0, min(255, int(c*k))) for c in rgb)

def main():
    with open(SAMPLE, encoding="utf-8") as f:
        board = json.load(f)
    bbox = board["meta"]["board_bbox"]
    w_mm = bbox["x_max"] - bbox["x_min"]
    h_mm = bbox["y_max"] - bbox["y_min"]
    margin = 50
    scale = min((WIDTH - 2*margin)/w_mm, (HEIGHT - 2*margin)/h_mm)
    off_x = (WIDTH - w_mm*scale)/2 - bbox["x_min"]*scale
    off_y = (HEIGHT - h_mm*scale)/2 - bbox["y_min"]*scale

    def to_px(x_mm, y_mm):
        return (off_x + x_mm*scale, off_y + y_mm*scale)

    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)

    # Background grid (every 5 mm)
    grid_color = (31, 31, 31)
    step = 5 * scale
    sx = (off_x % step + step) % step
    sy = (off_y % step + step) % step
    x = sx
    while x < WIDTH:
        d.line([(x, 0), (x, HEIGHT)], fill=grid_color)
        x += step
    y = sy
    while y < HEIGHT:
        d.line([(0, y), (WIDTH, y)], fill=grid_color)
        y += step

    # Board outline
    x1, y1 = to_px(bbox["x_min"], bbox["y_min"])
    x2, y2 = to_px(bbox["x_max"], bbox["y_max"])
    for off in range(0, int(x2-x1), 10):
        d.line([(x1+off, y1), (min(x1+off+5, x2), y1)], fill=(102, 91, 58), width=2)
        d.line([(x1+off, y2), (min(x1+off+5, x2), y2)], fill=(102, 91, 58), width=2)
    for off in range(0, int(y2-y1), 10):
        d.line([(x1, y1+off), (x1, min(y1+off+5, y2))], fill=(102, 91, 58), width=2)
        d.line([(x2, y1+off), (x2, min(y1+off+5, y2))], fill=(102, 91, 58), width=2)

    # Net colour assignment
    nets = set()
    for t in board.get("tracks", []): nets.add(t["net"])
    for v in board.get("vias", []):   nets.add(v["net"])
    for fp in board.get("footprints", []):
        for p in fp.get("pads", []): nets.add(p["net"])
    net_colors = {}
    i = 0
    for n in sorted(nets):
        if n.upper() in ("GND","AGND","DGND"):
            net_colors[n] = (136,136,136)
        else:
            net_colors[n] = hex_to_rgb(PALETTE[i % len(PALETTE)])
            i += 1

    # Tracks
    for t in board.get("tracks", []):
        c = net_colors.get(t["net"], (170,170,170))
        if t["layer"] == "B.Cu":
            c = dim(c)
        sx_, sy_ = to_px(t["start"]["x_mm"], t["start"]["y_mm"])
        ex_, ey_ = to_px(t["end"]["x_mm"],   t["end"]["y_mm"])
        wpx = max(2, int(t["width_mm"] * scale))
        d.line([(sx_, sy_), (ex_, ey_)], fill=c, width=wpx)

    # Vias
    for v in board.get("vias", []):
        cx, cy = to_px(v["x_mm"], v["y_mm"])
        r = max(3, v["width_mm"]/2 * scale)
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(196,164,132))
        dr = max(2, v.get("drill_mm", 0.3)/2 * scale)
        d.ellipse([cx-dr, cy-dr, cx+dr, cy+dr], fill=(0,0,0))

    # Pads
    for fp in board.get("footprints", []):
        for p in fp.get("pads", []):
            px, py = to_px(p["x_mm"], p["y_mm"])
            sw = (p.get("size_mm",[1,1])[0]) * scale
            sh = (p.get("size_mm",[1,1])[1]) * scale
            color = net_colors.get(p["net"], (78,201,176))
            if p.get("shape") == "circle":
                r = sw/2
                d.ellipse([px-r, py-r, px+r, py+r], fill=color)
            else:
                d.rectangle([px-sw/2, py-sh/2, px+sw/2, py+sh/2], fill=color)

    # Refdes labels
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 11)
    except Exception:
        font = ImageFont.load_default()
    for fp in board.get("footprints", []):
        cx, cy = to_px(fp.get("x_mm",0), fp.get("y_mm",0))
        text = fp.get("ref","?")
        bbox_t = d.textbbox((0,0), text, font=font)
        tw = bbox_t[2]-bbox_t[0]
        d.text((cx - tw/2, cy - 18), text, fill=(170,170,170), font=font)

    # Title
    d.text((20, 14), "KiRouter — sample LED blinker", fill=(212,212,212), font=font)
    d.text((20, HEIGHT - 24), "F.Cu (bright) + B.Cu (dimmed) + vias",
           fill=(120,120,120), font=font)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img.save(OUT)
    print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")

if __name__ == "__main__":
    main()
