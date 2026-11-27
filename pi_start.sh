#!/usr/bin/env bash
# Raspberry Pi: start everything pi_trigger.py needs, then run it.
#   1. start the adb server and wait for the phone (USB debugging allowed)
#   2. turn on the phone's battery protection (Samsung "Protect battery": stops charging at 85%)
#   3. activate the virtual env
#   4. run pi_trigger.py
# Usage: ./pi_start.sh   (from anywhere; it cds to its own folder so .env is found)
# Optional env: CAT_ID_VENV (default ~/venv/cat-id), PHONE_WAIT (seconds, default 60).
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"
VENV="${CAT_ID_VENV:-$HOME/venv/cat-id}"
PHONE_WAIT="${PHONE_WAIT:-60}"

# 1. adb
echo "[start] starting adb server..."
adb start-server
echo "[start] waiting up to ${PHONE_WAIT}s for the phone..."
if ! timeout "$PHONE_WAIT" adb wait-for-device; then
    echo "[start] phone not ready. adb devices says:"
    adb devices
    echo "[start] 'unauthorized': unlock the phone and tap Allow on 'Allow USB debugging?'."
    echo "[start] nothing listed: check the cable and Developer options > USB debugging."
    exit 1
fi
echo "[start] phone connected: $(adb get-serialno)"

# 2. battery protection (the phone is plugged in all the time). Samsung only lets this cap
# at 85%; a failure here is only a warning, the script still starts.
if adb shell settings put global protect_battery 1; then
    echo "[start] Protect battery: $(adb shell settings get global protect_battery | tr -d '\r') (1 = on, 85% max)"
else
    echo "[start] warning: couldn't turn on Protect battery; set it on the phone instead."
fi

# 3. virtual env
if [ ! -f "$VENV/bin/activate" ]; then
    echo "[start] no virtual env at $VENV (set CAT_ID_VENV)."
    exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# 4. the trigger script (exec: Ctrl+C or a service stop goes straight to it)
echo "[start] running pi_trigger.py"
exec python pi_trigger.py
