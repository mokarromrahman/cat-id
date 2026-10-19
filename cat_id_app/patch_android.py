"""Android settings the app needs, applied to the project `flutter create` made.
Safe to run more than once. Run from the cat_id_app folder (setup.sh does this)."""
import pathlib
import re

manifest = pathlib.Path("android/app/src/main/AndroidManifest.xml")
s = manifest.read_text()

# 1. Internet access (a release build has none by default).
if "android.permission.INTERNET" not in s:
    s = s.replace(
        "<application",
        '<uses-permission android:name="android.permission.INTERNET"/>\n    <application',
        1,
    )

# 2. Android blocks plain http:// by default. The server is on your home network and
#    has no certificate, so allow it.
if "usesCleartextTraffic" not in s:
    s = s.replace("<application", '<application\n        android:usesCleartextTraffic="true"', 1)

manifest.write_text(s)

# 3. The secure-storage and web-view packages need Android 7 (API 24) or newer.
for name, pattern, new in (
    ("android/app/build.gradle.kts", r"minSdk\s*=\s*flutter\.minSdkVersion", "minSdk = 24"),
    ("android/app/build.gradle", r"minSdkVersion\s+flutter\.minSdkVersion", "minSdkVersion 24"),
):
    p = pathlib.Path(name)
    if p.exists():
        t = p.read_text()
        p.write_text(re.sub(pattern, new, t))

print("Android settings patched.")
