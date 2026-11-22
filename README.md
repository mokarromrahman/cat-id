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
2. Pi: `sudo apt install adb libopenjp2-7`, then `pip install -r pi_requirements.txt`. Pillow
   from piwheels needs `libopenjp2-7`; check with
   `python -c "from PIL import Image"` (`import PIL` alone doesn't load it).
3. `adb start-server`, then `adb devices`: tap "Allow" (and "Always allow from this
   computer") on the phone; the phone must show as `device`, not `unauthorized`.
4. `.env` next to `pi_trigger.py`: `SERVER`, `API_KEY`, optional `CAT_ID_USER` (default
   `pi`) and `CAT_ID_LOCATION` (default: the server's `PI_LOCATION`, `basement`).
5. `./pi_start.sh`: starts the adb server, waits for the phone, turns on the phone's
   "Protect battery" (stops charging at 85%), activates `~/venv/cat-id` (or `CAT_ID_VENV`)
   and runs `pi_trigger.py`. Use it to test by hand (Ctrl+C to stop); step 7 runs it at boot.
6. Zoom: each photo is cropped on the Pi before upload (the phone stays at 1x). The numbers are
   `ZOOM`, `ZOOM_X`, `ZOOM_Y` at the top of `phone_control.py` (2x around 0.68, 0.58; `ZOOM = 1`
   turns it off). Try others first: `python phone_control.py some_photo.jpg --zoom 2 --x 0.68
   --y 0.58` writes `zoom_test_full.jpg` (red box) and `zoom_test_crop.jpg`; without a photo it
   takes a new one with the phone. Restart the service after changing them.
7. Start at boot: a systemd service `cat-id-pi` runs `pi_start.sh` as `rpi` and restarts it
   10 s after it stops (phone not ready, crash). Create
   `/etc/systemd/system/cat-id-pi.service`:
   ```ini
   [Unit]
   Description=cat-id litterbox trigger (adb + pi_trigger.py)
   Wants=network-online.target
   After=network-online.target

   [Service]
   User=rpi
   WorkingDirectory=/home/rpi/dev/cat-id
   Environment=PYTHONUNBUFFERED=1
   ExecStart=/home/rpi/dev/cat-id/pi_start.sh
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```
   then `sudo systemctl daemon-reload` and `sudo systemctl enable --now cat-id-pi`.
   `User=rpi` matters: the phone trusts the adb key in `/home/rpi/.android/`, not root's.
   Stop the service before testing by hand (`./pi_start.sh`, `python phone_control.py`), or
   both react to motion.

### Pi logs and control
Everything `pi_start.sh` and `pi_trigger.py` print goes to the systemd journal
(`PYTHONUNBUFFERED=1` so lines show up straight away).

| What | Command |
| --- | --- |
| Is it running? (plus the last few lines) | `systemctl status cat-id-pi` |
| Follow the log live (Ctrl+C to stop watching) | `journalctl -u cat-id-pi -f` |
| Everything since the last boot | `journalctl -u cat-id-pi -b` |
| The last 100 lines | `journalctl -u cat-id-pi -n 100` |
| A time range | `journalctl -u cat-id-pi --since "1 hour ago"` (or `--since today`, `--since "2026-11-22 08:00"`) |
| Only errors | `journalctl -u cat-id-pi -p err` |
| Restart (after `git pull` or changing `.env`/zoom) | `sudo systemctl restart cat-id-pi` |
| Stop / start | `sudo systemctl stop cat-id-pi` / `sudo systemctl start cat-id-pi` |
| Don't start at boot any more | `sudo systemctl disable cat-id-pi` |

What a healthy start looks like: `[start] phone connected: ...`, `[start] Protect battery: 1`,
`[start] running pi_trigger.py`, then `waiting for motion...`; each visit adds `motion
detected`. `[start] phone not ready` repeating every ~10 s means adb can't see the phone
(cable, USB debugging, or `unauthorized`: allow it on the phone). `capture failed: ...` is a
photo or upload error. A server error (wrong `API_KEY`, 500) isn't logged yet, so check
Discord or `/label` if photos stop arriving.

## 5. Improve over time
Every capture is saved to `inbox/` with the guess in its name. Label the misses at
/label, then press "Retrain model now".
    
