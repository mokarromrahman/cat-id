import time
import tempfile
import os
import io
import argparse
from ppadb.client import Client as AdbClient


# Digital zoom applied to every photo before upload (a crop; the phone itself stays at 1x).
# ZOOM: 2 keeps half the width and height, 1 = off. ZOOM_X / ZOOM_Y: centre of the kept part,
# as a fraction of the upright photo (0 = left/top, 1 = right/bottom). Try other numbers with
# `python phone_control.py <photo> --zoom 2 --x 0.68 --y 0.58`, then change them here.
ZOOM = 2.0
ZOOM_X = 0.68
ZOOM_Y = 0.58


def zoom_box(size, zoom, x, y):
    """Pixel box (left, top, right, bottom) keeping 1/zoom of the width and height around
    (x, y). Slid back inside the photo if it would go past an edge."""
    w, h = size
    cw, ch = round(w / zoom), round(h / zoom)
    left = min(max(round(x * w - cw / 2), 0), w - cw)
    top = min(max(round(y * h - ch / 2), 0), h - ch)
    return left, top, left + cw, top + ch


def crop_zoom(data, zoom, x, y):
    """Digital zoom: crop the photo (JPEG bytes) to 1/zoom around (x, y), return JPEG bytes.
    zoom <= 1 returns the photo unchanged (Pillow isn't even needed then)."""
    if zoom <= 1:
        return data
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))  # upright, as the phone shows it
    out = io.BytesIO()
    im.crop(zoom_box(im.size, zoom, x, y)).convert("RGB").save(out, "JPEG", quality=92)
    return out.getvalue()


def zoom_preview(data, zoom, x, y, width=1000):
    """The whole photo, shrunk to `width` px, with the zoom box drawn in red (JPEG bytes)."""
    from PIL import Image, ImageDraw, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    box = zoom_box(im.size, max(zoom, 1), x, y)
    scale = width / im.width
    im = im.resize((width, round(im.height * scale)))
    ImageDraw.Draw(im).rectangle([round(v * scale) for v in box], outline=(255, 0, 0), width=6)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return out.getvalue()

class PhoneController(AdbClient):
    def __init__(self, host="127.0.0.1", port=5037):
        super().__init__(host=host, port=port)
        self.device = self.get_adb_device()
        self.camera_dir = "/sdcard/DCIM/Camera/"

    def get_adb_device(self):
        devices = self.devices()
        if len(devices) == 0:
            print("Error: No devices found. Check USB debugging.")
            return None
        return devices[0]

    def wake_up_screen(self):
        power_state = self.device.shell("dumpsys power | grep mHoldingDisplaySuspendBlocker")
        if "false" in power_state.lower() or "mHoldingDisplaySuspendBlocker=false" in power_state:
            print("[Phone] Screen is off. Waking it up...")
            self.device.shell("input keyevent 26") 
            time.sleep(0.5)

    def unlock_screen(self):
        self.device.shell("input keyevent 82") 
        time.sleep(0.5)

    def sleep_screen(self):
        self.device.shell("input keyevent 26") 
        print("[Phone] Screen returned to sleep.\n")

    def launch_camera(self):
        print("[Phone] Launching Standalone Camera...")
        self.device.shell("am start -a android.media.action.STILL_IMAGE_CAMERA")
        time.sleep(2.0) # Give the sensor time to adjust exposure

    def take_photo(self):
        print("[Phone] Taking and Saving Photo...")
        self.device.shell("input keyevent 27") # KEYCODE_CAMERA
        time.sleep(2.5) # Give the phone's processing system enough time to commit the file to disk

    def close_camera(self):
        self.device.shell("am force-stop com.sec.android.app.camera")

    def fetch_most_recent_photo(self):
        camera_dir = self.camera_dir

        # 1. Query the phone for the newest file name in the Camera directory
        # -t sorts by time (newest first)
        # -1 forces single-column output
        # head -n 1 grabs only the top row
        print("Finding the newest photo on the device...")
        command = f"ls -t1 {camera_dir} | head -n 1"
        newest_file = self.device.shell(command).strip()

        # Handle bytes decoding if the library returns raw binary text
        if isinstance(newest_file, bytes):
            newest_file = newest_file.decode('utf-8').strip()

        # Quick validation check to make sure the directory isn't empty
        if not newest_file or "no such file" in newest_file.lower():
            print("Error: No photos found in the camera directory.")
            return None

        print(f"Most recent file found: {newest_file}")
        remote_path = os.path.join(camera_dir, newest_file).replace("\\", "/")

        # 2. Stream the file directly into a RAM buffer using shell_stream
        print(f"Streaming {newest_file} into RAM buffer...")
        
        # Create an ephemeral temp file that gets wiped out automatically
        with tempfile.NamedTemporaryFile() as tmp_file:
            # Safely use ppadb's native pull method to write directly to the buffer descriptor
            self.device.pull(remote_path, tmp_file.name)
            
            # Read the raw binary out of the temp descriptor
            tmp_file.seek(0)
            file_bytes = tmp_file.read()

        # Wrap raw bytes in your io.BytesIO stream
        image_buffer = io.BytesIO(file_bytes)
        return image_buffer, newest_file


def trigger_covert_photo(device: PhoneController):
    if not device:
        print("No device connected. Cannot trigger photo.")
        return
    
    # 1. Wake up the screen if it's off
    device.wake_up_screen()

    # 2. Unlock the screen 
    device.unlock_screen()
    time.sleep(0.5)

    # 3. Launch standalone Camera (This mode auto-saves photos)
    device.launch_camera()
    time.sleep(2.0) # Give the sensor time to adjust exposure

    # 4. Trigger the Shutter (Keyevent 27 instructs standard apps to capture and save)
    device.take_photo()

    # 5. Force close camera and sleep
    device.close_camera()
    device.sleep_screen()

def save_zoom_test(data, zoom, x, y):
    """Writes zoom_test_full.jpg (whole photo + red box) and zoom_test_crop.jpg (what gets sent)."""
    with open("zoom_test_full.jpg", "wb") as f:
        f.write(zoom_preview(data, zoom, x, y))
    with open("zoom_test_crop.jpg", "wb") as f:
        f.write(crop_zoom(data, zoom, x, y))
    print(f"zoom {zoom} at x={x} y={y}: wrote zoom_test_full.jpg and zoom_test_crop.jpg")


def main():
    """Test tool. With a photo file: try zoom numbers on it (no phone needed).
    Without: press Enter to take a photo with the phone, then the same.
    Numbers default to ZOOM / ZOOM_X / ZOOM_Y; --zoom/--x/--y override them for this run."""
    ap = argparse.ArgumentParser()
    ap.add_argument("photo", nargs="?", help="existing photo to try the zoom on")
    ap.add_argument("--zoom", type=float, default=ZOOM)
    ap.add_argument("--x", type=float, default=ZOOM_X)
    ap.add_argument("--y", type=float, default=ZOOM_Y)
    args = ap.parse_args()

    if args.photo:
        with open(args.photo, "rb") as f:
            save_zoom_test(f.read(), args.zoom, args.x, args.y)
        return

    phone = PhoneController()
    if phone.device is None:
        return
    print("==================================================")
    print(f"Connected to: {phone.device.get_serial_no()}")
    print("Press [ENTER] in this terminal to trigger a photo.")
    print("Type 'exit' and press [ENTER] to quit.")
    print("==================================================")

    while True:
        user_input = input("\nReady to shoot. Press [ENTER]...")

        if user_input.strip().lower() == 'exit':
            print("Exiting test script.")
            break

        trigger_covert_photo(phone)
        result = phone.fetch_most_recent_photo()
        if result:
            image_buffer, filename = result
            print(f"Captured {filename}.")
            try:
                save_zoom_test(image_buffer.getvalue(), args.zoom, args.x, args.y)
            except Exception as e:
                print(f"Zoom test failed: {e}")

if __name__ == "__main__":
    main()
