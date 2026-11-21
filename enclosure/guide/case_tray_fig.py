import sys
sys.path.insert(0, "enclosure"); sys.path.insert(0, sys.argv[1])
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyArrowPatch
from section import section
import enclosure as e
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

t = e.case_tray_hung()
fig = plt.figure(figsize=(14, 6.2))
# 3D view of the printed part
ax = fig.add_subplot(1, 2, 1, projection="3d")
v, f = t.tessellate(0.1, 0.3); v = np.array([[p.X, p.Y, p.Z] for p in v]); tri = v[np.array(f)]
n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-9
L = np.array([0.3, -0.5, 0.8]); L /= np.linalg.norm(L); s = 0.45 + 0.55 * np.abs(n @ L)
ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[np.outer(s, (0.85, 0.72, 0.48)), np.ones(len(s))], edgecolor="none"))
mn, mx = v.min(0), v.max(0); c = (mn + mx) / 2; r = (mx - mn).max() / 2 * 0.8
ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
ax.view_init(38, -62); ax.set_box_aspect((1, 1, 1)); ax.set_axis_off()
ax.set_title("pi_case_tray.stl (prints flat, this way up)", fontsize=11)
# top view: tray, case, screws, wall
ax = fig.add_subplot(1, 2, 2)
for outer, holes in section(t, "z" if False else "y", 0) if False else []:
    pass
x0, x1 = e.CASE_TRAY_X0, e.TRAY_X1; y0, y1 = e.TRAY_Y0 - 2, e.TRAY_Y1 + 2
ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#d9b77a", ec="#555"))
ax.add_patch(Rectangle((e.IN_X1, y0 - 12), 4, y1 - y0 + 24, fc="#e9e2d0", ec="#555", hatch="//"))
ax.text(e.IN_X1 + 6, (y0 + y1) / 2, "right wall\n(USB notch)", fontsize=9, va="center")
ax.add_patch(Rectangle((e.CASE_X0, e.CASE_YC - 30.5), e.PI_CASE_L, e.PI_CASE_W, fc=(0.8, 0.9, 1.0, 0.5), ec="#2a6fb0", lw=1.5, ls="--"))
ax.text(e.CASE_X0 + 40, e.CASE_YC + 4, "Pi in its clear case bottom\n91.5 x 61 mm, stuck down with\ndouble-sided foam tape", fontsize=9, ha="center", color="#1f4f80")
ax.add_patch(Rectangle((e.CASE_X1 - 2, e.CASE_YC - 28), 6, 52, fc="#9aa3ab", ec="#555"))
ax.text(e.CASE_X1 - 6, e.CASE_YC - 22, "USB /\nEthernet", fontsize=7, ha="right")
for x, y in e.TRAY_SCREWS:
    ax.add_patch(Circle((x, y), 3.2, fc="#d62828", ec="k", lw=0.6, zorder=5))
ax.annotate("4 x M3 x 6 button head into the shelf\n(heads sit flush, under the case)", (e.TRAY_SCREWS[0][0], e.TRAY_SCREWS[0][1]),
            (x0 - 55, y0 - 24), fontsize=9, arrowprops=dict(arrowstyle="-", color="#666", lw=0.7))
ax.annotate("back wall gap:\nmicro-USB power plug", (e.CASE_X0 + 3 + e.PI_POWER_X, y0 + 2), (e.CASE_X0 + 45, y0 - 24), fontsize=9,
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.7))
ax.text((x0 + x1) / 2, y1 + 6, "front (room side)", ha="center", fontsize=9, color="#555")
ax.text((x0 + x1) / 2, y0 - 34, "back (wall side)", ha="center", fontsize=9, color="#555")
ax.set_xlim(x0 - 60, x1 + 30); ax.set_ylim(y0 - 38, y1 + 12); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("From above, on the shelf", fontsize=11)
plt.tight_layout(); plt.savefig(sys.argv[1] + "/case_tray.png", dpi=110, facecolor="white")
