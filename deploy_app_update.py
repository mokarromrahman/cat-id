"""Puts a release's APK and notes on the server, for the app's Update button.

Run by deploy.yml on the home server (self-hosted runner), before the container restarts:
    GH_TOKEN=... python3 deploy_app_update.py <tag> <owner/repo> <deploy dir>
Downloads cat-id-<tag>.apk and the release notes from that tag's GitHub Release and writes
    <deploy dir>/app_updates/<channel>/cat-id.apk
    <deploy dir>/app_updates/<channel>/info.json   {version, notes, sha256, published_at}
replacing the channel's previous files (only the newest of each channel is kept). Channel:
"prerelease" for tags with a dash (v1.5.0-test, same rule as release.yml), else "release".
GH_TOKEN is the workflow's own GITHUB_TOKEN, which can read a private repo; without it this
only works for a public repo. The server serves the files (app_update_api.py).

Stdlib only, Python 3.8+ (whatever the server's python3 is). Exits non-zero, with a
GitHub Actions ::error:: line, if the release or its APK is missing, so the deploy stops.
"""
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def request(url, accept):
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cat-id-deploy",
    })
    token = os.environ.get("GH_TOKEN")
    if token:
        # Unredirected: the asset download redirects to a storage host that must not get
        # the token (it refuses requests that carry two kinds of auth).
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=60)


def clean_notes(body):
    """GitHub's generated notes, without the Release's boilerplate lines, the "New
    Contributors" section, the "Full Changelog" link and each line's "by @someone in <PR
    link>" tail; headings lose their #."""
    lines = []
    skipping = False  # inside the "New Contributors" section
    for line in (body or "").splitlines():
        line = line.rstrip()
        if line.startswith("#"):
            skipping = line.lstrip("# ").startswith("New Contributors")
        if skipping or line.startswith(("Server image:", "Android APK:", "**Full Changelog**")):
            continue
        line = re.sub(r" by @\S+ in https://\S+$", "", line)
        line = re.sub(r"^#+\s*", "", line)
        if not line and (not lines or not lines[-1]):
            continue  # no leading or double blank lines
        lines.append(line)
    return "\n".join(lines).strip()


def main():
    if len(sys.argv) != 4:
        fail("usage: deploy_app_update.py <tag> <owner/repo> <deploy dir>")
    tag, repo, deploy_dir = sys.argv[1:]
    channel = "prerelease" if "-" in tag else "release"
    apk_name = f"cat-id-{tag}.apk"

    try:
        with request(f"{API}/repos/{repo}/releases/tags/{tag}", "application/vnd.github+json") as r:
            release = json.load(r)
    except urllib.error.HTTPError as e:
        fail(f"Couldn't read the GitHub Release for {tag} (HTTP {e.code})")
    asset = next((a for a in release.get("assets", []) if a.get("name") == apk_name), None)
    if asset is None:
        fail(f"The {tag} Release has no {apk_name}. Run 'Build APK' for {tag}, then deploy again.")

    folder = Path(deploy_dir) / "app_updates" / channel
    try:
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / "cat-id.apk.part"
        sha = hashlib.sha256()
        with request(asset["url"], "application/octet-stream") as r, open(part, "wb") as out:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                sha.update(chunk)
                out.write(chunk)
        if part.stat().st_size != asset.get("size", part.stat().st_size):
            fail(f"{apk_name} download was cut short")
        info = {
            "version": tag,
            "notes": clean_notes(release.get("body")),
            "sha256": sha.hexdigest(),
            "published_at": release.get("published_at"),
        }
        info_part = folder / "info.json.part"
        info_part.write_text(json.dumps(info, indent=2), encoding="utf-8")
        # APK first: if this stops in between, the old info's checksum won't match the new
        # APK and the app refuses to install it (it doesn't install a wrong file).
        os.replace(part, folder / "cat-id.apk")
        os.replace(info_part, folder / "info.json")
    except urllib.error.HTTPError as e:
        fail(f"Couldn't download {apk_name} (HTTP {e.code})")
    except PermissionError as e:
        fail(f"Can't write {folder} ({e}). If Docker created app_updates/ as root, "
             f"run: sudo chown -R $USER {Path(deploy_dir) / 'app_updates'}")
    print(f"{apk_name} -> {folder} ({channel}, sha256 {info['sha256'][:12]}...)")


if __name__ == "__main__":
    main()
