# cat-id

Identifies which of two cats (Litten, Shinx) is in a photo, posts litterbox visits and
cough reports to Discord, and records photos, events and vet visits in Postgres. Runs on an
Ubuntu server on the home network (192.168.1.116:8000). Nothing is exposed to the internet: away
from home the app reaches it over Tailscale (`tailscale` sidecar in `docker-compose.yml`,
https://cat-id.<tailnet>.ts.net, only the owner's and Ashley's phones, only port 443).

## Working rules

- **Never commit or push.** The owner reviews and commits locally. Leave changes in the
  working tree and say which files changed.
- Don't remove existing functionality (endpoints, aliases, buttons) when changing something.
  Keep old routes working unless asked to remove them.
- Keep the top-of-file endpoint docs in `app.py` up to date when endpoints change.
- Ask before big design decisions; small, obvious choices are fine to make and mention.

## Layout

| Path | What it is |
| --- | --- |
| `embed.py` | DINOv2-small (`facebook/dinov2-small`) image embeddings; `open_image()` handles EXIF/HEIC |
| `train.py` | Embeds `data/<class>/` (jpg/jpeg/png/webp), caches by path in `embeddings_cache.npz`, fits `LogisticRegression(C=10, class_weight="balanced")`, writes `model.joblib`. Run from the repo root (paths are relative). |
| `app.py` | FastAPI server (in Docker). Endpoints below. |
| `db.py` | SQLAlchemy 2 models, connection, `safe_write`/`safe_read`, and the writers (picture, label, crop, archive, delete, undo, cough) that `app.py` and `replay_db_failed.py` share. |
| `vet_api.py` | `/vet_visit` routes (APIRouter included by `app.py`). |
| `events_api.py` | `/events`, `/event_types`, `/picture/{id}/image` for the app's Events tab (APIRouter included by `app.py`). |
| `alembic.ini`, `migrations/` | Alembic. `0001_initial_schema.py`: tables, CHECKs, audit trigger, `active_vet_visit` view, seed rows. `0002_location_and_litterbox_clean.py`: `location`, `litterbox_clean_event`, `location_id` on `picture`/`event`, backfill of the Pi's photos to basement. |
| `start.py` | Container entry point: waits up to 30 s for Postgres, runs `alembic upgrade head`, then starts uvicorn either way. |
| `replay_db_failed.py` | Replays `inbox/_db_failed.jsonl` (writes that failed while Postgres was down). |
| `sorter_core.py` | Framework-free photo sorter shared by `label.py` and `/label`: undo history, crop/rotate, archive, delete, log. Optional `on_action` callback (server only) updates the DB. |
| `ui/label.{html,css,js}` | The shared label page. Button colours: Litten `#d62828`, Shinx `#f4c20d`, neither `#9a9a9a`, both `#7b4bb5`. Server only: event-type picker and `?user=`. |
| `img_src/` | Pokémon-style button art (`litten_pokemon.png`, `shinx_pokemon.png`, ...) served at `/asset/<file>`; `app_icon.jpg` for the Android app. |
| `label.py` | Stdlib server for sorting photos on the Mac (127.0.0.1:8765), same page and API, no database. Must keep working on the Mac's Python 3.9. |
| `pi_trigger.py` | Raspberry Pi 3: gpiozero `MotionSensor(17)` -> `phone_control.py` takes a photo on a Galaxy S20 FE over adb -> POSTs it to `/litterbox` with `user=pi`. 20 s cooldown. Config via `.env` (`SERVER`, `API_KEY`, optional `CAT_ID_USER`, optional `CAT_ID_LOCATION`, sent as `location`). |
| `phone_control.py` | `PhoneController` (pure-python-adb): wake screen, take photo, fetch newest file from `/sdcard/DCIM/Camera/`. Needs an `adb` server running on the Pi. |
| `pi_requirements.txt` | Pi-only deps: pure-python-adb, gpiozero, lgpio, requests, python-dotenv |
| `cat_id_app/` | Flutter Android app (see below). Excluded in `.dockerignore`. Walking-cat sprites in `cat_id_app/assets/sprites/` (`tool/fetch_sprites.py`). |
| `Dockerfile`, `docker-compose.yml` | `python:3.14-slim`; bind mounts for `data/`, `inbox/`, `model.joblib`, `embeddings_cache.npz`, `hf_cache/`; `db` Postgres 18 service; `tailscale` sidecar (cat-id uses its network, so port 8000 is published on it; Serve config inline under `configs:` because `deploy.yml` checks out only the compose file; login kept in the `tailscale-state` volume; `TS_AUTHKEY` in `.env` for the first start). |

Not in git: `data/`, `inbox/`, `model.joblib`, `embeddings_cache.npz`, `hf_cache/`, `.env`.

## Server endpoints (`app.py`)

- `POST /identify` (multipart `file`, `key`, optional `user`): classify, save the photo to
  `inbox/` as `<unix>_<label>_<conf>.jpg`, return `{cat, best_guess, confidence, saved_as}`.
  No Discord. Below `MIN_CONF` (0.75) the `cat` is `"uncertain"`. Records a `picture` row
  (source `identify`) after the response.
- `POST /litterbox`: same as `/identify` (photo saved once, source `litterbox`), plus posts to
  `DISCORD_WEBHOOK_URL`. This is what the Pi calls. Optional form `location` (a `location.name`):
  the box the photo is of; missing = `PI_LOCATION` env (default `basement`). With form `cat`
  (plus optional `info`, `file`, `event_time`, `location`) it's a visit reported by hand from the
  app: handled like `/cough` (shared `report_event()`; db writer `litterbox_report`), the event
  is recorded now, photo source `litterbox`, `location` missing = not known, posted to
  `DISCORD_WEBHOOK_URL`, `null` if that isn't set. No `cat` and no `file` gives 400; an unknown
  location gives 400.
- `POST /litterbox_clean` (form `location`, `key`, optional `bag_changed` true/false (default
  false), `info`, `user`, `event_time`): records a `litterbox_clean_event` row (db writer
  `litterbox_clean`, after the response). `event_time` as for `/cough`; `server_timestamp` is
  the arrival time. No Discord. Returns `{status, location, message}`. Missing/unknown
  location, bad `bag_changed` or `event_time`: 400, nothing saved.
- `POST /cough` (form `cat`, `key`, optional `info`, `user`, `file`): records a cough event, posts a
  text report to `COUGH_DISCORD_WEBHOOK_URL`. Returns `null` (200) if that webhook isn't set
  (the event is still recorded). Checks the key but not the model. An optional photo is
  handled like `/identify`'s (model guess if the model is loaded, saved to `inbox/` for
  labeling, `picture` row with source `identify`), linked by `event.picture_id`, attached to
  the Discord post and returned as `photo`. Not an image: 400 and nothing is recorded.
  Optional `event_time` (ISO 8601 with a UTC offset; the app sends UTC): becomes the event's
  `event_timestamp` (missing = arrival time; future beyond 5 min of clock slack, no offset or
  unreadable: 400, nothing saved). The photo's `picture.event_timestamp` keeps the arrival
  time. Discord shows the event time, plus "(reported ...)" when it's over 5 min earlier.
- `GET|POST /vet_visit`, `PATCH|DELETE /vet_visit/{id}`, `POST /vet_visit/{id}/restore`: see
  `vet_api.py`. Key in the `X-API-Key` header. Need the DB: 503 if it's down.
- `GET /events` (`cat`, `type`, `from`, `to` as Edmonton days, `limit`, `before` cursor),
  `GET /event_types`, `GET /picture/{id}/image` (serves only files under `data/` or `inbox/`):
  see `events_api.py`. View only. Key in `X-API-Key`; 503 if the DB is down. Totals and chart
  data cover the whole filtered range and come with the first page only.
- `GET /health`: `{model_loaded, classes, photos: {class: count}, waiting_in_inbox, version,
  commit, litterboxes}`. `litterboxes`: per location `{location, name, last_cleaned,
  bag_last_changed}` (UTC, null if never), or null if the DB is down (`db.litterbox_status()`). `version`/`commit` come from the `CAT_ID_VERSION`/`CAT_ID_COMMIT` build args baked
  into the image (`release.yml` passes the tag and `github.sha`); a local build says `dev` and
  `null` unless you run `CAT_ID_COMMIT=$(git rev-parse HEAD) docker compose up -d --build`.
  The app's Health tab shows them ("Server v0.2.0", "Commit 433c253").
- `GET /label` (optional `?user=`) plus `/ui/*`, `/asset/*`, `/img/*`, `GET /api/config|state|log`,
  `POST /api/{label,crop,archive,undo,keep,delete}`, `POST /api/retrain`. `/api/config` adds
  `event_types`; `/api/state` adds `sources` for the queue.
  Old aliases kept on purpose: `POST /label` (form, `__delete__`), `POST /retrain`,
  `GET /inbox/{name}`.
- Label semantics: a class label moves the photo to `data/<class>/`; "both" goes to
  `inbox/_both`; Done/Skip goes to `inbox/_archived`; Delete really deletes (undoable in-session).
  Use `shutil.move`, not `Path.rename` (separate Docker bind mounts). The label buttons come from
  the folders in `data/`.
- `/identify`, `/litterbox`, `/litterbox_clean`, `/cough`, `/vet_visit`, `/events`, `/event_types` and
  `/picture/{id}/image` check `API_KEY`. `/label` and its
  `/api/*` routes don't, on purpose (owner's choice): anyone on the home network can label.

## Database (Postgres 18, SQLAlchemy 2 sync + Alembic, psycopg 3)

- Tables (all with `created_on`, `modified_by` -> `app_user`, `modified_on`): `app_user`
  (seeded `system`, `pi`, `Ashley`, `Mac`), `cat` (Litten, Shinx only; both born 2023-06-15,
  gotcha day 2023-11-21), `event_type` (`litterbox`/Litterbox, `cough`/Cough: code + display
  name), `label` (Litten, Shinx, neither, both, with optional cat), `picture`, `event`,
  `vet_visit`, `location` (`basement`/Basement, `master_bathroom`/Master Bathroom: unique `name`
  + `label_name`), `litterbox_clean_event`. View `active_vet_visit`. Diagram: https://claude.ai/artifact/NsFLSjW8gcAGmHAmhoJRYa
- A trigger on every table sets `modified_on` on insert/update (DBeaver edits too) and fills an
  empty `modified_by` with `system`. Integer identity IDs. No edit-history table.
- `user` on every request is an `app_user` name; missing or unknown means `system`.
- `picture`: one row per photo received (`event_timestamp` = UTC time the request arrived,
  model guess, `filename`, current `file_path`, `source`, `reporter_id`, `status`
  pending/labeled/archived/deleted, `final_label_id`, `labeled_on`, `labeled_by`,
  `model_version`, `location_id`: the box for `/litterbox` photos, null otherwise; crops copy it). A crop is its own row with `parent_picture_id`. Original filenames are
  unique; crop filenames aren't (same crop name can exist in two cat folders). Deleted photos
  keep their row.
- `event`: always a real cat. `location_id` (nullable): litterbox visits only, copied from the
  photo when labeling, or picked in the app for a hand report; coughs have none. Litterbox-type events come from labeling on `/label` (a
  Litten/Shinx label, plain or crop, with an event type) or from a hand report
  (`/litterbox` with `cat`). The picker defaults to `litterbox` for
  `/litterbox` photos and None otherwise; `event_type` missing means that default, `"none"`
  means no event. Never two events for the same original photo, cat and type. Undo deletes the
  event its action created (the only hard delete of events): for a whole photo, only events
  with `created_on >= labeled_on` (`labeled_on` is set with the DB's `now()` for this), so a
  cough linked to the photo survives undo. `event.picture_id` is unique, so labeling a photo
  that already has an event (a cough photo) makes no new one; crops still can. Coughs from `/cough` and hand-reported
  litterbox visits create an event directly (picture only if a photo was sent; unknown cat
  name -> no event). Cats/users with events can't be
  deleted.
- `litterbox_clean_event`: `location_id` (required), `event_timestamp` (when it was cleaned),
  `server_timestamp` (when the request arrived; differs from `created_on` only for a replayed
  row), `reporter_id`, `bag_changed` (bool, default false), `notes`. No cat, no photo, not in
  `/events`.
- `vet_visit`: `cat_id` nullable (pickups), `visit_date` (date), `appointment_time` (time,
  Edmonton clock), `doctor`, `clinic` (default `unknown`), `notes`, `reason` text[] (checkup,
  shots, emergency, food pickup, medication pickup, other; at least one), `weight_kg`
  numeric(5,2), `cost` numeric(10,2), `follow_up_date`, `reporter_id`, `deleted_on` (soft
  delete; `modified_by` = who deleted). "Both" = two independent rows saved in one request.
- A DB failure never breaks a request: `safe_write` appends the row to
  `inbox/_db_failed.jsonl` (replay: `docker compose exec cat-id python replay_db_failed.py`).
  After a connection failure requests skip the DB until a background probe (every 15 s) sees it
  again; picture/cough writes run after the response. If Postgres was down at startup,
  migrations didn't run: restart `cat-id` once it's back.
- `db` runs with `init: true`: without it, a leftover `docker exec`/healthcheck process that
  exits non-zero is adopted by Postgres, which then crash-restarts.
- Changing the schema: edit `db.py`, `alembic revision --autogenerate -m "..."` (in the
  container), review it, `alembic check` must say no changes. Recreate `active_vet_visit` if
  `vet_visit` gains columns (`SELECT *` is frozen at creation).
- `event.picture_id` stays nullable for every type (no trigger requiring a photo); the app
  shows a placeholder when there's none.
- Time zones: Edmonton is UTC-6 all year from Nov 2026 (tzdata 2026c; last clock change Mar 8,
  2026). The server uses the pip `tzdata` package (`PYTHONTZPATH=` in the Dockerfile) so an old
  base-image copy can't shift days by an hour. Day boundaries come from
  `events_api.local_midnight()`.
- Not built yet: the Databricks export (push batches of new rows
  to cloud storage for Auto Loader; select by `created_on`/`modified_on`, since events can be
  created long after `event_timestamp`).

## Android app (`cat_id_app/`)

Flutter, Android only, sideloaded (not on the Play Store). Tabs, in `kTabOrder` in
`lib/screens/home_screen.dart`: Health, Identify, Events, Vet, Label. Cough has no tab: the
Events tab's Add event menu (Litterbox / Cough / Clean Litterbox) opens `ReportEventScreen`
(`screens/report_event_screen.dart`, `ReportKind`) in a sheet: cat, When (date then time
picker; default "Now", any past date, not the future; sent as `event_time` in UTC), note,
optional photo
from gallery or camera, "Send to Discord" (a camera photo lost to Android closing the app
comes back on Identify). Litterbox also has "Which litterbox?" (Basement default, or Master
Bathroom). Clean Litterbox (`ReportKind.clean`): pick the box instead of a cat, When,
"Bag changed" switch, note, no photo, "Save" (no Discord). Locations are `kLitterboxLocations`
in `api.dart` (keep in step with the `location` table). The Identify tab only identifies (no Discord button; that moved
to Add event > Litterbox).

- Up to 5 servers saved (`server_store.dart`, SharedPreferences); each server's API key in
  `flutter_secure_storage` (Android Keystore). Plain http on the home network (`host:port`,
  port 8000 by default), or HTTPS through Tailscale Serve (`https://host`, port 443 by default;
  a `.ts.net` name typed without a scheme is HTTPS). `normalizeAddress` and `Server.baseUri`
  in `server_store.dart`; old saved `host:port` entries stay HTTP. Tests: `test/server_store_test.dart`.
- "Who am I" (`who_am_i.dart`): Ashley or Mac, one setting per phone, picked from the app bar.
  Sent as `user` on identify, litterbox, cough and vet requests, and as `?user=` on the Label
  web view. Not set means nothing is sent (server records `system`).
- Health tab: a Litterboxes card per location: "Last cleaned <day, time> (<ago>)", red with a
  warning icon when over 24 h or never (`kCleanOverdueAfter`), and "Bag was last changed <day,
  time>" (no highlight). Hidden for servers without `litterboxes`.
- Label tab is a WebView of the server's `/label`. Health and Label reload each time you
  switch to them; Identify, Events and Vet keep their state (Events: pull down to refresh).
- Events tab (`screens/events_screen.dart`), view only. Filters, one value each: cat (Both /
  Litten / Shinx), event (All / each type from `/event_types`), dates dropdown (Today, Last 7
  days (default), Last 30 days, This month, Custom range picker). Summary line, then a chart per
  event type (`fl_chart`; swipe between them when Event is All; swiping changes only the chart)
  with its own per-cat totals: Today = bars per hour, up to 31 days = side-by-side bars per day
  (Litten red, Shinx yellow), longer = a line per cat (per week past 183 days); tap for that
  bucket's counts. Event cards newest first, 50 at a time with Load more; photo thumbnails open
  full screen (model guess, labeler, sender); no photo = the cat's art dimmed with "No photo".
  Mockups: https://claude.ai/artifact/GExMht8zuX7qAbbSsNaUeQ.
- Vet tab (`screens/vet_screen.dart`): form (Litten / Shinx / Both / No cat; date defaults to
  today, time optional, clinic pre-filled "Millwoods East Veterinary Clinic"; reasons, weight,
  cost, follow-up and notes per cat) and the visit list with edit, delete, "Show deleted" and
  restore. No offline caching: if the server can't be reached it shows the error.
- Walking cats (`lib/pets/`): Shinx and Litten walk, sit and sleep on a 60 px strip above the
  tab bar, drawn over the content (`WithPets` in `home_screen.dart` pads the tabs by 60 px; the
  `PetLayer` box is 60 + 48 px so hops and hearts can rise over the content). Only a cat
  catches taps (painter `hitTest`); tapping one makes it face you, nod and show a pixel heart
  (drawn in code; Litten red, Shinx gold). An Identify result of Litten or Shinx makes that cat
  hop 3 times (`PetEvents.instance.celebrate`, called from `identify_screen.dart`). Events >
  Add event: the form covers the strip, so the cats react when it closes
  (`ReportEventScreen.onSent` collects what was sent; `_addEvent` in `events_screen.dart` calls
  `PetEvents.instance.afterReports`): litterbox = hop, cough = face you and nod (no heart), one
  reaction per cat (hop beats nod), first after 0.3 s, the next 0.8 s later. Delays run on the
  pet layer's own clock, not timers.
  `pet.dart` is the state machine (idle / walk left / walk right / sleep picked at random;
  hop, love and nod interrupt and return to the previous state, sleep wakes to idle).
  `pet_settings.dart` (loaded in `main.dart`): on/off and per-cat Auto / Normal / Shiny (Auto =
  1 in 20 shiny roll per launch), set from the paw button in the app bar
  (`pet_settings_sheet.dart`). Paused in the background; hidden when the phone's reduce-motion
  setting is on.
  Sprites: `assets/sprites/<cat>/<default|shiny>/` from PMD SpriteCollab (CC BY-NC 4.0, credit
  in `assets/sprites/CREDITS.md` and the settings sheet), copied once by
  `tool/fetch_sprites.py` (stdlib, needs git). Sheets: frames across, rows = directions (0
  faces you, 2 right, 6 left; Sleep has 1 row); durations in 1/60 s ticks; every frame is
  centred on the cat's position with feet 7 sprite px below centre. Drawn at 2x with
  `FilterQuality.none`.
- `api.dart`: `health()`, `identify(path, sendToDiscord:)` (`/identify` or `/litterbox`; the app now only
  uses `/identify`), `cough(cat, info, photoPath:, when:)`, `litterbox(cat, info, photoPath:, when:, location:)`,
  `litterboxClean(location, bagChanged:, info:, when:)`, `vetVisits`, `addVetVisits`, `editVetVisit`, `deleteVetVisit`,
  `restoreVetVisit`, `eventTypes`, `events`, `pictureUri`, `retrain()`.
- Tests: `flutter test` (`test/vet_screen_test.dart`, `test/events_screen_test.dart` and
  `test/health_screen_test.dart` drive the Vet, Events and Health tabs against a fake server;
  `test/pets/` covers the cats' state machine, sprite sheets and assets, taps, Identify hops,
  after-form reactions and settings; `events_screen_test.dart` checks the form's reactions
  are sent only once it closes).
- Build: `cd cat_id_app && flutter run --release` or `flutter build apk --release`.
  Release build has `isMinifyEnabled = false` / `isShrinkResources = false` in
  `android/app/build.gradle.kts` (R8 broke shared_preferences). minSdk 24.
- `setup.sh` / `patch_android.py`: one-time project creation and manifest patch
  (INTERNET, cleartext). See `SETUP.md`.

## Local testing on the Mac

Docker Desktop (used from the terminal). Copy `model.joblib` and `embeddings_cache.npz` from
the server first (a missing bind-mounted file becomes an empty directory and crashes the
server). `.env` with test values (`POSTGRES_PASSWORD`, `API_KEY=test`, empty Discord webhooks).
`docker compose up --build`, then `curl localhost:8000/health`. `data/Litten`, `data/Shinx`,
`data/neither` must exist for all label buttons to work.

## Other open ideas

- **Server test suite (planned separately, not part of the Events tab work).** Today the
  server has no saved tests: each phase was checked by hand (curl, psql) and those checks
  can't be re-run. Plan:
  - `tests/` with pytest, run inside the container: `docker compose exec cat-id pytest`.
    `requirements-dev.txt` holds pytest (installed for tests only; the production image stays
    the same).
  - `tests/conftest.py`: creates a separate, empty `catid_test` database on the `db` service,
    runs the Alembic migrations on it, points `db.py` at it, gives each test a clean state, and
    drives the app with FastAPI's `TestClient` (no running server needed). Never touches the
    real `catid` database, `data/` or `inbox/` (temporary folders instead).
  - `test_photos.py`: `/litterbox` and `/identify` create `picture` rows with the right
    source, reporter (`pi`, Ashley, `system` for missing/unknown) and `event_timestamp`; the
    JSON response is unchanged; bad key gives 401.
  - `test_labels.py`: Litten/Shinx with the default type makes a litterbox event only for
    `/litterbox` photos; `event_type` cough/none; neither/both make none; crops get their own
    rows; one event per cat per original photo (duplicates skipped); undo removes the event;
    archive/delete set the status; the old `POST /label` form still works.
  - `test_coughs.py`: `/cough` records an event (notes NULL when empty); unknown cat gives no
    event; no webhook still records it and returns null.
  - `test_vet.py`: add one / "both" (all or nothing), validation errors, edit, soft delete,
    `include_deleted`, restore, `active_vet_visit` view.
  - `test_db_down.py`: with the DB unreachable, requests still succeed, rows land in the failed
    file, and `replay_db_failed.py` restores them.
  - `label.py` / `sorter_core.py` without a database (must also pass on the Mac's Python 3.9).
  - Later: the Events tab's date logic (midnight in Edmonton, daylight-saving days) goes here
    too. Running tests automatically on every commit (e.g. GitHub Actions) is a separate step.

- Alerts: no litterbox visit from a cat in 24 h+, unusual frequency; weekly Discord summary
  (would read `picture`, so they don't depend on how fast photos are labeled).
- `evaluate.py` for held-out accuracy; auto-retrain after N new labels.
- The "neither" class is small (~42 photos vs ~900 Litten / ~700 Shinx); add more.
