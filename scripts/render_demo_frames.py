#!/usr/bin/env python3
"""Render tmux capture-pane text files to 1280x720 PNG frames (2 fps).

Each capture is one 0.5s slot of the real demo session, so the PNG
sequence at 2 fps plays back in real time. Text is rendered with
DejaVu Sans Mono, matching a terminal: white on black.
"""
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

CAP_DIR = "/tmp/demo_cap"
OUT_DIR = "/tmp/demo_frames"
W, H = 1280, 720
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 14
FG = (232, 232, 232)
BG = (0, 0, 0)
X0, Y0 = 8, 8

font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
probe = Image.new("RGB", (10, 10))
d0 = ImageDraw.Draw(probe)
adv = d0.textlength("M", font=font)
line_h = 17

frames = sorted(glob.glob(os.path.join(CAP_DIR, "frame_*.txt")))
if not frames:
    print("no captures found", file=sys.stderr)
    sys.exit(1)

for idx, path in enumerate(frames):
    with open(path, errors="replace") as f:
        lines = f.read().splitlines()
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for r, line in enumerate(lines[:40]):
        d.text((X0, Y0 + r * line_h), line.rstrip(), font=font, fill=FG)
    # cursor block from the matching cursor file
    cur_path = path.replace("frame_", "cursor_")
    try:
        with open(cur_path) as f:
            cx, cy = map(int, f.read().split())
        x = X0 + cx * adv
        y = Y0 + cy * line_h
        d.rectangle([x, y, x + adv, y + line_h - 2], outline=FG)
    except Exception:
        pass
    img.save(os.path.join(OUT_DIR, f"f{idx:04d}.png"))

print(f"rendered {len(frames)} frames to {OUT_DIR}")
