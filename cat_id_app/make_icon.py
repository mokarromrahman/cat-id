"""Make the Android launcher icons from a photo.

Run from the cat_id_app folder (needs Pillow: pip install pillow):
    python3 make_icon.py                         # uses ../img_src/app_icon.jpg
    python3 make_icon.py photo.jpg               # or another photo
    python3 make_icon.py photo.jpg preview.png   # also save a preview of the cropped icon

To frame the photo differently, change CX, CY and R below and run it again.
"""
import pathlib
import sys

from PIL import Image, ImageDraw, ImageOps

# The part of the photo the icon shows: a circle centred on (CX, CY) with radius R, in
# the photo's pixels. These suit img_src/app_icon.jpg (2560x1440, both cats' faces).
CX, CY, R = 1315, 600, 730

RES = pathlib.Path("android/app/src/main/res")
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}

src = sys.argv[1] if len(sys.argv) > 1 else "../img_src/app_icon.jpg"
preview = sys.argv[2] if len(sys.argv) > 2 else None
img = Image.open(src).convert("RGB")
w, h = img.size

# Android 8+ icons are a 108dp square, and the phone shows only about the middle 72dp
# (cut to a circle, rounded square, ...). So the whole square is 1.5x the part we want.
side = int(R * 2 * 108 / 72)

# That square can run past the edge of the photo. Fill around it with mirrored copies of
# the photo, so any bit that shows looks like a continuation rather than a flat band.
pad = side
mirrored = Image.new("RGB", (w + 2 * pad, h + 2 * pad))
for i, flip_x in enumerate((True, False, True)):
    for j, flip_y in enumerate((True, False, True)):
        tile = img
        if flip_x:
            tile = ImageOps.mirror(tile)
        if flip_y:
            tile = ImageOps.flip(tile)
        mirrored.paste(tile, (pad + (i - 1) * w, pad + (j - 1) * h))
x0, y0 = CX - side // 2 + pad, CY - side // 2 + pad
fg = mirrored.crop((x0, y0, x0 + side, y0 + side))

# Older Android (before 8) uses a plain square icon: just the part that would show.
inner = fg.crop((side // 6, side // 6, side * 5 // 6, side * 5 // 6))

for name, k in DENSITIES.items():
    folder = RES / f"mipmap-{name}"
    fg.resize((round(108 * k),) * 2, Image.LANCZOS).save(folder / "ic_launcher_foreground.png")
    inner.resize((round(48 * k),) * 2, Image.LANCZOS).save(folder / "ic_launcher.png")

# Tells Android 8+ to use the layers above. The photo fills the foreground, so the
# background only shows if a launcher draws outside it.
anydpi = RES / "mipmap-anydpi-v26"
anydpi.mkdir(exist_ok=True)
(anydpi / "ic_launcher.xml").write_text(
    """<?xml version="1.0" encoding="utf-8"?>
<!-- Made by make_icon.py. Android 8+ crops this to the phone's icon shape. The photo
     fills the foreground, so the background only shows if a launcher draws outside it. -->
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@android:color/black"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
"""
)

if preview:
    # How a launcher would draw it: as a circle, and as a rounded square.
    big = fg.resize((432, 432), Image.LANCZOS).crop((72, 72, 360, 360))
    out = Image.new("RGB", (620, 300), "white")
    for n, shape in enumerate(("circle", "rounded")):
        mask = Image.new("L", big.size, 0)
        draw = ImageDraw.Draw(mask)
        if shape == "circle":
            draw.ellipse((0, 0, 287, 287), fill=255)
        else:
            draw.rounded_rectangle((0, 0, 287, 287), radius=70, fill=255)
        out.paste(big, (6 + n * 310, 6), mask)
    out.save(preview)
    print(f"Preview saved to {preview}")

print("App icons written.")
