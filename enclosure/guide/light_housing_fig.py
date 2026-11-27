"""Draws light_housing.png: the PIR light housing as it hangs (side cut + front view).

python enclosure/guide/light_housing_fig.py enclosure/guide   (from the repo root; needs build123d + matplotlib)
"""
import sys
sys.path.insert(0, "enclosure")
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, Circle, FancyBboxPatch
import light_housing as L

TAN, EDGE, LIGHT, BLUE, RED = "#d9b77a", "#8a6a2a", "#f4f4ee", "#5b8fd6", "#c0392b"
M, OW, H, T = L.MOUNT_T, L.OW, L.H, 0.0
ZC, BK = L.ZC, L.MOUNT_T + L.WALL
fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw=dict(width_ratios=[1, 1.5]))

# ---- side cut through the middle of the light (wall on the left)
a1.set_title("Side cut through the middle (wall on the left)", fontsize=12, loc="left")
a1.add_patch(Rectangle((-6, -10), 6, H + T + 20, fc="#ddd", ec="none")); a1.text(-3, -14, "wall", ha="center", fontsize=9, color="#666")
y0, y1 = L.YC - L.IW / 2, L.YC + L.IW / 2
for r in [(0, 0, BK, H), (M, H - L.BACK, OW, L.BACK), (M + OW - L.WALL, 0, L.WALL, H),
          (M, 0, L.WALL + L.LIP, L.LIP_T), (y1 - L.LIP, 0, L.LIP + L.WALL, L.LIP_T)]:
    a1.add_patch(Rectangle(r[:2], r[2], r[3], fc=TAN, ec=EDGE, lw=1))
a1.add_patch(FancyBboxPatch((y0 + L.CLEAR, L.LIP_T), L.LIGHT_W, L.LIGHT_T, boxstyle="round,pad=0,rounding_size=1.5", fc=LIGHT, ec="#999"))
t = np.linspace(0, np.pi, 30)
a1.add_patch(Polygon(np.c_[L.YC + L.DOME_D / 2 * np.cos(t), L.LIP_T + 0.2 - L.DOME_H * np.sin(t)], fc="white", ec="#999"))
a1.text(L.YC, L.LIP_T + L.LIGHT_T / 2, "light, face down\n(rests on the lips:\nno magnet needed)", ha="center", va="center", fontsize=9)
a1.annotate("lips under the light's edge", (y1 - 1, 0.8), (y1 + 6, -12), fontsize=8.5, arrowprops=dict(arrowstyle="-", color="#666", lw=0.6))
a1.add_patch(Rectangle((BK - L.HEAD_DEPTH, ZC - L.HEAD_D / 2), L.HEAD_DEPTH + 0.3, L.HEAD_D, fc="white", ec=EDGE))
a1.add_patch(Rectangle((-0.1, ZC - L.HOLE_D / 2), BK - L.HEAD_DEPTH + 0.2, L.HOLE_D, fc="white", ec=EDGE))
a1.plot([-16, BK - 3], [ZC, ZC], color=RED, lw=3); a1.add_patch(Rectangle((BK - 3.3, ZC - 4.2), 3, 8.4, fc=RED, ec="none", zorder=5))
fy = M + OW - L.WALL
a1.add_patch(Rectangle((fy - 0.1, ZC - L.ACCESS_D / 2), L.WALL + 0.2, L.ACCESS_D, fc="white", ec=EDGE))
a1.add_patch(Rectangle((fy + 0.2, ZC - L.CAP_OD / 2 + 0.1), L.WALL - 0.2, L.CAP_OD - 0.2, fc="#c9a463", ec=EDGE, zorder=5))
a1.add_patch(Rectangle((M + OW, ZC - L.CAP_RIM_D / 2), L.CAP_RIM_T, L.CAP_RIM_D, fc="#c9a463", ec=EDGE, zorder=5))
a1.text(-16, H + 9, "#8 pan-head screw into a Hillman anchor (x2),\nhead sunk flush inside the back", fontsize=8.5, color=RED)
a1.text(M + OW + 3, ZC + 10, "cap in the 10 mm\naccess hole", fontsize=8.5)
a1.annotate("", (L.YC + 10, -24), (L.YC + 10, -6), arrowprops=dict(arrowstyle="->", color="#e0a800", lw=1.5))
a1.text(L.YC + 13, -20, "light and sensor\nlook straight down", fontsize=8.5, color="#444")
a1.set_xlim(-20, M + OW + 32); a1.set_ylim(-30, H + 18); a1.set_aspect("equal"); a1.axis("off")

# ---- front view, from the room (lid end on your left)
a2.set_title("From the front (facing the wall)", fontsize=12, loc="left")
a2.add_patch(Rectangle((0, 0), L.LEN, H, fc=TAN, ec=EDGE, lw=1.2))
for x in L.SCREW_X:
    a2.add_patch(Circle((x, ZC), L.CAP_RIM_D / 2, fc="#c9a463", ec=EDGE, zorder=6))
a2.text(sum(L.SCREW_X) / 2, ZC - 11, f"2 caps over the screws ({L.SCREW_X[1] - L.SCREW_X[0]:.0f} mm apart)", ha="center", fontsize=8.5)
lx = (L.X_G0 + L.X_G1) / 2; lt = L.LID_T - L.LID_CLEAR
a2.add_patch(Rectangle((lx - lt / 2, L.LIP_T), lt, H - L.LIP_T, fc="none", ec="#2c5aa0", ls="--", zorder=6))  # behind the wall
a2.add_patch(Rectangle((lx - 3, H), 6, L.HANDLE, fc=BLUE, ec="#2c5aa0", zorder=6))
a2.add_patch(Circle((lx, H + L.HANDLE / 2), 1.2, fc="white", ec="none", zorder=7))
a2.annotate("lid: lift it straight up to take the\nlight out; drop it back into its grooves", (lx, H + L.HANDLE - 2), (lx + 6, H + 22),
            ha="right", fontsize=8.5, color="#2c5aa0", arrowprops=dict(arrowstyle="-", color="#2c5aa0", lw=0.7))
a2.annotate("", (lx, H + L.HANDLE + 18), (lx, H + L.HANDLE + 4), arrowprops=dict(arrowstyle="<->", color="#2c5aa0", lw=1.2))
dx = L.WALL + L.CLEAR + L.LIGHT_L - L.DOME_FROM_END
a2.plot([L.WALL, L.WALL + L.IL], [-0.6, -0.6], color="#bbb", lw=3)
t = np.linspace(0, np.pi, 30)
a2.add_patch(Polygon(np.c_[dx + L.DOME_D / 2 * np.cos(t), -0.2 - L.DOME_H * np.sin(t)], fc="white", ec="#999", zorder=5))
a2.text(dx, -9, "dome (lid end)", ha="center", fontsize=8.5)
a2.text(sum(L.SCREW_X) / 2, ZC + 2, "cradle (light inside, face down)", ha="center", va="center", fontsize=9)
a2.text(L.LEN / 2, -17, f"{L.LEN:.0f} mm long, {H + T:.0f} mm tall, {L.OW + M:.0f} mm off the wall. "
        "Leave ~40 mm clear above the lid end.", ha="center", fontsize=9, color="#444")
a2.set_xlim(-8, L.LEN + 8); a2.set_ylim(-22, H + 32); a2.set_aspect("equal"); a2.axis("off")
a2.invert_xaxis()  # model +X (the lid end) is on your left as you face the wall
plt.tight_layout(); plt.savefig(sys.argv[1] + "/light_housing.png", dpi=110, facecolor="white")
