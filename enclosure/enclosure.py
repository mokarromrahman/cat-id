"""Wall-hung 3D-printed shelf enclosure for the litterbox camera rig.

Hangs ~5 ft up on the wall, right above the litterbox. As hung: X along the wall (left to
right, looking at it), Y out from the wall (0 = the wall), Z up.

    +--------------------------------------------+  top (slot for the Pi's power cable)
    |   PIR wires ->|      Raspberry Pi 3 on its tray      [USB-A plug out the right side]
    |===============|==============================|  shelf
    | [PIR]   | phone lying flat, screen up, port right    [USB-C plug out the right side]
    +--------------------------------------------+  floor: camera window + PIR dome hole
                      (looking down at the litterbox)

Measured: the S20 FE in its case is 80 W x 165 L x 11.3 mm; the USB-A to USB-C cord from the
Pi to the phone is 214 mm and bends. The phone's top end (the camera) goes to the left, its
port to the right, screen up: then the camera sits near the front edge, over the floor's
camera window. Both plugs stick out through notches in the right wall and the cord loops
between them outside (the phone plus a plug and its bend is ~200 mm, more than the 180 mm bed).

Parts (each modelled in its print orientation, Z up, each fits a 180 x 180 x 180 mm bed, no
supports):

- ``body``: back plate (two keyhole slots), sides, floor, shelf and top in one piece. Print
  lying on its back plate. The floor has the camera window (open to the front), the PIR dome
  hole (a teardrop so it prints) with two M2 bosses for the HC-SR501, and a rib the phone
  rests against. The shelf has a hole for the PIR wires and four M3 holes for the Pi tray.
- ``pi_tray``: the Pi 3 on four M2.5 standoffs; 4 x M3 x 6 screws hold it to the shelf.
  Print flat.
- ``front_panel``: slides down into grooves in the side walls from the top; one M3 thumb
  screw through its tab into the top holds it. Vent slots in front of the Pi. Print face down.

``enclosure`` is everything as it hangs, with stand-ins for the phone, the Pi and the PIR.

Run with text-to-cad (https://github.com/earthtojake/text-to-cad) to see it in the CAD viewer:
    cad run enclosure/enclosure.py
or with plain build123d to write STL + STEP files into enclosure/out/:
    python enclosure/enclosure.py --export
"""
import math
import sys
from pathlib import Path

import build123d as bd

try:  # text-to-cad's decorator; without it the functions just return shapes
    from cad import model
except ImportError:  # pragma: no cover
    def model(fn):
        return fn

# --- Print settings -----------------------------------------------------------------------
FIT = 0.6           # clearance per side around the phone
FILLET = 2.0        # outer vertical edges of the panel / tray

# --- Phone (Galaxy S20 FE in its case, measured) ------------------------------------------
CASE_L = 165.0      # length (along X)
CASE_W = 80.0       # width (along Y)
CASE_T = 11.3       # thickness
PHONE_GAP = 2.7     # head room over the phone, so it slides in under the shelf
# Camera window in the floor, measured from the phone's top end (left) and its front edge.
CAM_FROM_TOP = (3.0, 60.0)
CAM_DEPTH = 42.0
# USB-C plug overmould where it leaves through the right wall
USB_C_NOTCH = (16.0, 11.0)   # width along Y, height

# --- Raspberry Pi 3 -----------------------------------------------------------------------
PI_L, PI_W = 85.0, 56.0
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]  # from the SD end, power edge
STANDOFF_H, STANDOFF_D, STANDOFF_HOLE = 5.0, 6.0, 2.2   # M2.5 self-tapping
PCB_T = 1.6
PI_POWER_X = 10.6   # micro-USB centre from the SD end, on the power edge
PI_PLUG_ROOM = 25.0  # behind the power edge for the micro-USB plug
PI_COMPARTMENT_H = 36.0  # shelf top to top plate: tray 3 + standoffs 5 + board + jumpers on GPIO
TRAY_T = 3.0
TRAY_MARGIN = 7.0   # around the board, room for the M3 screws
TRAY_SCREW = 3.4
SHELF_PILOT = 2.6   # M3 self-tapping

# --- HC-SR501 PIR: 32 x 24 mm board, 2 mm holes 28 mm apart on the long axis, 23 mm dome --
PIR_DOME_HOLE = 23.5
PIR_HOLE_PITCH = 28.0
PIR_BOSS_D, PIR_BOSS_HOLE, PIR_BOSS_H = 5.0, 1.8, 2.5   # M2 self-tapping; lens flange height
PIR_STRIP = 38.0    # depth of the strip behind the phone that holds the PIR
PIR_X = 34.0        # dome centre from the inner left wall
RIB_H = 6.0         # phone stop between the PIR strip and the phone

# --- Body ---------------------------------------------------------------------------------
BACK = 6.0          # back plate, thick enough for the keyholes
SIDE = 4.0          # side walls (deep enough for the panel grooves)
FLOOR = 3.0
SHELF = 4.0
TOP = 3.0
PANEL_T = 3.0
GROOVE_CLR = 0.4    # groove width = panel + this
GROOVE_DEPTH = 1.5  # into each side wall
LIP = 2.0           # wall in front of the groove
POWER_SLOT_W = 14.0  # slot in the top for the Pi's power cable (micro-USB plug fits through)
WIRE_HOLE = 16.0    # diamond hole in the shelf for the PIR's jumper wires

# --- Keyhole slots (pan or round head screws <= 9 mm head, ~4 mm shank) -------------------
KEY_HEAD_D, KEY_SHANK_W, KEY_TRAVEL, KEY_CHANNEL = 9.5, 4.5, 10.0, 3.2
KEY_X_FROM_SIDES = 35.0

# --- Panel thumb screw --------------------------------------------------------------------
TAB_W, TAB_L, TAB_X = 24.0, 14.0, 40.0
PANEL_SCREW = 3.4

PETG = "#e8e4da"

# --- Derived layout (hung coordinates) ----------------------------------------------------
IN_X0 = SIDE
IN_X1 = SIDE + CASE_L + 2 * FIT
OUT_X = IN_X1 + SIDE
PHONE_Y0 = BACK + PIR_STRIP                  # the rib's front face
PHONE_Y1 = PHONE_Y0 + CASE_W + 2 * FIT
GROOVE_Y0 = PHONE_Y1 + 0.2
GROOVE_Y1 = GROOVE_Y0 + PANEL_T + GROOVE_CLR
OUT_Y = GROOVE_Y1 + LIP
SHELF_Z0 = FLOOR + CASE_T + PHONE_GAP
SHELF_Z1 = SHELF_Z0 + SHELF
TOP_Z0 = SHELF_Z1 + PI_COMPARTMENT_H
OUT_Z = TOP_Z0 + TOP
# Pi: USB end against the right wall, power edge toward the wall (component side up).
BOARD_X0 = IN_X1 - 1.0 - PI_L
BOARD_Y0 = BACK + PI_PLUG_ROOM
BOARD_Z0 = SHELF_Z1 + TRAY_T + STANDOFF_H
TRAY_X0, TRAY_X1 = BOARD_X0 - TRAY_MARGIN, IN_X1 - 0.3
TRAY_Y0, TRAY_Y1 = BOARD_Y0 - TRAY_MARGIN, BOARD_Y0 + PI_W + TRAY_MARGIN
TRAY_SCREWS = [(TRAY_X0 + 3.5, TRAY_Y0 + 3.5), (TRAY_X0 + 3.5, TRAY_Y1 - 3.5),
               (TRAY_X1 - 3.5, TRAY_Y0 + 3.5), (TRAY_X1 - 3.5, TRAY_Y1 - 3.5)]
PIR_C = (IN_X0 + PIR_X, BACK + 13.5)  # board clears the back plate; the hole's tip clears the rib


def _box(x0, y0, z0, x1, y1, z1):
    """Axis-aligned box from two corners."""
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * bd.Box(x1 - x0, y1 - y0, z1 - z0)


def _zcyl(x, y, z0, z1, d):
    return bd.Pos(x, y, (z0 + z1) / 2) * bd.Cylinder(d / 2, z1 - z0)


def _keyhole(plane, depth, up):
    """Keyhole cutter: ``plane`` origin = entry hole centre on the wall-side face, its Z into
    the part; ``up`` = the way the screw slides, a unit (dx, dy) in the plane's X/Y."""
    ux, uy = up
    end = (ux * KEY_TRAVEL, uy * KEY_TRAVEL)
    ang = 90 if ux == 0 else 0
    slot_c = bd.Pos(end[0] / 2, end[1] / 2, 0)

    def cyl(d, h, at=(0, 0)):
        return bd.Pos(at[0], at[1], h / 2) * bd.Cylinder(d / 2, h)

    def bar(w, h):
        return slot_c * bd.Rot(0, 0, ang) * bd.Pos(0, 0, h / 2) * bd.Box(KEY_TRAVEL, w, h)

    entry = cyl(KEY_HEAD_D, depth)
    shank = bar(KEY_SHANK_W, depth) + cyl(KEY_SHANK_W, depth, end)
    channel = bar(KEY_HEAD_D, KEY_CHANNEL) + cyl(KEY_HEAD_D, KEY_CHANNEL, end)
    return plane * (entry + shank + channel)


def _teardrop_z(x, y, z0, z1, d):
    """Vertical (hung) hole with its point toward +Y, which is up when the body prints on its
    back: prints without a sagging crown. The tip is cut flat at 1.3 r (a ~3 mm bridge) so it
    stops short of the phone rib."""
    r = d / 2
    tip = bd.Pos(x, y + r / math.sqrt(2), (z0 + z1) / 2) * bd.Rot(0, 0, 45) * bd.Box(r, r, z1 - z0)
    tip &= _box(x - r, y, z0, x + r, y + 1.3 * r, z1)
    return _zcyl(x, y, z0, z1, d) + tip


def _diamond_z(x, y, z0, z1, d):
    return bd.Pos(x, y, (z0 + z1) / 2) * bd.Rot(0, 0, 45) * bd.Box(d / math.sqrt(2), d / math.sqrt(2), z1 - z0)


# --- Body (hung coordinates) --------------------------------------------------------------
def body_hung():
    b = _box(0, 0, 0, OUT_X, OUT_Y, OUT_Z)
    b = bd.fillet(b.edges().filter_by(bd.Axis.Y).group_by(bd.Axis.Z)[-1], 2.0)  # round the top
    # hollow: phone bay and Pi compartment, open at the front
    b -= _box(IN_X0, BACK, FLOOR, IN_X1, OUT_Y + 1, SHELF_Z0)
    b -= _box(IN_X0, BACK, SHELF_Z1, IN_X1, OUT_Y + 1, TOP_Z0)
    # the top plate stops at the groove so the panel drops in from above
    b -= _box(IN_X0, GROOVE_Y0, TOP_Z0 - 1, IN_X1, OUT_Y + 1, OUT_Z + 1)
    # the shelf stops at the groove too (the panel passes in front of it)
    b -= _box(IN_X0, GROOVE_Y0, SHELF_Z0 - 1, IN_X1, OUT_Y + 1, SHELF_Z1 + 1)
    # panel grooves in both side walls, floor to top
    b -= _box(IN_X0 - GROOVE_DEPTH, GROOVE_Y0, FLOOR, IN_X1 + GROOVE_DEPTH, GROOVE_Y1, OUT_Z + 1)

    # floor: camera window, open to the front (phone top end is on the left)
    ph_x0 = IN_X0 + FIT
    b -= _box(ph_x0 + CAM_FROM_TOP[0], PHONE_Y1 - FIT - CAM_DEPTH, -1,
              ph_x0 + CAM_FROM_TOP[1], OUT_Y + 1, FLOOR + 0.01)
    # floor: PIR dome hole and bosses
    px, py = PIR_C
    b -= _teardrop_z(px, py, -1, FLOOR + 1, PIR_DOME_HOLE)
    for dx in (-PIR_HOLE_PITCH / 2, PIR_HOLE_PITCH / 2):
        b += _zcyl(px + dx, py, FLOOR - 0.01, FLOOR + PIR_BOSS_H, PIR_BOSS_D)
        b -= _zcyl(px + dx, py, FLOOR + 0.3, FLOOR + PIR_BOSS_H + 0.1, PIR_BOSS_HOLE)
    # phone stop rib: upright face toward the phone, slope toward the wall (~53 degrees from the bed as printed), 1 mm flat
    rib = bd.extrude(bd.Plane.YZ * bd.Polygon((PHONE_Y0 - 1.0 - 1.35 * RIB_H, FLOOR - 0.01), (PHONE_Y0, FLOOR - 0.01),
                                              (PHONE_Y0, FLOOR + RIB_H), (PHONE_Y0 - 1.0, FLOOR + RIB_H), align=None),
                     IN_X1 - IN_X0)
    b += bd.Pos(IN_X0, 0, 0) * rib

    # right wall: USB-C plug notch (phone port, mid-thickness), open to the front
    port_y = (PHONE_Y0 + PHONE_Y1) / 2
    port_z = FLOOR + CASE_T / 2
    b -= _box(IN_X1 - 1, port_y - USB_C_NOTCH[0] / 2, port_z - USB_C_NOTCH[1] / 2,
              OUT_X + 1, OUT_Y + 1, port_z + USB_C_NOTCH[1] / 2)
    # right wall: the Pi's USB / Ethernet jacks, open to the front
    b -= _box(IN_X1 - 1, BOARD_Y0 + 1.0, BOARD_Z0 + 0.5, OUT_X + 1, OUT_Y + 1, BOARD_Z0 + PCB_T + 17.0)

    # shelf: hole for the PIR wires, pilot holes for the tray
    b -= _diamond_z(px, py + 2.0, SHELF_Z0 - 1, SHELF_Z1 + 1, WIRE_HOLE)
    for x, y in TRAY_SCREWS:
        b -= _zcyl(x, y, SHELF_Z0 - 1, SHELF_Z1 + 1, SHELF_PILOT)

    # top: slot for the power cable over the micro-USB, open to the front
    pwr_x = BOARD_X0 + PI_POWER_X
    b -= _box(pwr_x - POWER_SLOT_W / 2, BACK + 4, TOP_Z0 - 1, pwr_x + POWER_SLOT_W / 2, OUT_Y + 1, OUT_Z + 1)
    # top: pilot hole for the panel's thumb screw
    b -= _zcyl(IN_X0 + TAB_X, GROOVE_Y0 - TAB_L / 2, TOP_Z0 - 1, OUT_Z + 1, SHELF_PILOT)

    # vents in the left wall beside the Pi, long front-to-back so they print without bridges
    for i in range(4):
        z = SHELF_Z1 + 7 + i * 6.5
        b -= _box(-1, BOARD_Y0, z, IN_X0 + 1, BOARD_Y0 + PI_W, z + 3)

    # keyholes in the back plate; the screw slides toward +Z
    for x in (KEY_X_FROM_SIDES, OUT_X - KEY_X_FROM_SIDES):
        plane = bd.Plane(origin=(x, 0, SHELF_Z1 + 10), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
        b -= _keyhole(plane, BACK, (0, -1))  # plane local -Y = global +Z
    return b


def tray_hung():
    t = _box(TRAY_X0, TRAY_Y0, SHELF_Z1, TRAY_X1, TRAY_Y1, SHELF_Z1 + TRAY_T)
    t = bd.fillet(t.edges().filter_by(bd.Axis.Z), FILLET)
    for x, y in TRAY_SCREWS:
        t -= _zcyl(x, y, SHELF_Z1 - 1, SHELF_Z1 + TRAY_T + 1, TRAY_SCREW)
    for hx, hy in PI_HOLES:
        x, y = BOARD_X0 + hx, BOARD_Y0 + hy
        t += _zcyl(x, y, SHELF_Z1 + TRAY_T - 0.01, BOARD_Z0, STANDOFF_D)
        t -= _zcyl(x, y, SHELF_Z1 + 1.0, BOARD_Z0 + 1, STANDOFF_HOLE)
    # a window under the middle of the board saves plastic and lets air through
    t -= _box(BOARD_X0 + 12, BOARD_Y0 + 10, SHELF_Z1 - 1, BOARD_X0 + 52, BOARD_Y0 + 46, SHELF_Z1 + TRAY_T + 1)
    return t


def panel_hung():
    g = GROOVE_CLR / 2
    x0, x1 = IN_X0 - GROOVE_DEPTH + 0.3, IN_X1 + GROOVE_DEPTH - 0.3
    y0, y1 = GROOVE_Y0 + g, GROOVE_Y0 + g + PANEL_T
    p = _box(x0, y0, FLOOR + 0.3, x1, y1, OUT_Z)
    # tab over the top plate for the thumb screw
    tx = IN_X0 + TAB_X
    tab = _box(tx - TAB_W / 2, GROOVE_Y0 - TAB_L, OUT_Z, tx + TAB_W / 2, y1, OUT_Z + 3.0)
    p += tab
    p -= _zcyl(tx, GROOVE_Y0 - TAB_L / 2, OUT_Z - 1, OUT_Z + 4, PANEL_SCREW)
    # vents in front of the Pi
    for i in range(9):
        x = BOARD_X0 + 6 + i * 8.5
        p -= _box(x, y0 - 1, SHELF_Z1 + 8, x + 3.5, y1 + 1, TOP_Z0 - 6)
    return p


def _on_bed(shape):
    bb = shape.bounding_box()
    return bd.Pos(-bb.min.X, -bb.min.Y, -bb.min.Z) * shape


def _part(shape, label):
    shape.label = label
    shape.color = PETG
    return shape


@model
def body():
    """Print orientation: back plate on the bed."""
    return _part(_on_bed(bd.Rot(90, 0, 0) * body_hung()), "body")


@model
def pi_tray():
    return _part(_on_bed(tray_hung()), "pi_tray")


@model
def front_panel():
    """Print orientation: outer face on the bed, tab up."""
    return _part(_on_bed(bd.Rot(-90, 0, 0) * panel_hung()), "front_panel")


@model
def enclosure():
    """Everything as it hangs, with stand-ins for the phone, the Pi and the PIR."""
    parts = [_part(body_hung(), "body"), _part(tray_hung(), "pi_tray"), _part(panel_hung(), "front_panel")]
    parts[2].color = "#e8e4dacc"
    phone = _box(IN_X0 + FIT, PHONE_Y0 + FIT, FLOOR, IN_X1 - FIT, PHONE_Y1 - FIT, FLOOR + CASE_T)
    pi = _box(BOARD_X0, BOARD_Y0, BOARD_Z0, BOARD_X0 + PI_L, BOARD_Y0 + PI_W, BOARD_Z0 + PCB_T)
    pi += _box(BOARD_X0 + PI_L - 21, BOARD_Y0 + 2, BOARD_Z0 + PCB_T, BOARD_X0 + PI_L + 2, BOARD_Y0 + 54, BOARD_Z0 + PCB_T + 16)
    px, py = PIR_C
    pir = _box(px - 16, py - 12, FLOOR + PIR_BOSS_H, px + 16, py + 12, FLOOR + PIR_BOSS_H + 1.6)
    pir += _zcyl(px, py, FLOOR - 9, FLOOR + PIR_BOSS_H, 23)
    for shape, label, color in ((phone, "phone", "#2b2d42"), (pi, "raspberry_pi", "#2a9d4b"), (pir, "pir", "#f4f4f4")):
        shape.label, shape.color = label, color
        parts.append(shape)
    return bd.Compound(children=parts, label="litterbox_enclosure")


def _shape(x):
    return getattr(x, "shape", x)


if __name__ == "__main__":
    parts = {"body": body(), "pi_tray": pi_tray(), "front_panel": front_panel()}
    whole = enclosure()
    if "--export" in sys.argv:
        out = Path(__file__).parent / "out"
        out.mkdir(exist_ok=True)
        for old in out.glob("*"):
            old.unlink()
        for name, p in parts.items():
            s = _shape(p)
            bb = s.bounding_box()
            print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, valid={s.is_valid}")
            bd.export_stl(s, str(out / f"{name}.stl"), tolerance=0.02, angular_tolerance=0.2)
            bd.export_step(s, str(out / f"{name}.step"))
        bd.export_step(_shape(whole), str(out / "enclosure_assembly.step"))
        print("wrote", out)
