#!/usr/bin/env bash
# One-time setup for the Android app. Run it on your Mac from anywhere:
#     ./cat_id_app/setup.sh
# Safe to run again.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v flutter >/dev/null 2>&1; then
  echo "Flutter isn't installed (or isn't on your PATH). See SETUP.md, step 1."
  exit 1
fi

# `flutter create` makes the Android project around the lib/ folder that is already here.
# It would write its own sample lib/main.dart, so set ours aside and put it back after.
if [ ! -f pubspec.yaml ]; then
  keep="$(mktemp -d)"
  cp -R lib "$keep/lib"
  flutter create --platforms=android --project-name cat_id_app --org local.catid .
  rm -rf lib
  cp -R "$keep/lib" lib
  rm -rf "$keep"
fi
rm -f test/widget_test.dart   # the generated sample test refers to the sample app we replaced

# `pub add` picks the newest versions that work with your Flutter.
flutter pub add http image_picker shared_preferences flutter_secure_storage webview_flutter

python3 patch_android.py

echo
echo "Done. Next: connect your phone and run   flutter run --release"
echo "Or build an APK to send around:           flutter build apk --release"
