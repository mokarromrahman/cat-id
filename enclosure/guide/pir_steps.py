import sys
sys.path.insert(0, "enclosure"); sys.path.insert(0, sys.argv[1])
import numpy as np, matplotlib, math
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, PathPatch, Wedge, FancyArrowPatch, Circle, Polygon
from matplotlib.path import Path
from section import section
import enclosure as e

BODY = "#e9e2d0"; HOLD = "#d9b77a"; PCB = "#2e8b57"; RED = "#d62828"; BLUE = "#1f5fbf"; TAPE = "#7fb3e6"
lab = dict(fontsize=9.5, bbox=dict(fc="white", ec="none", alpha=0.9, pad=1.5), zorder=20)

def fill(ax, shape, axis, at, color, dy=0, dz=0, z=2):
    for outer, holes in section(shape, axis, at):
        verts, codes = [], []
        for ring in [outer] + holes:
            r = ring + np.array([dy, dz])
            verts += list(r) + [r[0]]; codes += [Path.MOVETO] + [Path.LINETO] * (len(r) - 1) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), fc=color, ec="#555", lw=0.8, zorder=z))

def arrow(ax, a, b, c=BLUE, lw=2.2):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=16, color=c, lw=lw, zorder=15))

def title(ax, n, t):
    ax.set_title(f"{n}.  {t}", fontsize=12, loc="left", fontweight="bold")

body, mount = e.body_hung(), e.pir_mount_hung()
px, py = e.PIR_C
iw, idp = e.PIR_BOARD[0] + 2 * e.PIR_CUP_CLR, e.PIR_BOARD[1] + 2 * e.PIR_CUP_CLR
FX, FY = e.PIR_FLANGE
bz = -(e.PIR_COMPONENT_ROOM + e.PCB_T)

fig, axs = plt.subplots(2, 3, figsize=(18, 11.5))
axs = axs.ravel()

# ---- 1. where it goes: looking UP at the underside of the body
ax = axs[0]; title(ax, 1, "Where it goes (looking up at the box's underside)")
W, D = e.OUT_X, e.OUT_Y
flip = lambda y: -y   # wall at the top of the picture
ax.add_patch(Rectangle((0, flip(D)), W, D, fc=BODY, ec="#555", lw=1.2))
ax.plot([-8, W + 8], [0, 0], color="#555", lw=3); ax.text(W / 2, 4, "WALL", ha="center", fontsize=10, color="#555")
ax.text(W / 2, flip(D) - 9, "front (room side)", ha="center", fontsize=9, color="#555")
# camera window
cx0 = e.IN_X0 + e.FIT + e.CAM_FROM_TOP[0]; cx1 = e.IN_X0 + e.FIT + e.CAM_FROM_TOP[1]
ax.add_patch(Rectangle((cx0, flip(D)), cx1 - cx0, D - (e.PHONE_Y1 - e.FIT - e.CAM_DEPTH), fc="white", ec="#555"))
ax.text((cx0 + cx1) / 2, flip(D) + 18, "camera\nwindow", ha="center", fontsize=8)
# PIR hole (teardrop)
r = e.PIR_DOME_HOLE / 2
ax.add_patch(Circle((px, flip(py)), r, fc="white", ec="#333", lw=1))
ax.add_patch(Polygon([(px - r / 1.4142, flip(py + r / 1.4142)), (px, flip(py + 1.3 * r)), (px + r / 1.4142, flip(py + r / 1.4142))], fc="white", ec="#333", lw=1))
ax.text(px, flip(py), "round\nhole", ha="center", va="center", fontsize=8)
# holder outline
ax.add_patch(Rectangle((px - FX / 2, flip(py + FY / 2)), FX, FY, fc="none", ec=RED, lw=2, ls="--", zorder=8))
ax.annotate("the holder goes here:\nits back edge touching the wall,\nits left edge 12 mm in from\nthe box's left side,\ncentred on the round hole", (px + FX / 2, flip(py)), (px + 40, flip(py) - 32),
            arrowprops=dict(arrowstyle="-", color=RED, lw=0.8), color=RED, **lab)
ax.annotate("", (0, flip(py) - 24), (px - FX / 2, flip(py) - 24), arrowprops=dict(arrowstyle="<->", color=RED, lw=1))
ax.text((px - FX / 2) / 2, flip(py) - 30, "12 mm", ha="center", fontsize=9, color=RED)
ax.set_xlim(-12, W + 12); ax.set_ylim(flip(D) - 16, 14); ax.set_aspect("equal"); ax.axis("off")

# ---- 2. sensor into the holder, on a table (top view of the holder)
def holder_top(ax):
    ax.add_patch(Rectangle((-FX / 2, -FY / 2), FX, FY, fc=HOLD, ec="#555", lw=1.2))
    ax.add_patch(Rectangle((-iw / 2, -idp / 2), iw, idp, fc="#bfa06a", ec="#555"))
    lx, ly = e.PIR_LENS_OPENING
    ax.add_patch(Rectangle((-lx / 2, -ly / 2), lx, ly, fc="white", ec="#555"))
    for dx in (-22, 22):
        for dy in (-12, 12):
            ax.add_patch(Circle((dx, dy), e.PIR_FLANGE_SCREW / 2, fc="white", ec="#555"))
ax = axs[1]; title(ax, 2, "On a table: sensor into the holder")
holder_top(ax)
ax.add_patch(Rectangle((-e.PIR_BOARD[0] / 2, -e.PIR_BOARD[1] / 2), *e.PIR_BOARD, fc=PCB, ec="#1d5c33", alpha=0.92, zorder=5))
for dx in (-14, 14):
    ax.add_patch(Circle((dx, 0), 2.2, fc=RED, ec="k", lw=0.6, zorder=7))
for i in (-2.54, 0, 2.54):
    ax.add_patch(Rectangle((i - 0.6, e.PIR_BOARD[1] / 2 - 3.2), 1.2, 2.2, fc="#ffd166", ec="#333", zorder=7))
ax.text(0, FY / 2 + 4, "3 pins: this edge will face the FRONT", ha="center", fontsize=9, zorder=9)
ax.text(0, -3, "sensor board, parts UP\n(dome hangs down through\nthe square opening)", ha="center", color="white", fontsize=8.5, zorder=9)
ax.annotate("2 x M2 screws through the board's\nholes into the holder's ledges", (14, 0), (10, -FY / 2 - 12), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.annotate("holder, seen from above\n(wide flat rim on top)", (-FX / 2 + 2, -FY / 2 + 2), (-FX / 2 - 6, -FY / 2 - 12), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.set_xlim(-FX / 2 - 8, FX / 2 + 8); ax.set_ylim(-FY / 2 - 16, FY / 2 + 16); ax.set_aspect("equal"); ax.axis("off")

# ---- 3. wires on, tape on the rim
ax = axs[2]; title(ax, 3, "Plug the 3 wires in; tape the rim")
holder_top(ax)
ax.add_patch(Rectangle((-e.PIR_BOARD[0] / 2, -e.PIR_BOARD[1] / 2), *e.PIR_BOARD, fc=PCB, ec="#1d5c33", alpha=0.92, zorder=5))
for i, c in zip((-2.54, 0, 2.54), ("#c0392b", "#222", "#c8a400")):
    ax.plot([i, i, i + 6 * (i / 2.54 if i else 0.2)], [e.PIR_BOARD[1] / 2 - 2, FY / 2 + 6, FY / 2 + 12], color=c, lw=2, zorder=9)
for sx in (-1, 1):
    x0 = sx * (iw / 2 + 1.2) if sx > 0 else -FX / 2 + 1.2
    ax.add_patch(Rectangle((x0, -FY / 2 + 2), FX / 2 - iw / 2 - 2.4, FY - 4, fc=TAPE, ec=BLUE, hatch="///", alpha=0.8, zorder=8))
ax.annotate("double-sided foam tape\non the two wide ends of the rim\n(peel the backing off last)", (FX / 2 - 4, -8), (FX / 2 - 30, -FY / 2 - 12), arrowprops=dict(arrowstyle="-", color=BLUE, lw=0.8), color=BLUE, **lab)
ax.text(5, FY / 2 + 9, "wires to the Pi", fontsize=9, zorder=10)
ax.set_xlim(-FX / 2 - 8, FX / 2 + 8); ax.set_ylim(-FY / 2 - 16, FY / 2 + 16); ax.set_aspect("equal"); ax.axis("off")

# ---- side views (cut through the sensor, wall on the left)
def side(ax, dz, show_wires_up=True):
    fill(ax, body, "x", px, BODY)
    fill(ax, mount, "x", px, HOLD, dz=dz, z=3)
    y0, y1 = py - e.PIR_BOARD[1] / 2, py + e.PIR_BOARD[1] / 2
    ax.add_patch(Rectangle((y0, bz + dz), e.PIR_BOARD[1], e.PCB_T, fc=PCB, ec="#1d5c33", zorder=5))
    ax.add_patch(Rectangle((py - 12, bz - 3.5 + dz), 24, 3.5, fc="#f2f2f2", ec="#999", zorder=4))
    ax.add_patch(Wedge((py, bz - 3.5 + dz), 11.5, 180, 360, fc="#f7f7f7", ec="#999", zorder=4))
    ax.add_patch(Rectangle((y1 - 3.0, bz + e.PCB_T + 2.5 + dz), 2.6, 12.5, fc="#333", zorder=6))
    top = bz + e.PCB_T + 15 + dz
    ax.plot([y1 - 1.7, y1 - 1.7, 29, 27], [top, max(top, 10), 14, 30], color="#c0392b", lw=2, zorder=7)
    ax.text(1, 30, "WALL", rotation=90, fontsize=8, color="#777")
    ax.text(py, 6, "floor", fontsize=8, color="#6b5b3a", ha="center", zorder=9)
    ax.text(py + 10, 23, "shelf", fontsize=8, color="#6b5b3a", zorder=9)
    ax.text(40, -50, "front / phone side ->", fontsize=8.5, color="#777")
    ax.set_xlim(-2, 62); ax.set_ylim(-52, 34); ax.set_aspect("equal"); ax.axis("off")

ax = axs[3]; title(ax, 4, "From underneath: wires up through the hole")
side(ax, -22)
arrow(ax, (py - 16, -48), (py - 16, -30)); arrow(ax, (py + 16, -48), (py + 16, -30))
ax.annotate("feed the wires up through\nthe round hole, then up\nthrough the hole in the\nshelf to the Pi", (27.5, 17), (36, 12), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.annotate("pins toward the front", (py + 10, -12), (40, -6), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)

ax = axs[4]; title(ax, 5, "Push the holder up flat; hold 30 seconds")
side(ax, 0)
arrow(ax, (py - 14, -40), (py - 14, -14)); arrow(ax, (py + 14, -40), (py + 14, -14))
ax.annotate("the tape on the rim sticks to\nthe underside of the floor", (py + 18, -1), (36, -12), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.annotate("the plug sits in the hole;\nthe dome looks down", (py, -24), (34, -30), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)

# ---- 6. optional screws: side cut through a corner screw
ax = axs[5]; title(ax, 6, "Optional: 4 screws so it can never fall")
cutx = px - 22
fill(ax, body, "x", cutx, BODY); fill(ax, mount, "x", cutx, HOLD, z=3)
for dy in (-12, 12):
    yy = py + dy
    ax.add_patch(Rectangle((yy - 1.2, -2.0), 2.4, 2 + e.FLOOR + 1.0, fc=RED, ec="k", lw=0.5, zorder=6))
    ax.add_patch(Rectangle((yy - 2.4, -2.0 - 1.6), 4.8, 1.6, fc=RED, ec="k", lw=0.5, zorder=6))
    arrow(ax, (yy, -16), (yy, -5), c=RED, lw=1.6)
ax.annotate("drill a 2 mm pilot hole up into the floor\nthrough each corner hole, then a\n#2 x 1/4\" (or M2.5 x 6) self-tapping screw.\nThe tip pokes ~1 mm into the empty\nstrip behind the phone: that's fine.", (py + 12, e.FLOOR + 0.6), (2, -42), arrowprops=dict(arrowstyle="-", color="#666", lw=0.7), **lab)
ax.text(1, 30, "WALL", rotation=90, fontsize=8, color="#777"); ax.text(py, 6, "floor", fontsize=8, color="#6b5b3a", ha="center")
ax.set_xlim(-2, 62); ax.set_ylim(-52, 34); ax.set_aspect("equal"); ax.axis("off")

fig.suptitle("Attaching the motion-sensor holder under the floor", fontsize=16, fontweight="bold", x=0.01, y=0.995, ha="left")
fig.text(0.01, 0.945, "Steps 4-6 are cut-through side views with the wall on the left. The holder is stuck on with tape; the screws in step 6 are extra.", fontsize=10.5)
plt.tight_layout(rect=(0, 0, 1, 0.93)); plt.savefig(sys.argv[1] + "/pir_steps.png", dpi=100, facecolor="white")
