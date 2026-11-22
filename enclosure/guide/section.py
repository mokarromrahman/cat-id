import sys, numpy as np
sys.path.insert(0, "enclosure")
import enclosure as e, build123d as bd

def _chain(edges, pick):
    segs = []
    for ed in edges:
        n = 2 if ed.geom_type == bd.GeomType.LINE else 24
        segs.append([pick(ed @ t) for t in np.linspace(0, 1, n)])
    out = segs.pop(0)
    while segs:
        end = np.array(out[-1])
        best = min(range(len(segs)), key=lambda i: min(np.linalg.norm(np.array(segs[i][0]) - end),
                                                       np.linalg.norm(np.array(segs[i][-1]) - end)))
        s = segs.pop(best)
        if np.linalg.norm(np.array(s[-1]) - end) < np.linalg.norm(np.array(s[0]) - end):
            s = s[::-1]
        out += s
    return np.array(out)

def section(shape, axis, at):
    if axis == "x":
        pl = bd.Plane(origin=(at, 0, 0), x_dir=(0, 1, 0), z_dir=(1, 0, 0)); pick = lambda v: (v.Y, v.Z)
    else:
        pl = bd.Plane(origin=(0, at, 0), x_dir=(1, 0, 0), z_dir=(0, 1, 0)); pick = lambda v: (v.X, v.Z)
    cut = shape & (pl * bd.Rectangle(1000, 1000))
    return [(_chain(f.outer_wire().edges(), pick), [_chain(w.edges(), pick) for w in f.inner_wires()])
            for f in (cut.faces() if cut else [])]
