#!/usr/bin/env python3
"""Generate the Recon app icon: a radar sweep in the dashboard's rust palette.
Renders at 4x then downsamples for clean antialiasing. Opaque RGB (iOS requires
no alpha on the app icon)."""
from PIL import Image, ImageDraw
import math

S = 1024
SS = 4                      # supersample factor
N = S * SS
img = Image.new("RGB", (N, N), (0, 0, 0))
d = ImageDraw.Draw(img, "RGBA")

# ---- background: warm rust vertical gradient -------------------------------
top = (171, 74, 44)        # #AB4A2C
bot = (122, 47, 26)        # #7A2F1A
for y in range(N):
    t = y / N
    r = int(top[0] + (bot[0] - top[0]) * t)
    g = int(top[1] + (bot[1] - top[1]) * t)
    b = int(top[2] + (bot[2] - top[2]) * t)
    d.line([(0, y), (N, y)], fill=(r, g, b))

cx = cy = N / 2
cream = (244, 239, 230)
gold = (212, 168, 67)

# ---- radar sweep wedge (drawn first, under the rings) ----------------------
sweep = Image.new("RGBA", (N, N), (0, 0, 0, 0))
sd = ImageDraw.Draw(sweep)
R = N * 0.40
start, end = -90, -20      # wedge from straight up, sweeping clockwise
steps = 60
for i in range(steps):
    a0 = math.radians(start + (end - start) * i / steps)
    a1 = math.radians(start + (end - start) * (i + 1) / steps)
    alpha = int(150 * (i / steps))     # fade toward the trailing edge
    sd.polygon([(cx, cy),
                (cx + R * math.cos(a0), cy + R * math.sin(a0)),
                (cx + R * math.cos(a1), cy + R * math.sin(a1))],
               fill=(244, 239, 230, alpha))
img.paste(Image.alpha_composite(img.convert("RGBA"), sweep).convert("RGB"), (0, 0))
d = ImageDraw.Draw(img, "RGBA")

# ---- concentric rings ------------------------------------------------------
lw = int(N * 0.006)
for frac in (0.16, 0.27, 0.38):
    rr = N * frac
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(244, 239, 230, 235), width=lw)

# ---- crosshair lines -------------------------------------------------------
R2 = N * 0.40
d.line([(cx, cy - R2), (cx, cy + R2)], fill=(244, 239, 230, 120), width=lw)
d.line([(cx - R2, cy), (cx + R2, cy)], fill=(244, 239, 230, 120), width=lw)

# ---- leading sweep line (bright) -------------------------------------------
a = math.radians(end)
d.line([(cx, cy), (cx + R * math.cos(a), cy + R * math.sin(a))],
       fill=(244, 239, 230, 255), width=int(lw * 1.4))

# ---- blip (a detected role) with a soft glow -------------------------------
bx, by = cx + N * 0.22, cy - N * 0.10
for gr, ga in ((N * 0.045, 60), (N * 0.030, 110), (N * 0.018, 255)):
    d.ellipse([bx - gr, by - gr, bx + gr, by + gr], fill=(212, 168, 67, ga))

# ---- center hub ------------------------------------------------------------
hr = N * 0.022
d.ellipse([cx - hr, cy - hr, cx + hr, cy + hr], fill=(244, 239, 230, 255))

out = img.resize((S, S), Image.LANCZOS)
dst = "Recon/Assets.xcassets/AppIcon.appiconset/icon_1024.png"
out.save(dst, "PNG")
print("wrote", dst, out.size)
