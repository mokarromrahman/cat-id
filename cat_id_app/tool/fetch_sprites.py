"""Copy the Shinx and Litten sprite sheets from PMD SpriteCollab into assets/sprites/.

Run once from anywhere (needs git on the PATH and Python 3.9+, stdlib only):

    python3 cat_id_app/tool/fetch_sprites.py

It does a shallow, sparse clone of https://github.com/PMDCollab/SpriteCollab into a temp
folder, copies the animations the app uses for each cat and colour, writes anim.json (frame
sizes and timings from each AnimData.xml) and CREDITS.md. The copied files are committed,
so the app never downloads anything.

Sprites are CC BY-NC 4.0 (non-commercial, credit required). See assets/sprites/CREDITS.md.
"""

import json
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = "https://github.com/PMDCollab/SpriteCollab"

# (cat, colour) -> folder inside the SpriteCollab repo.
SOURCES = {
    ("shinx", "default"): "sprite/0403",
    ("shinx", "shiny"): "sprite/0403/0000/0001",
    ("litten", "default"): "sprite/0725",
    ("litten", "shiny"): "sprite/0725/0000/0001",
}

# The animations the app plays (see lib/pets/pet.dart).
ANIMS = ["Walk", "Idle", "Sleep", "Hop", "Nod"]

DEST = Path(__file__).resolve().parent.parent / "assets" / "sprites"


def png_size(path):
    """Width and height from a PNG's IHDR chunk."""
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    return struct.unpack(">II", head[16:24])


def read_anim_data(folder):
    """{name: (frame_width, frame_height, [durations], source_name)} from AnimData.xml.
    An Anim with <CopyOf> reuses another animation's sheet and data."""
    root = ET.parse(folder / "AnimData.xml").getroot()
    anims = {}
    copies = {}
    for a in root.iter("Anim"):
        name = a.findtext("Name")
        copy_of = a.findtext("CopyOf")
        if copy_of:
            copies[name] = copy_of
            continue
        durations = [int(d.text) for d in a.iter("Duration")]
        anims[name] = (int(a.findtext("FrameWidth")), int(a.findtext("FrameHeight")), durations, name)
    for name, src in copies.items():
        if src in anims:
            anims[name] = anims[src]
    return anims


def credits_for(tracker, sprite_path, names):
    """Primary sprite credit for a folder like sprite/0403/0000/0001, as a display name."""
    parts = sprite_path.split("/")[1:]
    node = tracker[parts[0]]
    for p in parts[1:]:
        node = node["subgroups"][p]
    who = node.get("sprite_credit", {}).get("primary", "")
    return names.get(who, who) or "unknown"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "SpriteCollab"
        print("Cloning SpriteCollab (sparse, a few MB)...")
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPO, str(clone)],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(clone), "sparse-checkout", "set", "sprite/0403", "sprite/0725"],
            check=True,
        )

        tracker = json.loads((clone / "tracker.json").read_text(encoding="utf-8"))
        names = {}
        for line in (clone / "credit_names.txt").read_text(encoding="utf-8").splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) >= 2:
                names[cols[1]] = cols[0]

        credit_rows = []
        for (cat, colour), src in SOURCES.items():
            folder = clone / src
            out = DEST / cat / colour
            out.mkdir(parents=True, exist_ok=True)
            data = read_anim_data(folder)
            anim_json = {}
            for name in ANIMS:
                if name not in data:
                    sys.exit(f"{src} has no {name} animation")
                fw, fh, durations, sheet = data[name]
                png = folder / f"{sheet}-Anim.png"
                width, height = png_size(png)
                shutil.copyfile(png, out / f"{name}.png")
                anim_json[name] = {
                    "frameWidth": fw,
                    "frameHeight": fh,
                    "frames": width // fw,
                    "rows": height // fh,
                    "durations": durations,
                }
            (out / "anim.json").write_text(json.dumps(anim_json, indent=2) + "\n", encoding="utf-8")
            credit_rows.append((cat.capitalize(), colour, src, credits_for(tracker, src, names)))
            print(f"  {cat}/{colour}: {', '.join(ANIMS)}")

        lines = [
            "# Sprite credits",
            "",
            "Pixel sprites from PMD SpriteCollab, https://github.com/PMDCollab/SpriteCollab,",
            "licensed CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/):",
            "non-commercial use only, with credit. Pokémon © Nintendo / Creatures / GAME FREAK.",
            "",
            "| Cat | Colour | SpriteCollab folder | Sprite credit |",
            "|---|---|---|---|",
        ]
        lines += [f"| {c} | {col} | `{src}` | {who} |" for c, col, src, who in credit_rows]
        lines += ["", "Copied by `tool/fetch_sprites.py`. The heart is drawn in code (lib/pets/pet_painter.dart)."]
        (DEST / "CREDITS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Done: {DEST}")


if __name__ == "__main__":
    main()
