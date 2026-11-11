import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'server_store.dart';
import 'who_am_i.dart';

/// One row of the server's vet_visit table, as GET /vet_visit returns it.
class VetVisit {
  VetVisit.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        cat = j['cat'] as String?,
        visitDate = DateTime.parse(j['visit_date'] as String),
        appointmentTime = j['appointment_time'] as String?,
        doctor = j['doctor'] as String?,
        clinic = (j['clinic'] as String?) ?? 'unknown',
        notes = j['notes'] as String?,
        reason = [for (final r in (j['reason'] as List? ?? const [])) r as String],
        weightKg = _toDouble(j['weight_kg']),
        cost = _toDouble(j['cost']),
        followUpDate = j['follow_up_date'] == null
            ? null
            : DateTime.parse(j['follow_up_date'] as String),
        reporter = j['reporter'] as String?,
        modifiedBy = j['modified_by'] as String?,
        deleted = j['deleted_on'] != null;

  final int id;

  /// Litten, Shinx, or null (a pickup not for one cat).
  final String? cat;
  final DateTime visitDate;

  /// "HH:MM" clock time in Edmonton, or null.
  final String? appointmentTime;
  final String? doctor;
  final String clinic;
  final String? notes;
  final List<String> reason;
  final double? weightKg;
  final double? cost;
  final DateTime? followUpDate;
  final String? reporter;
  final String? modifiedBy;
  final bool deleted;

  /// The server sends numbers; accept numeric text too, rather than failing on it.
  static double? _toDouble(dynamic v) =>
      v is num ? v.toDouble() : (v is String ? double.tryParse(v) : null);
}

/// An error with a message that is fine to show to the user.
class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// What /identify and /litterbox send back.
class IdentifyResult {
  IdentifyResult.fromJson(Map<String, dynamic> j)
      : cat = j['cat'] as String,
        bestGuess = j['best_guess'] as String,
        confidence = (j['confidence'] as num).toDouble(),
        savedAs = j['saved_as'] as String;

  /// Litten / Shinx / neither / "uncertain" (best guess was below the server's MIN_CONF).
  final String cat;
  final String bestGuess;
  final double confidence;
  final String savedAs;
}

/// Talks to one cat-id server. The /label page is shown in a web view instead (see
/// screens/label_screen.dart), so it is not here.
///
/// Every request that records something also sends the "who am I" name as `user`
/// (see who_am_i.dart); when it isn't set, nothing is sent and the server records "system".
class CatApi {
  CatApi(this.server, this.apiKey);

  final Server server;
  final String apiKey;

  String? get _user => WhoAmI.current;

  Uri _uri(String path, [Map<String, String>? query]) =>
      server.baseUri.replace(path: path, queryParameters: query);

  /// GET /health
  Future<Map<String, dynamic>> health() async {
    final r = await _guard(
        () => http.get(_uri('/health')).timeout(const Duration(seconds: 10)));
    return _json(r);
  }

  /// POST /identify, or POST /litterbox (same, plus a post to Discord).
  /// Either way the server also saves the photo in its inbox for later labeling.
  Future<IdentifyResult> identify(String photoPath,
      {required bool sendToDiscord}) async {
    final r = await _guard(() async {
      final req = http.MultipartRequest(
          'POST', _uri(sendToDiscord ? '/litterbox' : '/identify'))
        ..fields['key'] = apiKey
        ..files.add(await http.MultipartFile.fromPath('file', photoPath));
      final user = _user;
      if (user != null) req.fields['user'] = user;
      final streamed = await req.send().timeout(const Duration(seconds: 90));
      return http.Response.fromStream(streamed);
    });
    return IdentifyResult.fromJson(_json(r));
  }

  /// POST /cough: the server records a cough event and posts it to its Discord channel.
  /// [info] is optional; the server fills in "No additional info." when it is left out.
  Future<void> cough(String cat, String info) async {
    final r = await _guard(() async {
      final req = http.MultipartRequest('POST', _uri('/cough'))
        ..fields['cat'] = cat
        ..fields['key'] = apiKey;
      if (info.trim().isNotEmpty) req.fields['info'] = info.trim();
      final user = _user;
      if (user != null) req.fields['user'] = user;
      final streamed = await req.send().timeout(const Duration(seconds: 30));
      return http.Response.fromStream(streamed);
    });
    if (r.statusCode == 200) {
      dynamic body;
      try {
        body = jsonDecode(utf8.decode(r.bodyBytes));
      } catch (_) {
        body = null;
      }
      if (body is Map) return;
      // The server answers 200 with nothing when COUGH_DISCORD_WEBHOOK isn't set.
      throw ApiException(
          'The cough was saved, but the server has no cough Discord webhook set, so nothing was posted.');
    }
    _json(r); // not 200: throws the matching error
  }

  // ---------- vet visits (server: vet_api.py) ----------

  Map<String, String> get _jsonHeaders => {
        'Content-Type': 'application/json',
        if (apiKey.isNotEmpty) 'X-API-Key': apiKey,
      };

  Map<String, String> get _userQuery {
    final user = _user;
    return user == null ? {} : {'user': user};
  }

  /// GET /vet_visit: newest first; [includeDeleted] adds the soft-deleted ones.
  Future<List<VetVisit>> vetVisits({bool includeDeleted = false}) async {
    final r = await _guard(() => http
        .get(_uri('/vet_visit', includeDeleted ? {'include_deleted': 'true'} : null),
            headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return _visitList(_vetJson(r));
  }

  /// POST /vet_visit: one visit, or two (one per cat) saved together or not at all.
  Future<List<VetVisit>> addVetVisits(List<Map<String, dynamic>> visits) async {
    final r = await _guard(() => http
        .post(_uri('/vet_visit'),
            headers: _jsonHeaders, body: jsonEncode({'user': _user, 'visits': visits}))
        .timeout(const Duration(seconds: 15)));
    return _visitList(_vetJson(r));
  }

  /// PATCH /vet_visit/{id} with only the fields that changed.
  Future<VetVisit> editVetVisit(int id, Map<String, dynamic> changes) async {
    final r = await _guard(() => http
        .patch(_uri('/vet_visit/$id'),
            headers: _jsonHeaders, body: jsonEncode({...changes, 'user': _user}))
        .timeout(const Duration(seconds: 15)));
    return VetVisit.fromJson(_vetJson(r));
  }

  /// DELETE /vet_visit/{id}: a soft delete; [restoreVetVisit] undoes it.
  Future<VetVisit> deleteVetVisit(int id) async {
    final r = await _guard(() => http
        .delete(_uri('/vet_visit/$id', _userQuery), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return VetVisit.fromJson(_vetJson(r));
  }

  Future<VetVisit> restoreVetVisit(int id) async {
    final r = await _guard(() => http
        .post(_uri('/vet_visit/$id/restore', _userQuery), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return VetVisit.fromJson(_vetJson(r));
  }

  List<VetVisit> _visitList(Map<String, dynamic> body) => [
        for (final v in (body['visits'] as List? ?? const []))
          VetVisit.fromJson(v as Map<String, dynamic>)
      ];

  /// Like [_json], but the vet routes' errors are shown as the server words them.
  Map<String, dynamic> _vetJson(http.Response r) {
    dynamic body;
    try {
      body = jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      body = null;
    }
    if (r.statusCode == 401) {
      throw ApiException('Wrong API key for this server. Fix it under Servers.');
    }
    if (r.statusCode != 200) {
      var detail = body is Map ? body['detail'] : null;
      // FastAPI's validation errors are a list of {loc, msg}; show the first one.
      if (detail is List && detail.isNotEmpty && detail.first is Map) {
        final first = detail.first as Map;
        // loc is e.g. ["body", "visits", 0, "weight_kg"]: name only the field.
        final field = (first['loc'] as List?)
            ?.whereType<String>()
            .where((p) => p != 'body' && p != 'visits')
            .lastOrNull
            ?.replaceAll('_', ' ');
        detail = field == null ? first['msg'] : '$field: ${first['msg']}';
      }
      if (r.statusCode == 404 && detail == 'Not Found') {
        detail = "This server doesn't have vet visits yet. Update the server.";
      }
      throw ApiException(detail?.toString() ?? 'Server error (${r.statusCode})');
    }
    if (body is! Map<String, dynamic>) {
      throw ApiException('The server sent something unexpected.');
    }
    return body;
  }

  /// POST /api/retrain. Trains again on the server's data/ folder; takes a few minutes.
  Future<void> retrain() async {
    final r = await _guard(() =>
        http.post(_uri('/api/retrain')).timeout(const Duration(minutes: 20)));
    _json(r);
  }

  Future<http.Response> _guard(Future<http.Response> Function() call) async {
    try {
      return await call();
    } on TimeoutException {
      throw ApiException('${server.address} took too long to answer.');
    } on SocketException {
      throw _unreachable();
    } on http.ClientException {
      throw _unreachable();
    }
  }

  ApiException _unreachable() => ApiException(
      "Can't reach ${server.address}. Is the server running, and is this phone on the home Wi-Fi?");

  Map<String, dynamic> _json(http.Response r) {
    dynamic body;
    try {
      body = jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      body = null;
    }
    if (r.statusCode != 200) {
      final detail = body is Map ? (body['detail'] ?? body['error']) : null;
      throw ApiException(_explain(r.statusCode, detail?.toString()));
    }
    if (body is! Map<String, dynamic>) {
      throw ApiException('The server sent something unexpected.');
    }
    return body;
  }

  String _explain(int code, String? detail) {
    switch (code) {
      case 401:
        return 'Wrong API key for this server. Fix it under Servers.';
      case 503:
        return "The model isn't trained yet. Train it on the server first.";
      case 400:
        return "The server couldn't read that as an image.";
      case 409:
        return 'Retraining is already running.';
      default:
        final d = detail == null || detail.isEmpty ? '' : ': $detail';
        final shown = d.length > 300 ? '${d.substring(0, 300)}…' : d;
        return 'Server error ($code)$shown';
    }
  }
}
