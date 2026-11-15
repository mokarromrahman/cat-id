import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Normal or shiny colours for one cat. [auto] uses this launch's random roll.
enum ShinyMode { auto, normal, shiny }

/// The walking-cats settings, saved on this phone (same pattern as WhoAmI).
class PetSettings extends ChangeNotifier {
  PetSettings._(this._prefs, this._enabled, this._modes, this._rolled);

  static const cats = ['Shinx', 'Litten'];

  /// In Auto, each cat has a 1 in [shinyOdds] chance of being shiny each time the app starts.
  static const shinyOdds = 20;

  static const _enabledKey = 'pets_enabled';
  static String _modeKey(String cat) => 'pets_shiny_$cat';

  static PetSettings? _instance;

  /// The app-wide settings; [load] must have run first (see main.dart).
  static PetSettings get instance => _instance!;

  /// The settings, or null if not loaded (e.g. in tests that don't need them).
  static PetSettings? get current => _instance;

  final SharedPreferences _prefs;
  bool _enabled;
  final Map<String, ShinyMode> _modes;
  final Map<String, bool> _rolled;

  static Future<PetSettings> load({Random? random}) async {
    final prefs = await SharedPreferences.getInstance();
    final r = random ?? Random();
    final modes = <String, ShinyMode>{};
    for (final cat in cats) {
      final saved = prefs.getString(_modeKey(cat));
      modes[cat] = ShinyMode.values
          .firstWhere((m) => m.name == saved, orElse: () => ShinyMode.auto);
    }
    final rolled = {for (final cat in cats) cat: r.nextInt(shinyOdds) == 0};
    return _instance = PetSettings._(prefs, prefs.getBool(_enabledKey) ?? true, modes, rolled);
  }

  /// Whether the cats are shown at all.
  bool get enabled => _enabled;

  Future<void> setEnabled(bool value) async {
    _enabled = value;
    notifyListeners();
    await _prefs.setBool(_enabledKey, value);
  }

  ShinyMode modeFor(String cat) => _modes[cat] ?? ShinyMode.auto;

  Future<void> setMode(String cat, ShinyMode mode) async {
    _modes[cat] = mode;
    notifyListeners();
    await _prefs.setString(_modeKey(cat), mode.name);
  }

  /// Whether this launch's roll came up shiny for [cat] (what Auto shows).
  bool rolledShiny(String cat) => _rolled[cat] ?? false;

  /// Whether [cat] is drawn shiny right now.
  bool isShiny(String cat) => switch (modeFor(cat)) {
        ShinyMode.shiny => true,
        ShinyMode.normal => false,
        ShinyMode.auto => rolledShiny(cat),
      };
}
