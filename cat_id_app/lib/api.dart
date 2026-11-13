import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'server_store.dart';
import 'who_am_i.dart';

String _two(int n) => n.toString().padLeft(2, '0');

/// "2026-11-13": a day as the server's date parameters expect it.
String isoDay(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';

/// One row of the server's event_type table: `type` is the code, `name` the display label.
class EventType {
  EventType.fromJson(Map<String, dynamic> j)
      : type = j['type'] as String,
        name = j['name'] as String;

  final String type;
  final String name;
}

/// The photo an event came from (litterbox visits, crops).
class EventPicture {
  EventPicture.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        source = j['source'] as String?,
        bestGuess = j['best_guess'] as String?,
        confidence = (j['confidence'] as num?)?.toDouble(),
        labeledBy = j['labeled_by'] as String?,
        hasImage = j['has_image'] as bool? ?? false;

  final int id;
  final String? source;

  /// The model's guess; null for a crop (the model only saw the whole photo).
  final String? bestGuess;
  final double? confidence;
  final String? labeledBy;

  /// False when the photo was deleted on the label page.
  final bool hasImage;
}

/// One event from GET /events.
class CatEvent {
  CatEvent.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        type = j['type'] as String,
        typeName = j['type_name'] as String,
        cat = j['cat'] as String,
        when = DateTime.parse(j['event_timestamp'] as String).toLocal(),
        reporter = j['reporter'] as String?,
        notes = j['notes'] as String?,
        picture = j['picture'] == null
            ? null
            : EventPicture.fromJson(j['picture'] as Map<String, dynamic>);

  final int id;
  final String type;
  final String typeName;
  final String cat;

  /// When it happened, in the phone's time zone (Edmonton).
  final DateTime when;
  final String? reporter;
  final String? notes;
  final EventPicture? picture;
}

/// Event counts for the chart: one series per event type and cat, one count per bucket.
class EventChart {
  EventChart.fromJson(Map<String, dynamic> j)
      : kind = j['kind'] as String,
        bucket = j['bucket'] as String,
        buckets = [for (final b in j['buckets'] as List) b as String],
        series = {
          for (final t in (j['series'] as Map<String, dynamic>).entries)
            t.key: {
              for (final c in (t.value as Map<String, dynamic>).entries)
                c.key: [for (final n in c.value as List) (n as num).toInt()]
            }
        };

  /// "bar" or "line".
  final String kind;

  /// "hour", "day" or "week".
  final String bucket;

  /// Each bucket's start in Edmonton time: "2026-11-13" (day, week) or
  /// "2026-11-13T08:00-07:00" (hour).
  final List<String> buckets;

  /// type -> cat -> counts, one per bucket.
  final Map<String, Map<String, List<int>>> series;
}

/// One page of GET /events. [totals] and [chart] come only with the first page.
class EventsPage {
  EventsPage.fromJson(Map<String, dynamic> j)
      : events = [
          for (final e in (j['events'] as List? ?? const []))
            CatEvent.fromJson(e as Map<String, dynamic>)
        ],
        next = j['next'] as String?,
        total = (j['totals'] as Map?)?['all'] as int?,
        byCat = _counts((j['totals'] as Map?)?['by_cat']),
        byType = {
          for (final t in (((j['totals'] as Map?)?['by_type'] as Map?) ?? const {}).entries)
            t.key as String: _counts(t.value)
        },
        chart = j['chart'] == null ? null : EventChart.fromJson(j['chart'] as Map<String, dynamic>);

  static Map<String, int> _counts(dynamic m) => {
        for (final e in ((m as Map?) ?? const {}).entries) e.key as String: (e.value as num).toInt()
      };

  final List<CatEvent> events;
  final String? next;
  final int? total;
  final Map<String, int> byCat;
  final Map<String, Map<String, int>> byType;
  final EventChart? chart;
}

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
    final body = _detailBody(r, 'vet visits');
    if (body is! Map<String, dynamic>) {
      throw ApiException('The server sent something unexpected.');
    }
    return body;
  }

  /// The decoded JSON body of a vet or events route, or an [ApiException] worded from the
  /// server's `detail`. [feature] names what an older server lacks when the route is missing.
  dynamic _detailBody(http.Response r, String feature) {
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
        detail = "This server doesn't have $feature yet. Update the server.";
      }
      throw ApiException(detail?.toString() ?? 'Server error (${r.statusCode})');
    }
    return body;
  }

  // ---------- events (server: events_api.py) ----------

  /// GET /event_types: the Event filter's choices and the chart pages, in order.
  Future<List<EventType>> eventTypes() async {
    final r = await _guard(() => http
        .get(_uri('/event_types'), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    final body = _detailBody(r, 'events');
    if (body is! List) throw ApiException('The server sent something unexpected.');
    return [for (final t in body) EventType.fromJson(t as Map<String, dynamic>)];
  }

  /// GET /events. [cat] and [type] null mean every cat / every type; [from] and [to] are
  /// days (the server reads them as Edmonton days, both included). [before] is the
  /// previous page's [EventsPage.next], for Load more.
  Future<EventsPage> events({
    String? cat,
    String? type,
    required DateTime from,
    required DateTime to,
    String? before,
    int limit = 50,
  }) async {
    final query = {
      'cat': ?cat,
      'type': ?type,
      'from': isoDay(from),
      'to': isoDay(to),
      'limit': '$limit',
      'before': ?before,
    };
    final r = await _guard(() => http
        .get(_uri('/events', query), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 20)));
    final body = _detailBody(r, 'events');
    if (body is! Map<String, dynamic>) {
      throw ApiException('The server sent something unexpected.');
    }
    return EventsPage.fromJson(body);
  }

  /// Where an event's photo is served (GET /picture/{id}/image); load it with [imageHeaders].
  Uri pictureUri(int pictureId) => _uri('/picture/$pictureId/image');

  Map<String, String> get imageHeaders => {if (apiKey.isNotEmpty) 'X-API-Key': apiKey};

  /// Button art from the server's img_src/ (the label page's pictures).
  Uri assetUri(String file) => _uri('/asset/$file');

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
