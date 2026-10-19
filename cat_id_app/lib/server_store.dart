import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// One cat-id server you can connect to.
class Server {
  Server({required this.id, required this.name, required this.address});

  final String id;

  /// What you call it, e.g. "Home server". Optional.
  final String name;

  /// host:port, e.g. 192.168.1.116:8000
  final String address;

  String get label => name.isEmpty ? address : name;

  /// The app talks plain HTTP: the server is only reachable on the home network.
  Uri get baseUri => Uri.parse('http://$address');

  Map<String, dynamic> toJson() => {'id': id, 'name': name, 'address': address};

  factory Server.fromJson(Map<String, dynamic> j) => Server(
        id: j['id'] as String,
        name: (j['name'] as String?) ?? '',
        address: j['address'] as String,
      );
}

/// "192.168.1.116" or "http://192.168.1.116:8000/" -> "192.168.1.116:8000".
/// The port defaults to 8000. Returns null if it doesn't look like an address.
String? normalizeAddress(String input) {
  var s = input.trim();
  s = s.replaceFirst(RegExp(r'^https?://', caseSensitive: false), '');
  s = s.replaceFirst(RegExp(r'/+$'), '');
  final m = RegExp(r'^([A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?)(?::(\d{1,5}))?$')
      .firstMatch(s);
  if (m == null) return null;
  final port = m.group(2) == null ? 8000 : int.parse(m.group(2)!);
  if (port < 1 || port > 65535) return null;
  return '${m.group(1)}:$port';
}

/// Remembers up to [maxServers] servers.
///
/// - The server list (names + addresses) is in SharedPreferences. It is not secret.
/// - Each server's API key is in flutter_secure_storage, which encrypts it with a key
///   held in the Android Keystore. It is never written to the list above.
class ServerStore extends ChangeNotifier {
  ServerStore._(this._prefs, this._secure, this._servers, this._selectedId);

  static const int maxServers = 5;
  static const _serversKey = 'servers';
  static const _selectedKey = 'selected_server';

  final SharedPreferences _prefs;
  final FlutterSecureStorage _secure;
  List<Server> _servers;
  String? _selectedId;

  static Future<ServerStore> load() async {
    final prefs = await SharedPreferences.getInstance();
    var servers = <Server>[];
    try {
      final raw = prefs.getString(_serversKey);
      if (raw != null) {
        servers = (jsonDecode(raw) as List)
            .map((e) => Server.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {
      servers = <Server>[]; // unreadable data: start empty rather than crash
    }
    var selected = prefs.getString(_selectedKey);
    if (!servers.any((s) => s.id == selected)) {
      selected = servers.isEmpty ? null : servers.first.id;
    }
    return ServerStore._(prefs, const FlutterSecureStorage(), servers, selected);
  }

  List<Server> get servers => List.unmodifiable(_servers);
  bool get isFull => _servers.length >= maxServers;

  Server? get selected {
    for (final s in _servers) {
      if (s.id == _selectedId) return s;
    }
    return null;
  }

  String _keyName(String id) => 'apikey_$id';

  /// The saved API key for a server ('' if none).
  Future<String> keyFor(String id) async {
    try {
      return (await _secure.read(key: _keyName(id))) ?? '';
    } catch (_) {
      return '';
    }
  }

  Future<void> _writeKey(String id, String apiKey) async {
    final k = apiKey.trim();
    if (k.isEmpty) {
      await _secure.delete(key: _keyName(id));
    } else {
      await _secure.write(key: _keyName(id), value: k);
    }
  }

  Future<void> _save() async {
    await _prefs.setString(
        _serversKey, jsonEncode(_servers.map((s) => s.toJson()).toList()));
    final sel = _selectedId;
    if (sel == null) {
      await _prefs.remove(_selectedKey);
    } else {
      await _prefs.setString(_selectedKey, sel);
    }
  }

  /// Returns an error message, or null on success.
  Future<String?> add({
    required String name,
    required String address,
    required String apiKey,
  }) async {
    if (isFull) {
      return 'You can save up to $maxServers servers. Remove one first.';
    }
    final addr = normalizeAddress(address);
    if (addr == null) {
      return "That doesn't look like an address. Try 192.168.1.116 or 192.168.1.116:8000.";
    }
    if (_servers.any((s) => s.address == addr)) {
      return 'That address is already saved.';
    }
    try {
      final s = Server(
        id: DateTime.now().microsecondsSinceEpoch.toString(),
        name: name.trim(),
        address: addr,
      );
      await _writeKey(s.id, apiKey);
      _servers = [..._servers, s];
      _selectedId ??= s.id;
      await _save();
      notifyListeners();
      return null;
    } catch (e) {
      return 'Could not save: $e';
    }
  }

  /// Returns an error message, or null on success. A blank [apiKey] clears the saved key.
  Future<String?> update(
    String id, {
    required String name,
    required String address,
    required String apiKey,
  }) async {
    final addr = normalizeAddress(address);
    if (addr == null) {
      return "That doesn't look like an address. Try 192.168.1.116 or 192.168.1.116:8000.";
    }
    if (_servers.any((s) => s.id != id && s.address == addr)) {
      return 'That address is already saved.';
    }
    try {
      await _writeKey(id, apiKey);
      _servers = [
        for (final s in _servers)
          if (s.id == id) Server(id: id, name: name.trim(), address: addr) else s
      ];
      await _save();
      notifyListeners();
      return null;
    } catch (e) {
      return 'Could not save: $e';
    }
  }

  Future<void> select(String id) async {
    if (!_servers.any((s) => s.id == id)) return;
    _selectedId = id;
    await _save();
    notifyListeners();
  }

  /// Removes the server and its saved API key.
  Future<void> remove(String id) async {
    try {
      await _secure.delete(key: _keyName(id));
    } catch (_) {}
    _servers = _servers.where((s) => s.id != id).toList();
    if (_selectedId == id) {
      _selectedId = _servers.isEmpty ? null : _servers.first.id;
    }
    await _save();
    notifyListeners();
  }
}
