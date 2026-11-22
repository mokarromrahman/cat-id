import sys
sys.path.insert(0, sys.argv[1])
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, FancyArrowPatch, Rectangle, Circle
from matplotlib.path import Path
from section import section
import enclosure as e, build123d as bd

BG = "white"
COL = dict(body="#e9e2d0", tray="#d9b77a", panel="#9cc3e6", phone="#3a3f55", pi="#3aa860",
           pir="#f5f5f5", screw="#d62828", wall="#bbbbbb")

def fill(ax, shape, axis, at, color, dx=0, dz=0, ec="#555", lw=0.8, z=2, alpha=1):
    for outer, holes in section(shape, axis, at):
        verts, codes = [], []
        for ring in [outer] + holes:
            r = ring + np.array([dx, dz])
            verts += list(r) + [r[0]]
            codes += [Path.MOVETO] + [Path.LINETO] * (len(r) - 1) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), fc=color, ec=ec, lw=lw, zorder=z, alpha=alpha))

def screw_v(ax, x, ztop, length, head_w, label=None, lx=0, lz=0, z=6, arrow=True, ha="left"):
    """Vertical screw, head at ztop, shank going down, red."""
    ax.add_patch(Rectangle((x - head_w / 2, ztop), head_w, 1.6, fc=COL["screw"], ec="k", lw=0.5, zorder=z))
    ax.add_patch(Rectangle((x - head_w / 5, ztop - length), head_w / 2.5, length, fc=COL["screw"], ec="k", lw=0.5, zorder=z))
    if arrow:
        ax.add_patch(FancyArrowPatch((x, ztop + 14), (x, ztop + 3), arrowstyle="-|>", mutation_scale=9, color=COL["screw"], lw=1.2, zorder=z))
    if label:
        ax.annotate(label, (x, ztop + 1), (x + lx, ztop + lz), fontsize=8.5, color="#222", ha=ha, bbox=dict(fc="white", ec="none", alpha=0.9, pad=1.5),
                    arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), zorder=9)

def move(ax, a, b, text=None, color="#1f5fbf", tx=0, tz=0):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=14, color=color, lw=1.8, zorder=8))
    if text:
        ax.text((a[0] + b[0]) / 2 + tx, (a[1] + b[1]) / 2 + tz, text, fontsize=9, color=color, zorder=9)

def num(ax, x, z, n):
    ax.add_patch(Circle((x, z), 4.2, fc="#1f5fbf", ec="none", zorder=10))
    ax.text(x, z, str(n), color="white", ha="center", va="center", fontsize=9, fontweight="bold", zorder=11)

body, tray, panel = e.body_hung(), e.tray_hung(), e.panel_hung()
asm = e.enclosure(); stand = {c.label: c for c in asm.children[3:]}

# ---------------- Figure 1: side cut-through, exploded ----------------
fig, ax = plt.subplots(figsize=(12, 9.5)); fig.patch.set_facecolor(BG)
XS = e.TRAY_X0 + 3.5   # body cut through the tray's left screws (top is solid here)
XP = e.BOARD_X0 + 3.5  # tray and Pi cut through the standoffs
TRAY_DZ, TRAY_DY, PANEL_DZ, PANEL_DY, PHONE_DY = 10, 150, 66, 0, 230
# wall
ax.add_patch(Rectangle((-22, -25), 22, 205, fc="#efefef", ec="none", hatch="///", zorder=0))
ax.text(-11, 140, "WALL", rotation=90, ha="center", va="center", fontsize=10, color="#777")
fill(ax, body, "x", XS, COL["body"])
fill(ax, stand["pir"], "x", e.PIR_C[0], COL["pir"], z=3)
fill(ax, tray, "x", XP, COL["tray"], dx=TRAY_DY, dz=TRAY_DZ)
fill(ax, stand["raspberry_pi"], "x", XP, COL["pi"], dx=TRAY_DY, dz=TRAY_DZ, z=3)
fill(ax, panel, "x", e.IN_X0 + e.TAB_X, COL["panel"], dx=PANEL_DY, dz=PANEL_DZ)
fill(ax, stand["phone"], "x", XS, COL["phone"], dx=PHONE_DY - 115, z=3)
# phone: draw it pulled out in front (shift so it sits outside the box)
# wall screw in the keyhole (left keyhole; both look the same from the side)
kz = e.SHELF_Z1 + 10 + e.KEY_TRAVEL
ax.add_patch(Rectangle((0.3, kz - 4.5), 2.4, 9, fc=COL["screw"], ec="k", lw=0.5, zorder=6))
ax.add_patch(Rectangle((-24, kz - 1.8), 24.3, 3.6, fc=COL["screw"], ec="k", lw=0.5, zorder=6))
ax.annotate("wall screw (x2): head sits in the\nkeyhole's channel; hang the body\nand push it down 10 mm",
            (1, kz - 4), (-66, kz - 50), fontsize=8.5, bbox=dict(fc="white", ec="none", alpha=0.9),
            arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), zorder=9)
num(ax, -72, kz - 34, 1)
# PIR M2 screws (both at the same depth)
px, py = e.PIR_C
screw_v(ax, py, e.FLOOR + e.PIR_BOSS_H + 1.6, 4.5, 3.5, "M2 x 5 (x2): PIR board\nto the floor posts,\ndome down through the hole", lx=-14, lz=-45, arrow=False)
num(ax, py + 10, -11, 2)
ax.text(py + 17, -13, "PIR dome looks down", ha="left", va="center", fontsize=8, color="#444")
# Pi M2.5 screws into tray standoffs (exploded with the tray)
for by in (e.BOARD_Y0 + 3.5, e.BOARD_Y0 + 52.5):
    screw_v(ax, by + TRAY_DY, e.BOARD_Z0 + e.PCB_T + TRAY_DZ, 6, 4.5,
            "M2.5 x 6 (x4): Pi to the tray's\nposts (do this first)" if by > e.BOARD_Y0 + 10 else None, lx=8, lz=22)
num(ax, e.BOARD_Y0 + TRAY_DY + 52.5 - 2, e.BOARD_Z0 + TRAY_DZ + 36, 3)
# tray M3 screws: through the tray into the shelf
for ty in (e.TRAY_Y0 + 3.5, e.TRAY_Y1 - 3.5):
    screw_v(ax, ty, e.SHELF_Z1 + e.TRAY_T + 0.2, 6, 5.5,
            "M3 x 6 (x4): through the tray into\nthe shelf, once the tray is in" if ty < e.BOARD_Y0 else None, lx=12, lz=20)
move(ax, (e.TRAY_Y0 + TRAY_DY - 4, e.SHELF_Z1 + TRAY_DZ + 2), (e.OUT_Y - 18, e.SHELF_Z1 + 6), "slide the tray in", tx=-22, tz=6)
num(ax, e.TRAY_Y1 + TRAY_DY + 10, e.SHELF_Z1 + TRAY_DZ + 3, 4)
ax.text(e.TRAY_Y0 + TRAY_DY + 20, e.SHELF_Z1 + TRAY_DZ - 9, "Pi on its tray", fontsize=9, color="#7a5a20")
# power cable
pwr_y = e.BOARD_Y0 - 9
ax.plot([pwr_y, pwr_y], [180, e.OUT_Z + 2], color="#222", lw=2.2, zorder=7)
ax.plot([pwr_y, pwr_y], [e.OUT_Z + 2, e.BOARD_Z0 + e.PCB_T + 3], color="#222", lw=1.6, ls=":", zorder=7)
ax.text(pwr_y + 4, 170, "power from the ceiling, down through\nthe slot in the top into the Pi (after 4)", fontsize=8.5, zorder=9)
num(ax, pwr_y - 8, 172, 5)
# phone pulled out to the front
pz = e.FLOOR + e.CASE_T / 2
move(ax, (e.PHONE_Y0 + PHONE_DY - 115 - 4, pz), (e.OUT_Y - 30, pz), "slide in under the shelf", tz=-11, tx=-6)
num(ax, e.PHONE_Y1 + PHONE_DY - 115 + 8, pz, 6)
ax.text(e.PHONE_Y0 + PHONE_DY - 115 + 40, pz - 17, "phone, screen up, cord already plugged in", ha="center", fontsize=8.5)
# panel
move(ax, (e.OUT_Y + 8, e.FLOOR + PANEL_DZ + 2), (e.OUT_Y + 8, e.OUT_Z + 6), "slides down into the\nside-wall grooves (last)", tx=4)
screw_v(ax, e.GROOVE_Y0 - e.TAB_L / 2 + PANEL_DY, e.OUT_Z + 3 + PANEL_DZ, 9, 6,
        "M3 x 8 thumb screw (x1):\ntab into the top", lx=-75, lz=6)
num(ax, e.OUT_Y + 22, e.OUT_Z + PANEL_DZ + 8, 7)
ax.text(e.OUT_Y + 8, e.OUT_Z + PANEL_DZ - 22, "front panel", fontsize=9, color="#2a5d8f")
ax.text(e.OUT_Y / 2 + 30, -24, "body (stays on the wall)", ha="center", fontsize=9, color="#6b5b3a")
ax.text(e.OUT_Y + 5, -20, "ROOM / litterbox below  ->", fontsize=9, color="#777")
ax.set_xlim(-80, 310); ax.set_ylim(-50, 185); ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Side cut-through (wall on the left), pulled apart: blue numbers = assembly order, red = screws", fontsize=11)
plt.tight_layout(); plt.savefig(sys.argv[2] + "/assembly_side.png", dpi=110, facecolor=BG)

# ---------------- Figure 2: front view ----------------
fig, ax = plt.subplots(figsize=(12, 8.2)); fig.patch.set_facecolor(BG)
YS = 80.0
fill(ax, body, "y", YS, COL["body"])
fill(ax, tray, "y", e.TRAY_Y0 + 3.5, COL["tray"])
fill(ax, stand["raspberry_pi"], "y", YS, COL["pi"], z=3)
fill(ax, stand["phone"], "y", YS, COL["phone"], z=3)
# keyholes (behind, dashed)
for kx in (e.KEY_X_FROM_SIDES, e.OUT_X - e.KEY_X_FROM_SIDES):
    ax.add_patch(Circle((kx, e.SHELF_Z1 + 10), 4.75, fc="none", ec="#555", ls="--", lw=0.8, zorder=4))
    ax.add_patch(Rectangle((kx - 2.25, e.SHELF_Z1 + 10), 4.5, 10, fc="none", ec="#555", ls="--", lw=0.8, zorder=4))
ax.annotate("keyholes (x2) in the back plate,\n104 mm apart: put the wall\nscrews in level first", (e.KEY_X_FROM_SIDES - 5, e.SHELF_Z1 + 10), (-75, e.SHELF_Z1 + 40), fontsize=8.5,
            bbox=dict(fc="white", ec="none", alpha=0.9), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), zorder=9)
# tray screws
for tx in (e.TRAY_X0 + 3.5, e.TRAY_X1 - 3.5):
    screw_v(ax, tx, e.SHELF_Z1 + e.TRAY_T, 6, 5.5, arrow=False)
ax.annotate("M3 x 6 screws: tray into the shelf", (e.TRAY_X0 + 3.5, e.SHELF_Z1 + 2), (-75, e.SHELF_Z1 - 8), fontsize=8.5,
            bbox=dict(fc="white", ec="none", alpha=0.9), arrowprops=dict(arrowstyle="-", color="#666", lw=0.6), zorder=9)
# USB cord loop outside the notched wall (your left)
x0 = e.OUT_X
pz = e.FLOOR + e.CASE_T / 2; uz = e.BOARD_Z0 + e.PCB_T + 8
t = np.linspace(0, 1, 60)
cx = x0 + 6 + 26 * np.sin(np.pi * t); cz = pz + (uz - pz) * t
ax.plot(cx, cz, color="#222", lw=2.2, zorder=7)
ax.add_patch(Rectangle((x0 - 4, pz - 3.5), 12, 7, fc="#444", zorder=7)); ax.add_patch(Rectangle((x0 - 4, uz - 4), 12, 8, fc="#444", zorder=7))
ax.text(x0 + 36, (pz + uz) / 2, ha="right", s="USB cord loops outside:\nUSB-C plug out of the lower notch,\nUSB-A plug out of the upper notch", fontsize=8.5, va="center")
# power cable
pwr_x = e.BOARD_X0 + e.PI_POWER_X
ax.plot([pwr_x, pwr_x], [e.OUT_Z + 40, e.BOARD_Z0 + e.PCB_T + 3], color="#222", lw=2.2, zorder=7)
ax.text(pwr_x + 3, e.OUT_Z + 30, "power from the ceiling", fontsize=8.5)
# panel above, sliding down
pl = e.IN_X0 - e.GROOVE_DEPTH + 0.3
ax.add_patch(Rectangle((pl, e.OUT_Z + 52), e.IN_X1 - e.IN_X0 + 2 * e.GROOVE_DEPTH - 0.6, e.OUT_Z - e.FLOOR, fc=COL["panel"], ec="#555", alpha=0.55, zorder=5))
ax.text(e.OUT_X / 2, e.OUT_Z + 52 + 28, "front panel: slides straight down into the grooves", ha="center", fontsize=9, color="#1f3f66", zorder=6)
move(ax, (12, e.OUT_Z + 50), (12, e.OUT_Z + 6))
move(ax, (e.OUT_X - 12, e.OUT_Z + 50), (e.OUT_X - 12, e.OUT_Z + 6))
ax.text(e.OUT_X / 2, -10, "camera window and PIR hole in the floor, looking down at the litterbox", ha="center", fontsize=8.5, color="#444")
ax.text((e.IN_X0 + e.IN_X1) / 2, e.FLOOR + 3, "phone, screen up, top end on your right", ha="center", color="white", fontsize=8, zorder=8)
ax.text(e.BOARD_X0 + 5, e.BOARD_Z0 + 5, "Pi", color="#1d5c33", fontsize=9, zorder=8)
ax.set_xlim(-170, 380); ax.set_ylim(-20, 185); ax.set_aspect("equal"); ax.axis("off")
ax.invert_xaxis()  # as seen facing the wall: the model's x+ is on your left
ax.set_title("Front view (cut through the middle of the phone), panel lifted off", fontsize=11)
plt.tight_layout(); plt.savefig(sys.argv[2] + "/assembly_front.png", dpi=110, facecolor=BG)
