import time
import os
from ppadb.client import Client as AdbClient

class PhoneController(AdbClient):
    def __init__(self, host="127.0.0.1", port=5037):
        super().__init__(host=host, port=port)
        self.device = self.get_adb_device()

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


# def main():
#     phone = PhoneController()
#     if not phone:
#         return
#     print("==================================================")
#     print(f"Connected to: {phone.device.get_serial_no()}")
#     print("Press [ENTER] in this terminal to trigger a photo.")
#     print("Type 'exit' and press [ENTER] to quit.")
#     print("==================================================")

#     while True:
#         # Waits for you to physically interact with your MacBook keyboard
#         user_input = input("\nReady to shoot. Press [ENTER]...")
        
#         if user_input.strip().lower() == 'exit':
#             print("Exiting test script.")
#             break
            
#         trigger_covert_photo(phone)

# if __name__ == "__main__":
#     main()
