# cat-id

Identifies Litten vs Shinx from a photo and posts the result to Discord.

## 1. Prepare data (on the server)
    data/Litten/*.jpg
    data/Shinx/*.jpg
    data/neither/*.jpg    # empty litterbox, people, other animals, blurry shots

Fast way to sort 1700 photos: put them all in `inbox/`, start the service, and
tap through `http://SERVER:8000/label` on your phone. Or bootstrap: sort ~50 of
each cat by hand, train, then let the model pre-sort the rest into the inbox.

## 2. Train (one-off, CPU is fine: minutes for 1700 images)
    python -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt
    python train.py

## 3. Run
    export DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
    export COUGH_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
    export API_KEY=choose-a-secret
    docker compose up -d --build

Check: `curl http://SERVER:8000/health`
Test:  `curl -F file=@cat.jpg -F key=$API_KEY http://SERVER:8000/identify`

## 3b. Away from home (Tailscale)
The `tailscale` service in `docker-compose.yml` puts cat-id on your tailnet. Nothing is opened
on the router, and the tailnet sees only the cat-id container.

1. Tailscale admin console: turn on MagicDNS and HTTPS certificates (DNS page).
2. Access controls: replace the default allow-all with
   ```json
   {
     "tagOwners": { "tag:catserver": ["autogroup:admin"] },
     "grants": [
       { "src": ["autogroup:member"], "dst": ["tag:catserver"], "ip": ["443"] }
     ]
   }
   ```
3. Settings -> Keys: generate an auth key (one-off, pre-approved, tag `tag:catserver`) and
   put it in the server's `.env` as `TS_AUTHKEY=...`. Make sure `API_KEY` is set there too.
4. Deploy, then check: `docker compose exec tailscale tailscale serve status`.
5. Phones: install Tailscale, sign in (invite other people as tailnet members), and add the
   server in the app as `https://cat-id.<tailnet>.ts.net`.

## 4. Capture (Raspberry Pi)
The Pi takes photos with the S20 FE over adb on a USB cable (`phone_control.py`) and posts
them to `/litterbox`. The phone needs no Wi-Fi; only the Pi has to be on the network.

1. Phone: Settings > About phone > Software information > tap "Build number" 7 times, then
   Settings > Developer options > turn on "USB debugging". Plug it into the Pi.
2. Pi: `sudo apt install adb`, then `pip install -r pi_requirements.txt`.
3. `adb start-server`, then `adb devices`: tap "Allow" (and "Always allow from this
   computer") on the phone; the phone must show as `device`, not `unauthorized`.
4. `.env` next to `pi_trigger.py`: `SERVER`, `API_KEY`, optional `CAT_ID_USER` (default
   `pi`) and `CAT_ID_LOCATION` (default: the server's `PI_LOCATION`, `basement`).
5. `./pi_start.sh`: starts the adb server, waits for the phone, turns on the phone's
   "Protect battery" (stops charging at 85%), activates `~/venv/cat-id` (or `CAT_ID_VENV`)
   and runs `pi_trigger.py`. Run it again after every reboot (the adb server doesn't survive one).
6. Zoom: each photo is cropped on the Pi before upload (the phone stays at 1x). The numbers are
   `ZOOM`, `ZOOM_X`, `ZOOM_Y` at the top of `phone_control.py` (2x around 0.68, 0.58; `ZOOM = 1`
   turns it off). Try others first: `python phone_control.py some_photo.jpg --zoom 2 --x 0.68
   --y 0.58` writes `zoom_test_full.jpg` (red box) and `zoom_test_crop.jpg`; without a photo it
   takes a new one with the phone. Restart the service after changing them.

## 5. Improve over time
Every capture is saved to `inbox/` with the guess in its name. Label the misses at
/label, then press "Retrain model now".
    
