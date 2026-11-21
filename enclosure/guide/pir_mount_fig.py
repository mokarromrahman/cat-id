import sys
sys.path.insert(0, "enclosure"); sys.path.insert(0, sys.argv[1])
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, PathPatch, Ellipse, FancyArrowPatch, Wedge
from matplotlib.path import Path
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from section import section
import enclosure as e

def fill(ax, shape, axis, at, color, z=2):
    for outer, holes in section(shape, axis, at):
        verts, codes = [], []
        for ring in [outer] + holes:
            verts += list(ring) + [ring[0]]; codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 1) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), fc=color, ec="#555", lw=0.8, zorder=z))

body, mount = e.body_hung(), e.pir_mount_hung()
px, py = e.PIR_C
fig = plt.figure(figsize=(15, 6.8))
# 3D of the part
ax = fig.add_subplot(1, 2, 1, projection="3d")
v, f = mount.tessellate(0.05, 0.2); v = np.array([[p.X, p.Y, p.Z] for p in v]); tri = v[np.array(f)]
n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]); n /= np.linalg.norm(n, axis=1)[:, None] + 1e-9
L = np.array([0.3, -0.5, 0.8]); L /= np.linalg.norm(L); s = 0.45 + 0.55 * np.abs(n @ L)
ax.add_collection3d(Poly3DCollection(tri, facecolors=np.c_[np.outer(s, (0.85, 0.72, 0.48)), np.ones(len(s))], edgecolor="none"))
mn, mx = v.min(0), v.max(0); c = (mn + mx) / 2; r = (mx - mn).max() / 2 * 0.75
ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
ax.view_init(32, -60); ax.set_box_aspect((1, 1, 1)); ax.set_axis_off()
ax.set_title("pir_mount.stl (prints this way up: cup bottom on the bed)", fontsize=11)
# side cut through the sensor: wall left, room right, z up
ax = fig.add_subplot(1, 2, 2)
fill(ax, body, "x", px, "#e9e2d0")
fill(ax, mount, "x", px, "#d9b77a", z=3)
bz = -(e.PIR_COMPONENT_ROOM + e.PCB_T)
y0, y1 = py - e.PIR_BOARD[1] / 2, py + e.PIR_BOARD[1] / 2
ax.add_patch(Rectangle((y0, bz), e.PIR_BOARD[1], e.PCB_T, fc="#2e8b57", ec="#1d5c33", zorder=5))           # board
ax.add_patch(Rectangle((py - 12, bz - 3.5), 24, 3.5, fc="#f2f2f2", ec="#999", zorder=4))                   # lens base
ax.add_patch(Wedge((py, bz - 3.5), 11.5, 180, 360, fc="#f7f7f7", ec="#999", zorder=4))                    # dome
ax.add_patch(Rectangle((y0 + 2, bz + e.PCB_T), 4, 5, fc="#222", zorder=5))                                # a folded cap
ax.add_patch(Rectangle((y1 - 2.6, bz + e.PCB_T), 2.0, 2.5, fc="#111", zorder=6))                          # header base
ax.add_patch(Rectangle((y1 - 3.0, bz + e.PCB_T + 2.5), 2.6, 12.5, fc="#333", ec="#000", zorder=6))       # plug
ax.plot([y1 - 1.7, y1 - 1.7, y1 + 3, 30], [bz + 16.6, 12.5, 14.5, 26], color="#c0392b", lw=2, zorder=7)  # wire up to the Pi
ax.text(31, 25, "wires up through the\nshelf hole to the Pi", fontsize=9, color="#c0392b")
lab = dict(fontsize=9, bbox=dict(fc="white", ec="none", alpha=0.85, pad=1))
ax.annotate("body floor (already printed)", (py + 20, 1.5), (py + 30, 6), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), **lab)
ax.annotate("holder, stuck under the floor\nwith foam tape on its flange", (py + 17, -1), (py + 30, -9), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), **lab)
ax.annotate("sensor board, parts facing UP", (py, bz + 0.8), (py - 48, bz + 9), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), **lab)
ax.annotate("pins + plugs: toward the FRONT,\nup through the original hole", (y1 - 1.7, 4), (py - 48, 20), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), **lab)
ax.annotate("dome looks DOWN at the litterbox", (py, bz - 14), (py - 48, bz - 16), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), **lab)
ax.annotate("M2 screws (x2) through the board\ninto the holder's ledge", (py - 9, bz - 1.5), (py - 48, bz - 6), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), **lab)
ax.text(1, 33, "WALL", rotation=90, fontsize=9, color="#777"); ax.text(46, -24, "front / phone side ->", fontsize=9, color="#777")
ax.set_xlim(py - 50, py + 60); ax.set_ylim(-28, 36); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Side cut through the sensor (wall on the left)", fontsize=11)
plt.tight_layout(); plt.savefig(sys.argv[1] + "/pir_mount.png", dpi=110, facecolor="white")
