import 'dart:io';

import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Android often closes the app while the camera is open (to free memory). The photo
/// then comes back to a fresh start of the app, and image_picker keeps it for us to
/// collect with retrieveLostData(). It only saves it after Android has scanned the new
/// file, a moment after the app restarts, so asking once at start-up can miss it.
///
/// We note when the camera is opened, and if the app starts with that note still
/// there, keep asking for a few seconds.
class CameraRecovery {
  static const _pendingKey = 'camera_pending';

  static Future<void> markOpened() async {
    if (Platform.isAndroid) {
      // Throw away anything left from an earlier photo we never collected, so a
      // recovery after this one can't hand back that old photo instead.
      try {
        await ImagePicker().retrieveLostData();
      } catch (_) {}
    }
    await (await SharedPreferences.getInstance()).setBool(_pendingKey, true);
  }

  static Future<void> markReturned() async =>
      (await SharedPreferences.getInstance()).remove(_pendingKey);

  /// The photo (or camera error) from before Android closed the app, or null.
  static Future<LostDataResponse?> recover() async {
    if (!Platform.isAndroid) return null;
    final prefs = await SharedPreferences.getInstance();
    if (prefs.getBool(_pendingKey) != true) return null;
    try {
      for (var i = 0; i < 30; i++) {
        try {
          final lost = await ImagePicker().retrieveLostData();
          if (!lost.isEmpty) return lost;
        } catch (_) {
          // Not attached to the screen yet; try again.
        }
        await Future<void>.delayed(const Duration(milliseconds: 300));
      }
      return null;
    } finally {
      await prefs.remove(_pendingKey);
    }
  }
}
