"""Wall hole layout: a dimensioned diagram (PNG) and a 1:1 paper template (PDF, US Letter)."""
import sys
sys.path.insert(0, "enclosure")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
import enclosure as e

KZ = e.SHELF_Z1 + 10 + e.KEY_TRAVEL                     # keyhole screws, above the box's bottom
KX = (e.KEY_X_FROM_SIDES, e.OUT_X - e.KEY_X_FROM_SIDES)
BZ = (-14.0, -(e.BRACKET_LEG - 12.0))
BR = {n: ((x0 + x1) / 2, x0, x1) for n, (x0, x1, w) in e.BRACKETS.items()}
W, H, LEG = e.OUT_X, e.OUT_Z, e.BRACKET_LEG
ORANGE, BLUE, RED = "#e07a2f", "#1f5fbf", "#d62828"

def cross(ax, x, y, c, r=4.0, lw=1.3):
    ax.plot([x - r, x + r], [y, y], color=c, lw=lw, zorder=8); ax.plot([x, x], [y - r, y + r], color=c, lw=lw, zorder=8)
    ax.add_patch(Circle((x, y), 2.1, fc="none", ec=c, lw=lw, zorder=8))

def layout(ax, dims=True, fs=9):
    ax.add_patch(Rectangle((0, 0), W, H, fc="none", ec="#888", lw=1, ls="--"))
    ax.text(W / 2, H - 9, "outline of the box once it's hung", ha="center", fontsize=fs, color="#777")
    for n, (cx, x0, x1) in BR.items():
        ax.add_patch(Rectangle((x0, -LEG), x1 - x0, LEG, fc="none", ec=ORANGE, lw=1, ls="--"))
    ax.plot([-12, W + 12], [KZ, KZ], color=BLUE, lw=0.8, ls=":")
    ax.text(W + 12, KZ + 2, "level", color=BLUE, fontsize=fs - 1, ha="right")
    for i, x in enumerate(KX):
        cross(ax, x, KZ, BLUE)
        ax.text(x, KZ + 7, f"K{i + 1}", color=BLUE, fontsize=fs + 1, ha="center", fontweight="bold")
    labels = {"left": "L", "middle": "M", "right": "R"}
    for n, (cx, x0, x1) in BR.items():
        for j, z in enumerate(BZ):
            cross(ax, cx, z, RED)
            ax.text(cx + 5, z + 2, f"{labels[n]}{j + 1}", color=RED, fontsize=fs, fontweight="bold")
    if not dims:
        return
    # dimensions, all from K1 (the left keyhole screw)
    def hdim(x0, x1, y, txt):
        ax.annotate("", (x0, y), (x1, y), arrowprops=dict(arrowstyle="<->", color="#333", lw=0.9))
        ax.text((x0 + x1) / 2, y + 2, txt, ha="center", fontsize=fs, bbox=dict(fc="white", ec="none", pad=0.5))
    def vdim(x, y0, y1, txt):
        ax.annotate("", (x, y0), (x, y1), arrowprops=dict(arrowstyle="<->", color="#333", lw=0.9))
        ax.text(x + 2, (y0 + y1) / 2, txt, ha="left", va="center", fontsize=fs, bbox=dict(fc="white", ec="none", pad=0.5))
    hdim(KX[0], KX[1], KZ + 16, f"{KX[1] - KX[0]:.0f} mm")
    hdim(BR["left"][0], KX[0], -LEG - 10, f"{KX[0] - BR['left'][0]:.0f}")
    hdim(KX[0], BR["middle"][0], -LEG - 10, f"{BR['middle'][0] - KX[0]:.0f}")
    hdim(KX[0], BR["right"][0], -LEG - 22, f"{BR['right'][0] - KX[0]:.0f} mm")
    vdim(W + 22, KZ, BZ[0], f"{KZ - BZ[0]:.0f} mm")
    vdim(W + 22, BZ[0], BZ[1], f"{BZ[0] - BZ[1]:.0f} mm")
    vdim(-26, KZ, 0, f"{KZ:.0f} mm")
    ax.text(-28, 6, "box\nbottom", fontsize=fs - 1, ha="right", color="#777")

# ---- dimensioned diagram
fig, ax = plt.subplots(figsize=(13, 10))
layout(ax, dims=True, fs=10)
ax.set_title("Where the 8 holes go (looking at the wall). Every distance is measured from K1, the left keyhole screw.", fontsize=12, loc="left")
ax.text(-40, -LEG - 40,
        "K1, K2 (blue): the two keyhole screws the box hangs on (pan-head, leave ~3 mm out). Draw a level line through them.\n"
        "L, M, R (red): the bracket screws, 2 per bracket (flat-head). Top ones 55 mm below the level line, bottom ones 94 mm below those.\n"
        "Horizontal, from K1: left bracket 36 mm LEFT, middle 55 mm right, right 125 mm right.",
        fontsize=10, va="top")
ax.set_xlim(-80, W + 60); ax.set_ylim(-LEG - 78, H + 30); ax.set_aspect("equal"); ax.axis("off")
plt.tight_layout(); plt.savefig(sys.argv[1] + "/wall_holes.png", dpi=100, facecolor="white")

# ---- 1:1 paper template (US Letter, portrait); 1 data unit = 1 mm
PW, PH = 215.9, 279.4
fig = plt.figure(figsize=(PW / 25.4, PH / 25.4))
x0, x1 = -45.0, 170.9          # 215.9 mm across: K1 sits 80 mm from the paper's left edge
y0, y1 = -LEG - 70, -LEG - 70 + PH
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(x0 + 35, x1 + 35); ax.set_ylim(y0, y1); ax.axis("off")
layout(ax, dims=False, fs=8)
ax.text(x0 + 45, y1 - 8, "Wall template: litterbox camera box (print at 100% / \"Actual size\")", fontsize=10, fontweight="bold")
ax.text(x0 + 45, y1 - 13, "Check: the bar below must measure exactly 100 mm. Tape to the wall, level the blue line, mark through each cross.", fontsize=7)
ax.plot([x0 + 45, x0 + 145], [y1 - 20, y1 - 20], color="k", lw=2)
for t in range(0, 101, 10):
    ax.plot([x0 + 45 + t, x0 + 45 + t], [y1 - 20, y1 - 18 if t % 50 else y1 - 16], color="k", lw=1)
ax.text(x0 + 150, y1 - 20, "100 mm", fontsize=8, va="center")
ax.text(x0 + 45, y0 + 10, "Blue K1, K2 = keyhole screws (#8 pan head, leave ~3 mm out). Red L, M, R = bracket screws (#8 flat head).\n"
        "Checks with a ruler: K1 to K2 = 104 mm; K1 down to L1/M1/R1 = 55 mm; L1 to L2 = 94 mm.", fontsize=6.5)
fig.savefig(sys.argv[1] + "/wall_template.pdf")
fig.savefig(sys.argv[1] + "/wall_template_preview.png", dpi=50)
print("template x range on paper:", x0 + 35, x1 + 35, "keyholes at", KX, "right bracket hole x", BR["right"][0])
