"""Draws plug_box.png: the plug box in 3D and from the front (as you face the wall), plugs in place.

python enclosure/guide/plug_box_fig.py enclosure/guide   (from the repo root; needs build123d + matplotlib)
The model's x+ is on the viewer's LEFT, so the front view's x axis is inverted.
"""
import sys
sys.path.insert(0, "enclosure")
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import enclosure as e

b = e.plug_box_body()
fig = plt.figure(figsize=(16, 8.5))
ax = fig.add_subplot(1, 2, 1, projection="3d")
v, f = b.tessellate(0.05, 0.2); v = np.array([[q.X, q.Y, q.Z] for q in v]); tri = v[np.array(f)]
n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-9
L = np.array([-0.4, 0.7, 0.6]); L /= np.linalg.norm(L); s = 0.4 + 0.6 * np.abs(n @ L)
ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[np.outer(s, (0.85, 0.72, 0.48)), np.ones(len(s))], edgecolor="none"))
mn, mx = v.min(0), v.max(0); c = (mn + mx) / 2; r = (mx - mn).max() / 2 * 0.7
ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
ax.view_init(28, 105); ax.set_box_aspect((1, 1, 1)); ax.set_axis_off()
ax.set_title("plug_box, front panel off, as it hangs", fontsize=12)

ax = fig.add_subplot(1, 2, 2); ax.set_title("Facing the wall, panel off: how the plugs sit", fontsize=12, loc="left")
iw, idp, ih, gy0, gy1, od, ow, oh = e._plugbox_dims(); zf = e.PLUGBOX_END
ax.add_patch(Rectangle((-ow / 2, 0), ow, oh, fc="#d9b77a", ec="#8a6a2a", lw=1.5))
ax.add_patch(Rectangle((-iw / 2, zf), iw, ih, fc="#f2e6cc", ec="none"))
x0, x1 = e.PLUGBOX_TOP_SLOT; ax.add_patch(Rectangle((x0, zf + ih - 0.5), x1 - x0, zf + 1, fc="white", ec="none"))
f0, f1 = e.PLUGBOX_FLOOR_SLOT; ax.add_patch(Rectangle((f0, -0.5), f1 - f0, zf + 1, fc="white", ec="none"))
a0, a1 = e.PLUGBOX_ADAPTER_X
ax.add_patch(Rectangle((a0, zf + 0.5), a1 - a0, 48, fc="#222", ec="#000"))
ax.text((a0 + a1) / 2, zf + 22, "black Pi adapter\n(29 mm side against the wall)", ha="center", va="center", color="white", fontsize=9)
sx = (x0 + x1) / 2
ax.add_patch(Rectangle((sx - 16.5, zf + 48.5), 33, 66, fc="white", ec="#666"))
ax.add_patch(Rectangle((sx - 7, zf + 114.5), 14, ih - 115, fc="#eee", ec="#888"))
ax.text(sx, zf + 82, "white\nsocket", ha="center", va="center", fontsize=9)
ax.plot([sx, sx], [zf + ih - 2, oh + 60], color="#bbb", lw=7)
ax.text(sx + 8, oh + 40, "extension cord up\nthrough the top slot", ha="right", fontsize=9)
fx = (f0 + f1) / 2
ax.plot([a0 + 2, fx + 6, fx, fx], [zf + 24, zf + 24, zf + 14, -45], color="#111", lw=2.5)
ax.text(fx - 6, -30, "Pi cable out the floor slot,\ndown to the camera box", ha="left", fontsize=9)
for x, z in e.PLUGBOX_SCREWS:
    ax.plot(x, zf + z, "o", ms=9, mfc="#666", mec="k", zorder=5)
ax.annotate("#8 screw + anchor (x2):\nscrew the empty box up first", (e.PLUGBOX_SCREWS[1][0], zf + e.PLUGBOX_SCREWS[1][1]),
            (-ow / 2 - 8, zf + 108), ha="left", va="center", fontsize=9, arrowprops=dict(arrowstyle="-", color="#666", lw=0.7))
ax.text(0, oh + 12, "front panel slides down into the side grooves from the top", ha="center", fontsize=9, color="#1f5fbf", bbox=dict(fc="white", ec="none", pad=1), zorder=6)
ax.text(ow / 2 + 6, oh / 2, "your\nleft", ha="right", va="center", fontsize=10, color="#777"); ax.text(-ow / 2 - 6, oh / 2, "your\nright", ha="left", va="center", fontsize=10, color="#777")
ax.set_xlim(-ow / 2 - 120, ow / 2 + 40); ax.set_ylim(-55, oh + 75); ax.set_aspect("equal"); ax.axis("off")
ax.invert_xaxis()  # as seen facing the wall
plt.tight_layout(); plt.savefig(sys.argv[1] + "/plug_box.png", dpi=100, facecolor="white")
