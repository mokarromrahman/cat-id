"""Runs on the Raspberry Pi 3.

IR/PIR sensor trips -> grab a still from the phone (IP Webcam app) ->
POST it to the cat-id server.

Wiring: sensor OUT -> GPIO17 (pin 11), VCC -> 5V (pin 2), GND -> pin 6.
Install: sudo apt install python3-gpiozero python3-requests
"""
import os
import time

#import requests
from gpiozero import MotionSensor

SERVER = os.environ.get("SERVER", "http://192.168.1.116:8000/litterbox")
API_KEY = os.environ.get("API_KEY", "")
COOLDOWN = 20  # seconds; stops one visit from firing many alerts

sensor = MotionSensor(17)


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


while True:
    print("waiting for motion...")
    sensor.wait_for_motion()
    time.sleep(1.5)  # let the cat settle into frame
    try:
        #capture_and_send()
        print("motion detected")
    except Exception as e:
        print("capture failed:", e)
    time.sleep(COOLDOWN)
