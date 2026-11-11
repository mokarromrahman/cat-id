import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Who is using this phone ("who am I"). Sent as `user` with every request, so the server
/// records who reported or changed something. One setting per phone, for every server.
///
/// The names must match the server's app_user rows (seeded: Ashley, Mac). Not set means
/// nothing is sent and the server records its "system" user. There is no password: this
/// says who you are, it doesn't prove it.
class WhoAmI extends ChangeNotifier {
  WhoAmI._(this._prefs, this._name);

  static const List<String> people = ['Ashley', 'Mac'];
  static const _key = 'who_am_i';

  static WhoAmI? _instance;

  /// The app-wide setting; [load] must have run first (see main.dart).
  static WhoAmI get instance => _instance!;

  /// The current name, or null if not set (or not loaded, e.g. in tests).
  static String? get current => _instance?._name;

  final SharedPreferences _prefs;
  String? _name;

  String? get name => _name;

  static Future<WhoAmI> load() async {
    final prefs = await SharedPreferences.getInstance();
    var name = prefs.getString(_key);
    if (name != null && !people.contains(name)) name = null;
    return _instance = WhoAmI._(prefs, name);
  }

  Future<void> set(String? name) async {
    if (name != null && !people.contains(name)) return;
    _name = name;
    if (name == null) {
      await _prefs.remove(_key);
    } else {
      await _prefs.setString(_key, name);
    }
    notifyListeners();
  }
}
