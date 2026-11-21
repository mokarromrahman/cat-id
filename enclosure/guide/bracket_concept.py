import sys
sys.path.insert(0, "enclosure"); sys.path.insert(0, sys.argv[1])
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, Wedge, FancyArrowPatch, PathPatch
from matplotlib.path import Path
from section import section
import enclosure as e

BODY = "#e9e2d0"; BR = "#e07a2f"; RED = "#d62828"; BLUE = "#1f5fbf"; HOLD = "#d9b77a"
lab = dict(fontsize=9.5, bbox=dict(fc="white", ec="none", alpha=0.9, pad=1.5), zorder=20)
W, D, H = e.OUT_X, e.OUT_Y, e.OUT_Z
BRK = [(-7.0, 7.0), (80.0, 100.0), (150.0, 170.0)]   # x ranges: narrow left one + two 20 mm right ones
BX = tuple((a + b) / 2 for a, b in BRK)
LEG = 95.0                  # how far down the wall the bracket goes
ARM_T = 8.0
cam = (e.IN_X0 + e.FIT + e.CAM_FROM_TOP[0], e.IN_X0 + e.FIT + e.CAM_FROM_TOP[1], e.PHONE_Y1 - e.FIT - e.CAM_DEPTH)
pir = (e.PIR_C[0] - e.PIR_FLANGE[0] / 2, e.PIR_C[0] + e.PIR_FLANGE[0] / 2, e.PIR_C[1] - e.PIR_FLANGE[1] / 2, e.PIR_C[1] + e.PIR_FLANGE[1] / 2)

def fill(ax, shape, axis, at, color, z=2):
    for outer, holes in section(shape, axis, at):
        verts, codes = [], []
        for ring in [outer] + holes:
            verts += list(ring) + [ring[0]]; codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 1) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), fc=color, ec="#555", lw=0.8, zorder=z))

def bracket_profile(y0=0.0):
    # side profile in (y, z): wall leg, top arm under the floor, gusset, front lip
    return [(y0, 0), (D + 4, 0), (D + 4, e.FLOOR + 0.5), (D, e.FLOOR + 0.5), (D, -ARM_T + 0.0) if False else (D, 0.0),
            (D, -ARM_T), (100, -ARM_T), (8, -LEG), (y0, -LEG)]

fig = plt.figure(figsize=(18, 7.4))
gs = fig.add_gridspec(1, 3, width_ratios=[1.05, 1.15, 1.0])

# ---- A: side view, cut through a bracket
ax = fig.add_subplot(gs[0]); ax.set_title("A.  From the side (cut through a bracket)", loc="left", fontsize=12, fontweight="bold")
ax.add_patch(Rectangle((-14, -LEG - 15), 14, H + LEG + 30, fc="#efefef", ec="none", hatch="///", zorder=0))
ax.text(-7, 30, "WALL", rotation=90, ha="center", fontsize=10, color="#777")
fill(ax, e.body_hung(), "x", BX[2], BODY)
prof = [(0, 0), (D, 0), (D, -ARM_T), (100, -ARM_T), (8, -LEG), (0, -LEG)]
ax.add_patch(Polygon(prof, fc=BR, ec="#8a4a14", lw=1.2, zorder=4))
ax.add_patch(Polygon([(D, -ARM_T), (D + 4, -ARM_T), (D + 4, e.FLOOR), (D, e.FLOOR)], fc=BR, ec="#8a4a14", lw=1.2, zorder=4))
# web cut-out (lightening) to show it's a gusset
ax.add_patch(Polygon([(10, -ARM_T - 4), (88, -ARM_T - 4), (12, -LEG + 18)], fc="white", ec="#8a4a14", lw=1, zorder=5))
for z in (-30, -80):
    ax.add_patch(Rectangle((-14, z - 1.8), 20, 3.6, fc="#666", ec="k", lw=0.5, zorder=6))
for xy, txt, at in [((-3, -30), "2 wall screws per bracket\n(#8, into drywall anchors)", (25, -55)),
                    ((D + 2, 1), "front lip hooks the floor's\nfront edge: the box can't\ntip forward or slide off", (88, 34)),
                    ((50, -3), "top arm runs under the floor\nall the way to the front", (20, 14))]:
    ax.annotate(txt, xy, at, arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.add_patch(FancyArrowPatch((80, 55), (80, 64), arrowstyle="<|-", mutation_scale=12, color=RED, lw=1.5, zorder=9))
ax.text(84, 68, "front-heavy:\nthe box wants to tip\nforward and down here", fontsize=9, color=RED, va="bottom")
ax.text(D - 10, -LEG + 2, "about 95 mm down the wall", fontsize=8.5, color="#8a4a14", ha="right")
ax.set_xlim(-16, 175); ax.set_ylim(-LEG - 12, H + 40); ax.set_aspect("equal"); ax.axis("off")

# ---- B: from the front
ax = fig.add_subplot(gs[1]); ax.set_title("B.  From the front (looking at the wall)", loc="left", fontsize=12, fontweight="bold")
ax.add_patch(Rectangle((-20, -LEG - 12), W + 30, H + LEG + 30, fc="#f4f4f4", ec="none", zorder=0))
ax.add_patch(Rectangle((0, 0), W, H, fc=BODY, ec="#555", lw=1.2, zorder=2))
ax.text(W / 2, H / 2, "the enclosure\n(front panel on)", ha="center", va="center", fontsize=10, zorder=3)
# camera + PIR hanging below at the left
ax.add_patch(Rectangle((pir[0], -11.6), pir[1] - pir[0], 11.6, fc=HOLD, ec="#555", zorder=3))
ax.add_patch(Wedge((e.PIR_C[0], -11.6), 11.5, 180, 360, fc="#f7f7f7", ec="#999", zorder=3))
ax.annotate("PIR dome and camera window:\nkept clear", (e.PIR_C[0], -20), (22, -40), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
for a, b in BRK:
    ax.add_patch(Rectangle((a, -LEG), b - a, LEG, fc=BR, ec="#8a4a14", lw=1.2, zorder=4))
    for z in (-30, -80):
        ax.add_patch(Circle(((a + b) / 2, z), 2.4, fc="#666", ec="k", lw=0.5, zorder=5))
ax.annotate("two 20 mm brackets\non the right", (BX[1] + 8, -55), (110, -LEG - 8), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.annotate("narrow 14 mm bracket\nat the left edge (half of it\nsticks out past the box)", (BX[0], -60), (-60, -LEG - 6), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.add_patch(Rectangle((W, 3), 6, 10, fc="#444", zorder=3)); ax.add_patch(Rectangle((W, 30), 6, 9, fc="#444", zorder=3))
ax.plot(W + 6 + 14 * np.sin(np.linspace(0, np.pi, 30)), np.linspace(8, 34, 30), color="#222", lw=2, zorder=3)
ax.text(W + 4, 52, "USB cord loop\n(unchanged)", fontsize=8.5)
ax.set_xlim(-64, W + 40); ax.set_ylim(-LEG - 22, H + 14); ax.set_aspect("equal"); ax.axis("off")

# ---- C: from below
ax = fig.add_subplot(gs[2]); ax.set_title("C.  From below (looking up at the box)", loc="left", fontsize=12, fontweight="bold")
fl = lambda y: -y
ax.add_patch(Rectangle((0, fl(D)), W, D, fc=BODY, ec="#555", lw=1.2))
ax.plot([-6, W + 6], [0, 0], color="#555", lw=3); ax.text(W / 2, 4, "WALL", ha="center", fontsize=10, color="#555")
ax.add_patch(Rectangle((cam[0], fl(D)), cam[1] - cam[0], D - cam[2], fc="white", ec="#555")); ax.text((cam[0] + cam[1]) / 2, fl(D) + 22, "camera\nwindow", ha="center", fontsize=8.5)
ax.add_patch(Rectangle((pir[0], fl(pir[3])), pir[1] - pir[0], pir[3] - pir[2], fc=HOLD, ec="#555")); ax.text(e.PIR_C[0], fl(e.PIR_C[1]), "PIR\nholder", ha="center", va="center", fontsize=8.5)
for a, b in BRK:
    ax.add_patch(Rectangle((a, fl(D + 4)), b - a, D + 4, fc=BR, ec="#8a4a14", lw=1.2, zorder=4))
ax.text(W / 2 + 40, fl(D) - 9, "front", ha="center", fontsize=9, color="#555")
ax.annotate("all three arms clear of the camera\nwindow and the PIR holder", (BX[1], fl(60)), (60, fl(D) - 32), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.set_xlim(-12, W + 8); ax.set_ylim(fl(D) - 44, 12); ax.set_aspect("equal"); ax.axis("off")

fig.suptitle("Proposal v2: three wall brackets under the box (not built yet)", fontsize=15, fontweight="bold", x=0.01, ha="left")
plt.tight_layout(rect=(0, 0, 1, 0.94)); plt.savefig(sys.argv[1] + "/bracket_concept.png", dpi=100, facecolor="white")
