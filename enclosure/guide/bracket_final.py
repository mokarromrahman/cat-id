import sys
sys.path.insert(0, "enclosure"); sys.path.insert(0, sys.argv[1])
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, PathPatch, Circle, Wedge, FancyArrowPatch
from matplotlib.path import Path
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from section import section
import enclosure as e

BODY = "#e9e2d0"; BR = "#e07a2f"; HOLD = "#d9b77a"
lab = dict(fontsize=9.5, bbox=dict(fc="white", ec="none", alpha=0.9, pad=1.5), zorder=20)
def fill(ax, shape, axis, at, color, z=2, ec="#555"):
    for outer, holes in section(shape, axis, at):
        verts, codes = [], []
        for ring in [outer] + holes:
            verts += list(ring) + [ring[0]]; codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 1) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), fc=color, ec=ec, lw=0.8, zorder=z))

fig = plt.figure(figsize=(19, 8))
gs = fig.add_gridspec(1, 3, width_ratios=[0.8, 1.1, 1.2])
# 3D
ax = fig.add_subplot(gs[0], projection="3d")
br = e.bracket_hung(*e.BRACKETS["middle"])
v, f = br.tessellate(0.05, 0.2); v = np.array([[p.X, p.Y, p.Z] for p in v]); tri = v[np.array(f)]
n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-9
L = np.array([0.5, 0.6, 0.6]); L /= np.linalg.norm(L); s = 0.4 + 0.6 * np.abs(n @ L)
ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[np.outer(s, (0.88, 0.48, 0.18)), np.ones(len(s))], edgecolor="none"))
mn, mx = v.min(0), v.max(0); c = (mn + mx) / 2; r = (mx - mn).max() / 2 * 0.7
ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
ax.view_init(14, 62); ax.set_box_aspect((1, 1, 1)); ax.set_axis_off()
ax.set_title("A bracket, from the front\n(screwdriver goes in between the two side walls)", fontsize=11)
# side
ax = fig.add_subplot(gs[1]); ax.set_title("From the side, installed (cut through a bracket)", loc="left", fontsize=12, fontweight="bold")
ax.add_patch(Rectangle((-30, -135), 30, 210, fc="#efefef", ec="none", hatch="///", zorder=0))
ax.text(-15, 40, "WALL\n(drywall)", rotation=90, ha="center", va="center", fontsize=9, color="#777")
cx = e.BRACKETS["middle"][0] + 2.0   # through a side wall, clear of the power-cable slot
fill(ax, e.body_hung(), "x", cx, BODY)
fill(ax, br, "x", cx, BR, z=3, ec="#8a4a14")

for z in (-14.0, -(e.BRACKET_LEG - 12.0)):
    ax.add_patch(Rectangle((-16, z - 3.5), 16, 7, fc="#cfcfcf", ec="#666", zorder=5))           # anchor in the drywall
    ax.add_patch(Rectangle((-26, z - 1.9), 32, 3.8, fc="#555", zorder=6))                          # screw
    ax.add_patch(Rectangle((2, z - 4.2), 4, 8.4, fc="#555", zorder=6))                             # flat head (countersunk)
ax.annotate("#8 flat-head screw into a\nself-drilling drywall anchor\n(2 per bracket)", (-10, -14), (14, -48), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.annotate("deck under the box's floor", (60, -3), (40, 22), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.annotate("lip hooks the floor's\nfront edge", (e.OUT_Y + 2, 1), (e.OUT_Y - 18, 30), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.annotate("side wall (brace)", (55, -60), (70, -95), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.text(8, -127, "120 mm down the wall", fontsize=9, color="#8a4a14")
ax.set_xlim(-32, 150); ax.set_ylim(-138, 75); ax.set_aspect("equal"); ax.axis("off")
# front
ax = fig.add_subplot(gs[2]); ax.set_title("From the front: three brackets", loc="left", fontsize=12, fontweight="bold")
W, H = e.OUT_X, e.OUT_Z
ax.add_patch(Rectangle((0, 0), W, H, fc=BODY, ec="#555", lw=1.2, zorder=2)); ax.text(W / 2, H / 2, "enclosure", ha="center", va="center", fontsize=10)
pir = e.PIR_C[0] - e.PIR_FLANGE[0] / 2
ax.add_patch(Rectangle((pir, -11.6), e.PIR_FLANGE[0], 11.6, fc=HOLD, ec="#555", zorder=3)); ax.add_patch(Wedge((e.PIR_C[0], -11.6), 11.5, 180, 360, fc="#f7f7f7", ec="#999", zorder=3))
for name, (x0, x1, wt) in e.BRACKETS.items():
    ax.add_patch(Rectangle((x0, -e.BRACKET_LEG), x1 - x0, e.BRACKET_LEG, fc=BR, ec="#8a4a14", lw=1, zorder=4))
    ax.add_patch(Rectangle((x0 + wt, -e.BRACKET_LEG + 6), x1 - x0 - 2 * wt, e.BRACKET_LEG - 11, fc="#f2b27c", ec="none", zorder=4))
    for z in (-14.0, -(e.BRACKET_LEG - 12.0)):
        ax.add_patch(Circle(((x0 + x1) / 2, z), 2.3, fc="#555", zorder=5))
    ax.text((x0 + x1) / 2, -e.BRACKET_LEG - 7, {"left": "narrow\n(16 mm)", "middle": "20 mm", "right": "20 mm"}[name], ha="center", va="top", fontsize=9)
ax.text(W + 6, -60, "6 anchors + 6 screws\nfor the brackets", fontsize=10)
ax.set_xlim(-20, W + 60); ax.set_ylim(-150, H + 12); ax.set_aspect("equal"); ax.axis("off")
fig.suptitle("Wall brackets (built): 3 brackets, 120 mm down the wall, front lip", fontsize=15, fontweight="bold", x=0.01, ha="left")
plt.tight_layout(rect=(0, 0, 1, 0.94)); plt.savefig(sys.argv[1] + "/brackets.png", dpi=100, facecolor="white")
