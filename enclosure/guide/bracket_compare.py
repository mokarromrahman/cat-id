import sys
sys.path.insert(0, "enclosure")
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon, FancyArrowPatch
import enclosure as e

D, H = e.OUT_Y, e.OUT_Z
BR = "#e07a2f"; BODY = "#e9e2d0"; RED = "#d62828"; BLUE = "#1f5fbf"; GREEN = "#2e8b57"
lab = dict(fontsize=9.5, bbox=dict(fc="white", ec="none", alpha=0.9, pad=1.5), zorder=20)

# rough loads (estimates): box ~0.5 kg -> 5 N with its centre of mass ~70 mm out;
# a cat landing on the front edge ~120 N at ~125 mm out. Shared by 3 brackets.
N_BR = 3
cases = {"everyday (just the box)": (5.0, 0.070), "a cat lands on the front edge": (120.0, 0.125)}
TOP_SCREW = 20.0   # mm below the box

def pull(leg, load, d):
    lever = (leg - TOP_SCREW) / 1000.0
    return load * d / N_BR / lever

fig, axs = plt.subplots(1, 2, figsize=(16, 8.6))
for ax, leg, name in zip(axs, (95.0, 150.0), ("Now: 95 mm down the wall", "Longer: 150 mm down the wall")):
    ax.set_title(name, fontsize=13, fontweight="bold", loc="left")
    ax.add_patch(Rectangle((-14, -165), 14, H + 190, fc="#efefef", ec="none", hatch="///", zorder=0))
    ax.text(-7, 40, "WALL", rotation=90, ha="center", fontsize=9, color="#777")
    ax.add_patch(Rectangle((0, 0), D, H, fc=BODY, ec="#555", lw=1.2, zorder=2))
    ax.text(D / 2, H / 2 + 8, "box (side view)", ha="center", fontsize=9, zorder=3)
    prof = [(0, 0), (D, 0), (D, -8), (D * 0.76, -8), (8, -leg), (0, -leg)]
    ax.add_patch(Polygon(prof, fc=BR, ec="#8a4a14", lw=1.2, zorder=3))
    ax.add_patch(Rectangle((D, -8), 4, 8 + e.FLOOR, fc=BR, ec="#8a4a14", lw=1.2, zorder=3))
    ax.add_patch(Polygon([(10, -12), (D * 0.66, -12), (12, -leg + 18)], fc="white", ec="#8a4a14", lw=1, zorder=4))
    # weight
    ax.add_patch(FancyArrowPatch((70, H + 14), (70, H / 2 - 6), arrowstyle="-|>", mutation_scale=16, color=RED, lw=2.4, zorder=9))
    ax.text(72, H + 16, "weight, front-heavy\n(and a cat, if one jumps up)", color=RED, fontsize=9.5, va="bottom")
    # top screw pulled out of the wall
    t = pull(leg, *cases["a cat lands on the front edge"])
    ax.add_patch(Rectangle((-14, -TOP_SCREW - 1.8), 20, 3.6, fc="#555", zorder=6))
    ax.add_patch(FancyArrowPatch((8, -TOP_SCREW), (8 + t * 0.55, -TOP_SCREW), arrowstyle="-|>", mutation_scale=16, color=BLUE, lw=2.4, zorder=9))
    ax.text(12, -TOP_SCREW - 6, "top screw gets\npulled OUT of\nthe wall", color=BLUE, fontsize=9.5, va="top", zorder=20)
    # bottom of the leg pushes into the wall (the pivot)
    ax.add_patch(Rectangle((-14, -leg + 8 - 1.8), 20, 3.6, fc="#555", zorder=6))
    ax.add_patch(FancyArrowPatch((30, -leg + 2), (3, -leg + 2), arrowstyle="-|>", mutation_scale=16, color=GREEN, lw=2.4, zorder=9))
    ax.text(32, -leg - 2, "bottom of the bracket\npresses INTO the wall", color=GREEN, fontsize=9.5, va="center")
    # lever arm
    ax.annotate("", (-22, -TOP_SCREW), (-22, -leg), arrowprops=dict(arrowstyle="<->", color="#333", lw=1.2))
    ax.text(-25, -(TOP_SCREW + leg) / 2, f"lever\n{leg - TOP_SCREW:.0f} mm", ha="right", va="center", fontsize=10, fontweight="bold")
    # numbers
    rows = [f"{k}:  ~{pull(leg, *v):.0f} N" for k, v in cases.items()]
    ax.text(D + 12, -leg + 30, "pull on each top screw\n(3 brackets sharing)\n\n" + "\n".join(rows), fontsize=10.5, va="bottom",
            bbox=dict(fc="#f6f6f6", ec="#bbb", pad=6), zorder=20)
    ax.set_xlim(-60, 235); ax.set_ylim(-165, H + 40); ax.set_aspect("equal"); ax.axis("off")

fig.suptitle("Longer leg = longer lever = less pull on the wall anchors", fontsize=15, fontweight="bold", x=0.01, ha="left")
fig.text(0.01, 0.92, "The bracket pivots on its bottom end. The farther the top screw is from that pivot, the less it gets pulled out of the wall for the same load. "
         "Estimates: box ~0.5 kg, a cat landing ~12 kg-force on the front edge.", fontsize=10.5)
plt.tight_layout(rect=(0, 0, 1, 0.9)); plt.savefig(sys.argv[1] + "/bracket_compare.png", dpi=100, facecolor="white")
for leg in (95, 150):
    print(leg, {k: round(pull(leg, *v), 1) for k, v in cases.items()})
