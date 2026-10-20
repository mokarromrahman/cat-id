# cat_id_app

A small Android app for your cat-id server, for use on the home network.

| Tab | What it does | Server endpoint |
| --- | --- | --- |
| Identify | Pick a photo (gallery or camera) and see who it is. "Identify" returns the result only; "Identify + send to Discord" also posts it. | `POST /identify`, `POST /litterbox` |
| Label | The server's own label page, inside the app: label, crop, rotate, undo, history, delete, Retrain. | `GET /label` and its `/api/*` |
| Cough | Pick Litten or Shinx (same pictures and colours as the label page), add an optional note, and send a cough report to Discord. | `POST /cough` |
| Health | Model status, training photos per cat, how many captures are waiting, and a Retrain button. | `GET /health`, `POST /api/retrain` |

The Cough tab needs `COUGH_DISCORD_WEBHOOK` set on the server, and it loads the two pictures from the server's `/asset/` route (the files in `img_src/`), so they live in one place.

Tap the server name at the top (or the server icon) to add, edit, remove or switch between
**up to 5 servers**. Each is an IP address (port 8000 if you leave it out) plus its API key.
The app asks for the first one when you open it, then remembers them until you remove them.

## Where the API key lives

- Each server's key is saved with **flutter_secure_storage**. On Android that encrypts it with a
  key held in the Android Keystore, so it isn't readable from the phone's normal files.
- It is typed into the app once (Servers screen). It is **not in the code, the APK or git**.
  Never paste it into a `.dart` file: anyone with the APK could pull it out.
- The server list (names and addresses) is not secret and is kept in ordinary app storage.
- Removing a server deletes its key. Uninstalling the app deletes everything.
- The app talks plain `http://` to your server (it has no certificate), so the key travels
  unencrypted over your Wi-Fi. That is fine for a home network you trust; don't use the app
  over public Wi-Fi.
- Only `/identify` and `/litterbox` check the key. `/label`, `/health` and retrain don't ask
  for it, so keep the server off the internet (don't port-forward 8000).

## Set up (once, on your Mac)

1. **Install Flutter and the Android tools.** Follow https://docs.flutter.dev/get-started/install
   (pick macOS, then Android). Then run `flutter doctor` and fix anything it flags under
   Flutter and Android toolchain. You need Android Studio (or just its command-line tools).
2. **Turn on USB debugging on your phone:** Settings > About phone > Software information,
   tap Build number 7 times, then Settings > Developer options > USB debugging. Plug the phone in.
3. **From the repo root, run:**
   ```
   chmod +x cat_id_app/setup.sh
   ./cat_id_app/setup.sh
   ```
   This creates the Android project around `lib/`, adds the packages, and turns on internet
   access and plain-http for your home network.
4. **Run it on the phone:**
   ```
   cd cat_id_app
   flutter run --release
   ```
5. **Share it with the other person:** `flutter build apk --release`, then send
   `build/app/outputs/flutter-apk/app-release.apk`. On their phone, open the file and allow
   "install unknown apps" for whatever app they opened it from. They add their own server
   and key; nothing is shared between phones.

## Changing the app icon

The icon is made from `img_src/app_icon.jpg` by `make_icon.py`. To use a different photo,
or frame this one differently (change `CX`, `CY`, `R` at the top of the script):

```bash
cd cat_id_app
pip install pillow
python3 make_icon.py ../img_src/app_icon.jpg preview.png   # preview.png shows the result
```

Then rebuild the app. Some launchers keep the old icon until the phone restarts.

## If something goes wrong

- **"Can't reach 192.168.x.x:8000":** the phone must be on the home Wi-Fi, and
  `curl http://SERVER:8000/health` must work from another machine.
- **Wrong API key (401):** Servers > edit the server > fix the key.
- **Build error mentioning `minSdk`:** the setup script sets it to 24; check
  `android/app/build.gradle(.kts)` if you see it anyway.
- **Camera or gallery does nothing:** the first time, Android may ask for permission. Allow it.

## Keeping this in the cat-id repo

It lives in the `cat_id_app/` folder of the same repo. Your root `.gitignore` has `lib/` (from the
Python template), which would hide the app's `lib/` folder from git. Change these two lines:

```
/lib/
/lib64/
```

Flutter creates its own `.gitignore` inside `cat_id_app/` for build output. Add `cat_id_app/` to a
root `.dockerignore` so the server image build doesn't send the app along.
