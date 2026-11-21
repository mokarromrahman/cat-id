"""Runs on the Raspberry Pi 3.

IR/PIR sensor trips -> phone_control.py takes a photo on the phone over adb (USB) and
copies it to the Pi -> POST it to the cat-id server.

The phone needs no Wi-Fi: adb and the photo copy go over the USB cable, and the Pi does
the upload over its own network connection.

Wiring: sensor OUT -> GPIO17 (pin 11), VCC -> 5V (pin 2), GND -> pin 6.
Install: sudo apt install adb; pip install -r pi_requirements.txt
Before running: adb start-server, then `adb devices` must list the phone as "device"
(accept the "Allow USB debugging?" prompt on the phone the first time).
Config in .env: SERVER, API_KEY, optional CAT_ID_USER (default pi), CAT_ID_LOCATION.
"""
import os
import time

import requests
from gpiozero import MotionSensor

from phone_control import PhoneController, trigger_covert_photo
from dotenv import load_dotenv

load_dotenv()

SERVER = os.environ.get("SERVER", "http://192.168.1.116:8000/litterbox")
API_KEY = os.environ.get("API_KEY", "")
# Recorded as the photo's reporter on the server (a seeded app_user). Not called USER,
# which the shell already sets to the login name.
CAT_ID_USER = os.environ.get("CAT_ID_USER", "pi")
# Which litterbox this Pi watches (a location name); not set = the server's PI_LOCATION (basement).
CAT_ID_LOCATION = os.environ.get("CAT_ID_LOCATION", "")
COOLDOWN = 20  # seconds; stops one visit from firing many alerts

sensor = MotionSensor(17)

phone = PhoneController()

def capture_and_send(phone: PhoneController):
    trigger_covert_photo(phone)
    image_buffer, filename = phone.fetch_most_recent_photo()
    if image_buffer:
        try:
            r = requests.post(
                SERVER,
                files={"file": (filename, image_buffer, "image/jpeg")},
                data={"key": API_KEY, "user": CAT_ID_USER,
                      **({"location": CAT_ID_LOCATION} if CAT_ID_LOCATION else {})},
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
