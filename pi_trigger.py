"""Runs on the Raspberry Pi 3.

IR/PIR sensor trips -> grab a still from the phone (IP Webcam app) ->
POST it to the cat-id server.

Wiring: sensor OUT -> GPIO17 (pin 11), VCC -> 5V (pin 2), GND -> pin 6.
Install: sudo apt install python3-gpiozero python3-requests
"""
import os
import time

import requests
from gpiozero import MotionSensor

from phone_control import PhoneController, trigger_covert_photo

SERVER = os.environ.get("SERVER", "http://192.168.1.116:8000/litterbox")
API_KEY = os.environ.get("API_KEY", "")
COOLDOWN = 20  # seconds; stops one visit from firing many alerts

sensor = MotionSensor(17)

phone = PhoneController()

# def capture_and_send():
#     shot = requests.get(PHONE_SNAPSHOT, timeout=10)
#     shot.raise_for_status()
#     r = requests.post(
#         SERVER,
#         files={"file": ("shot.jpg", shot.content, "image/jpeg")},
#         data={"key": API_KEY},
#         timeout=60,
#     )
#     print(time.strftime("%H:%M:%S"), r.status_code, r.text)

def capture_and_send(phone: PhoneController):
    trigger_covert_photo(phone)
    image_buffer, filename = phone.fetch_most_recent_photo()
    if image_buffer:
        try:
            r = requests.post(
                SERVER,
                files={"file": (filename, image_buffer, "image/jpeg")},
                data={"key": API_KEY},
                timeout=60,
            )
        except Exception as e:
            print("capture failed:", e)


while True:
    print("waiting for motion...")
    sensor.wait_for_motion()
    time.sleep(1.5)  # let the cat settle into frame
    try:
        print("motion detected")
        capture_and_send(phone)
    except Exception as e:
        print("capture failed:", e)
    time.sleep(COOLDOWN)
