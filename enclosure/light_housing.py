r"""Wall housing for the Lyridz pill-shaped PIR motion lights (4 of them).

On the wall the light lies flat with its long side along the wall and its face (and motion
sensor dome) pointing straight down. Front view, as hung:

    ====================== <- top of the cradle
    |  (o)  light   (o)   || <- lid: slides down into grooves, lift it out to take the light
    ===================  ==    (o) = 10 mm access holes in the front, closed by push-in caps
        lips + dome          (the light rests on the lips: no magnet needed)

- The light slides in from the lid end (round end first, dome end last) and rests face down
  on lips along both sides and round the closed end, so it stays put without its magnetic
  plate. Its face and dome are open underneath.
- The lid slides straight down into grooves at the open end (like the plug box's panel) and
  rests on the lips; gravity holds it. Lift it out by its finger hole to take the light out.
  Leave ~40 mm clear above the lid end for that.
- Mounting: 2 x #8 pan-head screws (Hillman anchors) straight through the back, heads sunk
  flush in pockets on the inside. With the light out, the screwdriver (and the screw) go in
  through two 10 mm access holes in the front wall; then slide the light in and push the two
  ``light_cap`` plugs into the access holes (or leave them open). No gussets, no tab: light +
  housing is under 100 g.

As hung: X along the wall (0 = the closed end; the lid end is on your LEFT as you face the
wall), Y out from the wall (0 = the wall), Z up (0 = the underside of the lips).

Measured (light): 75.6 L x 40.04 W x 21.2 thick (caliper), dome 11.5 across standing 3.8 mm
proud (25 mm over the dome), 42 g.

Parts, each in its print orientation, no supports, no brim:
- ``light_housing``: stands on its closed end (every wall prints straight up).
- ``light_lid``: flat.
- ``light_cap`` (x2): rim down. A split tube that springs into the 10 mm hole; pry it out
  with a fingernail under the rim's chamfer.

    cad run enclosure/light_housing.py          # view
    python enclosure/light_housing.py --export  # STL + STEP into enclosure/out/ (light_*)
"""
import sys
from pathlib import Path

import build123d as bd

try:  # text-to-cad's decorator; without it the functions just return shapes
    from cad import model
except ImportError:  # pragma: no cover
    def model(fn):
        return fn

# ---- Light (measured) ----
LIGHT_L = 75.6       # end to end, without the nub
LIGHT_W = 40.04
LIGHT_T = 21.2       # back to face at the edge
DOME_D = 11.5
DOME_H = 3.8
DOME_FROM_END = 20.0  # dome centre from the nub end (photo)

# ---- Cradle ----
CLEAR = 0.3          # gap per side around the light; raise if too tight
WALL = 3.0           # side walls and closed end
BACK = 3.0           # top of the cradle (the light's back)
LIP = 2.5            # how far the lips reach under the light's face
LIP_T = 1.6

# ---- Screws through the back ----
MOUNT_T = 4.0        # extra back thickness behind the side wall (7 mm in all)
HOLE_D = 4.6         # #8 pan-head screw (Hillman anchors' own screws)
HEAD_D = 9.6         # pocket for the pan head (8.4 across)
HEAD_DEPTH = 3.5     # pocket depth: the head sits flush with the inside
ACCESS_D = 10.0      # access hole in the front wall: the head and the screwdriver pass

# ---- Caps for the access holes ----
CAP_RIM_D = 13.0
CAP_RIM_T = 1.2
CAP_OD = 10.15       # split tube, a bit over the hole: it springs in
CAP_ID = 7.4
CAP_SLIT = 1.2

# ---- Lid ----
LID_GAP = 3.0        # room for the nub between the light's end and the lid
LID_T = 2.4          # groove width
GROOVE_D = 1.5       # groove depth into each side wall
END_WALL = 3.0       # side wall beyond the groove, holding the lid in
LID_CLEAR = 0.3      # the lid is this much smaller than its groove (thickness, each side)
HANDLE = 10.0        # lid sticks up above the cradle by this, with a finger hole

IW = LIGHT_W + 2 * CLEAR
IL = LIGHT_L + 2 * CLEAR
OW = IW + 2 * WALL
CAV_H = LIGHT_T + CLEAR
H = LIP_T + CAV_H + BACK                 # cradle height
YC = MOUNT_T + WALL + IW / 2             # light's centre line, out from the wall
X_G0 = WALL + IL + LID_GAP               # lid groove
X_G1 = X_G0 + LID_T
LEN = X_G1 + END_WALL
ZC = LIP_T + CAV_H / 2                   # screw height
SCREW_X = (WALL + IW / 2 + 7.0, X_G0 - 10.0)  # on the straight part of the cradle


def _box(x0, y0, z0, x1, y1, z1):
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * bd.Box(x1 - x0, y1 - y0, z1 - z0)


def _stadium(width, x_start, x_end):
    """Channel along X: round end at x_start, straight to x_end, centred on YC."""
    r = width / 2
    return bd.Pos(x_start + r, YC) * bd.Circle(r) + bd.Pos((x_start + r + x_end) / 2, YC) * bd.Rectangle(x_end - x_start - r, width)


def housing_hung():
    h = _box(0, 0, 0, LEN, MOUNT_T + OW, H)
    h -= bd.Pos(0, 0, LIP_T) * bd.extrude(_stadium(IW, WALL, LEN + 5), amount=CAV_H)          # light
    h -= bd.Pos(0, 0, -1) * bd.extrude(_stadium(IW - 2 * LIP, WALL + LIP, LEN + 5), amount=LIP_T + 2)  # face opening
    h -= _box(X_G0, YC - IW / 2 - GROOVE_D, LIP_T, X_G1, YC + IW / 2 + GROOVE_D, H + 1)          # lid grooves
    h -= _box(X_G0, YC - IW / 2, LIP_T + CAV_H - 0.01, LEN + 1, YC + IW / 2, H + 1)               # open top past the lid
    y_in = YC - IW / 2                                                                           # inside of the back
    for x in SCREW_X:
        h -= _ycyl(x, -1, y_in + 1, HOLE_D)                                                      # screw
        h -= _ycyl(x, y_in - HEAD_DEPTH, y_in + 1, HEAD_D)                                       # head pocket
        h -= _ycyl(x, YC + IW / 2 - 1, MOUNT_T + OW + 1, ACCESS_D)                               # access hole
    return h


def _ycyl(x, y0, y1, d):
    """Cylinder along Y at (x, ZC) from y0 to y1."""
    return bd.Pos(x, (y0 + y1) / 2, ZC) * bd.Rot(90, 0, 0) * bd.Cylinder(d / 2, y1 - y0)


def cap_shape():
    """Rim on the bed (z 0..CAP_RIM_T), split tube up from it; WALL - 0.2 long so it stays
    clear of the light."""
    rim = bd.Cylinder(CAP_RIM_D / 2, CAP_RIM_T, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    rim = bd.chamfer(rim.edges().sort_by(bd.Axis.Z)[0], 0.6)                 # fingernail gap under the rim
    tube = bd.Pos(0, 0, CAP_RIM_T) * bd.Cylinder(CAP_OD / 2, WALL - 0.2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    tube -= bd.Pos(0, 0, CAP_RIM_T) * bd.Cylinder(CAP_ID / 2, WALL, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    tube -= bd.Pos(CAP_OD / 2 - 1, 0, CAP_RIM_T + WALL / 2) * bd.Box(4, CAP_SLIT, WALL)   # slit: it springs
    return rim + tube


def lid_hung():
    t = LID_T - LID_CLEAR
    w = IW + 2 * GROOVE_D - 2 * LID_CLEAR
    lid = _box((X_G0 + X_G1 - t) / 2, YC - w / 2, LIP_T, (X_G0 + X_G1 + t) / 2, YC + w / 2, H + HANDLE)
    lid -= bd.Pos((X_G0 + X_G1) / 2, YC, H + HANDLE / 2) * bd.Rot(0, 90, 0) * bd.Cylinder(3.5, LID_T + 2)  # finger hole
    return lid


def _on_bed(shape):
    bb = shape.bounding_box()
    return bd.Pos(-bb.min.X, -bb.min.Y, -bb.min.Z) * shape


@model
def light_housing():
    """Stands on its closed end: every wall prints straight up, no supports."""
    return _on_bed(bd.Rot(0, -90, 0) * housing_hung())


@model
def light_lid():
    """Flat on the bed."""
    return _on_bed(bd.Rot(0, 90, 0) * lid_hung())


@model
def light_cap():
    """Print 2. Rim on the bed."""
    return cap_shape()


@model
def light_assembly():
    """As hung, with the lid in and a stand-in light."""
    light = bd.Pos(0, 0, LIP_T) * bd.extrude(
        bd.Pos(WALL + CLEAR + LIGHT_L / 2, YC) * bd.SlotOverall(LIGHT_L, LIGHT_W), amount=LIGHT_T)
    light += bd.Pos(WALL + CLEAR + LIGHT_L - DOME_FROM_END, YC, LIP_T) * bd.Sphere(DOME_D / 2)
    caps = [bd.Pos(x, MOUNT_T + OW + CAP_RIM_T, ZC) * bd.Rot(90, 0, 0) * cap_shape() for x in SCREW_X]
    return bd.Compound([housing_hung(), lid_hung(), light, *caps])


assert ZC + HEAD_D / 2 < H - BACK and ZC - ACCESS_D / 2 > LIP_T, "screw pocket / access hole off the side walls"

if __name__ == "__main__":
    parts = {"light_housing": light_housing(), "light_lid": light_lid(), "light_cap": light_cap()}
    out = Path(__file__).parent / "out"
    for name, p in parts.items():
        s = getattr(p, "shape", p)
        bb = s.bounding_box()
        print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, valid={s.is_valid}")
        if "--export" in sys.argv:
            out.mkdir(exist_ok=True)
            bd.export_stl(s, str(out / f"{name}.stl"), tolerance=0.02, angular_tolerance=0.2)
            bd.export_step(s, str(out / f"{name}.step"))
