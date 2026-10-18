import time
import tempfile
import os
import io
from ppadb.client import Client as AdbClient
#from PIL import Image

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

def main():
    phone = PhoneController()
    if not phone:
        return
    print("==================================================")
    print(f"Connected to: {phone.device.get_serial_no()}")
    print("Press [ENTER] in this terminal to trigger a photo.")
    print("Type 'exit' and press [ENTER] to quit.")
    print("==================================================")

    while True:
        # Waits for you to physically interact with your MacBook keyboard
        user_input = input("\nReady to shoot. Press [ENTER]...")
        
        if user_input.strip().lower() == 'exit':
            print("Exiting test script.")
            break
            
        trigger_covert_photo(phone)
        image_buffer, filename = phone.fetch_most_recent_photo()

        if image_buffer:
            try:
                # 2. Tell Pillow to open and process the image directly out of RAM
                #image = Image.open(image_buffer)

                # 3. This tells macOS to open the image directly in 'Preview' app -  does not work on raspberry pi or linux
                print("Displaying image directly from RAM buffer...")
                #image.show()
                print(f"Success! Captured and streamed {filename} completely into RAM buffer.")
            except Exception as e:
                print(f"Error displaying image: {e}")

if __name__ == "__main__":
    main()
    