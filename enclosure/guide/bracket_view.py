import sys, math, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon
D, H = 130.8, 60.0
lens = (102.6, 3.0)            # (y out from the wall, z) estimate for the S20 FE's main camera
fig, ax = plt.subplots(figsize=(11, 8.2))
ax.add_patch(Rectangle((-14, -260), 14, 340, fc="#efefef", ec="none", hatch="///"))
ax.text(-7, 30, "WALL", rotation=90, ha="center", fontsize=9, color="#777")
ax.add_patch(Rectangle((0, 0), D, H, fc="#e9e2d0", ec="#555", lw=1.2))
ax.text(D / 2, H / 2 + 10, "box (side view)", ha="center", fontsize=9)
ax.plot(*lens, "o", color="k", zorder=9); ax.text(lens[0] + 3, lens[1] + 5, "camera lens\n(looks straight down)", fontsize=9)
for ang, c, txt in ((26, "#7aa6d6", "edge of the photo, short side (~26-34 deg)"), (40, "#1f5fbf", "corner of the photo (~40 deg)")):
    r = 300
    for s in (-1, 1):
        ax.plot([lens[0], lens[0] + s * r * math.sin(math.radians(ang))], [lens[1], lens[1] - r * math.cos(math.radians(ang))], color=c, lw=1.6, ls="--")
    ax.text(lens[0] - 255 * math.sin(math.radians(ang)) + 4, lens[1] - 255 * math.cos(math.radians(ang)), txt, color=c, fontsize=9, rotation=0)
cone = Polygon([lens, (lens[0] - 300 * math.sin(math.radians(40)), lens[1] - 300 * math.cos(math.radians(40))),
                (lens[0] + 300 * math.sin(math.radians(40)), lens[1] - 300 * math.cos(math.radians(40)))], fc="#1f5fbf", alpha=0.07)
ax.add_patch(cone)
for L, col, name in ((95, "#e07a2f", "95 mm leg"), (150, "#b5531a", "150 mm leg")):
    ax.add_patch(Rectangle((0, -L), 6 if L == 95 else 6, L, fc=col, ec="#8a4a14", alpha=0.9 if L == 95 else 0.55, zorder=4))
    ax.plot([6, 30], [-L, -L], color=col, lw=1); ax.text(32, -L, name, fontsize=10, va="center", color=col, fontweight="bold")
ax.text(D - 4, -245, "litterbox down here", ha="right", fontsize=9, color="#777")
ax.set_title("Side view: how close the legs get to the camera's view (left bracket, the closest one)", fontsize=12, loc="left", fontweight="bold")
ax.set_xlim(-20, 230); ax.set_ylim(-260, 75); ax.set_aspect("equal"); ax.axis("off")
plt.tight_layout(); plt.savefig(sys.argv[1] + "/bracket_view.png", dpi=100, facecolor="white")
