"""App updates: the Android app's Update button (Health tab) and Settings page.

deploy.yml (via deploy_app_update.py) puts the deployed version's APK and release notes in
app_updates/<channel>/ on the server, replacing what was there:
    release/     tags like v1.4.4 (the Health tab's Update button)
    prerelease/  tags like v1.5.0-test (offered on the Settings page only, when turned on)
Each channel folder has cat-id.apk and info.json:
    {"version": "v1.4.4", "notes": "...", "sha256": "<hex>", "published_at": "<ISO>"}
The phones never talk to GitHub, so this works with a private repo.

GET /app_update                -> {"release": {version, notes, sha256, size, published_at}
                                   or null, "prerelease": ... or null}
                                  null = nothing deployed for that channel yet (or a file is
                                  missing or unreadable).
GET /app_update/{channel}/apk  -> the APK file (channel: release or prerelease); 404 if none.
Both check API_KEY in the X-API-Key header. No database.
"""
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse

API_KEY = os.environ.get("API_KEY", "")
APP_UPDATES = Path("app_updates")
CHANNELS = ("release", "prerelease")
APK_NAME = "cat-id.apk"
INFO_NAME = "info.json"

router = APIRouter()


def _check_key(key: str | None):
    if API_KEY and key != API_KEY:
        raise HTTPException(401, "bad key")


def channel_info(channel: str) -> dict | None:
    """The channel's info.json plus the APK's size, or None if either file is missing or
    the info can't be read."""
    folder = APP_UPDATES / channel
    apk, info = folder / APK_NAME, folder / INFO_NAME
    try:
        data = json.loads(info.read_text(encoding="utf-8"))
        size = apk.stat().st_size
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("version") or not data.get("sha256"):
        return None
    return {
        "version": str(data["version"]),
        "notes": str(data.get("notes") or ""),
        "sha256": str(data["sha256"]).lower(),
        "size": size,
        "published_at": data.get("published_at"),
    }


@router.get("/app_update")
def app_update(x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    return {c: channel_info(c) for c in CHANNELS}


@router.get("/app_update/{channel}/apk")
def app_update_apk(channel: Literal["release", "prerelease"],
                   x_api_key: str | None = Header(None)):
    _check_key(x_api_key)
    info = channel_info(channel)
    if info is None:
        raise HTTPException(404, f"No {channel} APK on this server")
    return FileResponse(APP_UPDATES / channel / APK_NAME,
                        media_type="application/vnd.android.package-archive",
                        filename=f"cat-id-{info['version']}.apk")
