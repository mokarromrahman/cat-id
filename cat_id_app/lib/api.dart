import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'server_store.dart';
import 'who_am_i.dart';

String _two(int n) => n.toString().padLeft(2, '0');

/// "2026-11-13": a day as the server's date parameters expect it.
String isoDay(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';

/// A litterbox location (the server's location table): `name` is the code sent to the
/// server, `label` the display name.
class LitterboxLocation {
  const LitterboxLocation(this.name, this.label);
  final String name;
  final String label;
}

/// The seeded locations, in the server's order. Basement is the default for a visit.
const kLitterboxLocations = [
  LitterboxLocation('basement', 'Basement'),
  LitterboxLocation('master_bathroom', 'Master Bathroom'),
];

/// One location's row of GET /health's `litterboxes`: when that box was last cleaned (and
/// by whom, null = not known or an older server) and when its bag was last changed (null =
/// never recorded).
class LitterboxStatus {
  LitterboxStatus.fromJson(Map<String, dynamic> j)
      : location = j['location'] as String,
        name = (j['name'] as String?) ?? j['location'] as String,
        lastCleaned = _time(j['last_cleaned']),
        lastCleanedBy = j['last_cleaned_by'] as String?,
        bagLastChanged = _time(j['bag_last_changed']);

  static DateTime? _time(dynamic v) => v is String ? DateTime.parse(v).toLocal() : null;

  final String location;
  final String name;
  final DateTime? lastCleaned;
  final String? lastCleanedBy;
  final DateTime? bagLastChanged;
}

/// A household chore (the server's chore table) and its status: when it was last done
/// and by whom, and whether it's overdue (more than [warningThresholdDays] since then, or
/// never done; never overdue without a threshold). GET /chores and GET /health's `chores`.
class Chore {
  Chore.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        name = j['name'] as String,
        label = (j['label_name'] as String?) ?? j['name'] as String,
        warningThresholdDays = (j['warning_threshold_days'] as num?)?.toInt(),
        active = j['active'] as bool? ?? true,
        lastDone = _time(j['last_done']),
        lastDoneBy = [for (final n in (j['last_done_by'] as List? ?? const [])) n as String],
        dueAt = _time(j['due_at']),
        overdue = j['overdue'] as bool? ?? false,
        request = j['request'] is Map<String, dynamic>
            ? ChoreRequest.fromJson(j['request'] as Map<String, dynamic>)
            : null,
        inProgress = j['in_progress'] is Map<String, dynamic>
            ? ChoreStart.fromJson(j['in_progress'] as Map<String, dynamic>)
            : null;

  static DateTime? _time(dynamic v) => v is String ? DateTime.parse(v).toLocal() : null;

  final int id;

  /// The code sent to the server (vacuum, cat_food_pickup); never changes.
  final String name;

  /// The display name (Vacuum, Cat Food Pickup).
  final String label;

  /// Null = no reminder.
  final int? warningThresholdDays;

  /// False = hidden from the list.
  final bool active;
  final DateTime? lastDone;
  final List<String> lastDoneBy;

  /// When it becomes overdue (null without a threshold, or if never done).
  final DateTime? dueAt;

  /// Past its threshold, or past its open request's "needed by" day.
  final bool overdue;

  /// The open "this needs doing" request, or null (also null from older servers).
  final ChoreRequest? request;

  /// Someone is doing it right now (Start), or null (also null from older servers).
  final ChoreStart? inProgress;
}

/// Someone started a chore (the server's chore_start table). In progress until the chore's
/// next Done or until someone taps Stop; at most one in progress per chore.
class ChoreStart {
  ChoreStart.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        chore = j['chore'] as String,
        choreLabel = (j['chore_label'] as String?) ?? j['chore'] as String,
        startedOn = DateTime.parse(j['started_on'] as String).toLocal(),
        doers = [for (final n in (j['doers'] as List? ?? const [])) n as String],
        reporter = j['reporter'] as String?,
        notes = j['notes'] as String?,
        status = (j['status'] as String?) ?? 'in_progress',
        endedOn = Chore._time(j['ended_on']),
        endedBy = j['ended_by'] as String?;

  final int id;
  final String chore;
  final String choreLabel;
  final DateTime startedOn;

  /// Who is doing it; empty = not recorded.
  final List<String> doers;
  final String? reporter;
  final String? notes;

  /// in_progress, done or stopped.
  final String status;
  final DateTime? endedOn;
  final String? endedBy;
}

/// Someone marked a chore as needing to be done (the server's chore_request table). Open
/// until the chore's next Done, or until it's cancelled; at most one open per chore.
class ChoreRequest {
  ChoreRequest.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        chore = j['chore'] as String,
        choreLabel = (j['chore_label'] as String?) ?? j['chore'] as String,
        requestedOn = DateTime.parse(j['requested_on'] as String).toLocal(),
        requestedBy = j['requested_by'] as String?,
        notes = j['notes'] as String?,
        quantity = (j['quantity'] as num?)?.toDouble(),
        unit = j['unit'] as String?,
        neededBy = j['needed_by'] is String ? DateTime.parse(j['needed_by'] as String) : null,
        status = (j['status'] as String?) ?? 'open',
        doneOn = Chore._time(j['done_on']),
        doneBy = [for (final n in (j['done_by'] as List? ?? const [])) n as String],
        cancelledOn = Chore._time(j['cancelled_on']),
        closedBy = j['closed_by'] as String?,
        overdue = j['overdue'] as bool? ?? false;

  final int id;
  final String chore;
  final String choreLabel;
  final DateTime requestedOn;
  final String? requestedBy;
  final String? notes;
  final double? quantity;
  final String? unit;

  /// A day (midnight, local); the chore is overdue once it's over.
  final DateTime? neededBy;

  /// open, done or cancelled.
  final String status;
  final DateTime? doneOn;
  final List<String> doneBy;
  final DateTime? cancelledOn;

  /// Who recorded the Done, or who cancelled it.
  final String? closedBy;
  final bool overdue;

  bool get isOpen => status == 'open';

  /// "2", "1.5" (null without a quantity).
  String? get quantityNumber {
    final q = quantity;
    if (q == null) return null;
    return q == q.roundToDouble() ? q.toInt().toString() : '$q';
  }

  /// "2 bags", "1.5", "bags", or null.
  String? get quantityText {
    final parts = [?quantityNumber, ?unit];
    return parts.isEmpty ? null : parts.join(' ');
  }
}

/// One page of GET /chore_requests; [next] is for Load more.
class ChoreRequestsPage {
  ChoreRequestsPage.fromJson(Map<String, dynamic> j)
      : requests = [
          for (final r in (j['requests'] as List? ?? const []))
            ChoreRequest.fromJson(r as Map<String, dynamic>)
        ],
        next = j['next'] as String?;

  final List<ChoreRequest> requests;
  final String? next;
}

/// GET /chores: the chores, and the people who can be picked as having done one.
class ChoreList {
  ChoreList.fromJson(Map<String, dynamic> j)
      : chores = [
          for (final c in (j['chores'] as List? ?? const []))
            Chore.fromJson(c as Map<String, dynamic>)
        ],
        people = [for (final p in (j['people'] as List? ?? const [])) p as String];

  final List<Chore> chores;
  final List<String> people;
}

/// One time a chore was done (the server's chore_event table).
class ChoreEvent {
  ChoreEvent.fromJson(Map<String, dynamic> j)
      : id = j['id'] as int,
        chore = j['chore'] as String,
        choreLabel = (j['chore_label'] as String?) ?? j['chore'] as String,
        when = DateTime.parse(j['event_timestamp'] as String).toLocal(),
        doneBy = [for (final n in (j['done_by'] as List? ?? const [])) n as String],
        reporter = j['reporter'] as String?,
        notes = j['notes'] as String?,
        startedOn = Chore._time(j['started_on']),
        took = j['took_seconds'] is num
            ? Duration(seconds: (j['took_seconds'] as num).toInt())
            : null,
        modifiedBy = j['modified_by'] as String?,
        deleted = j['deleted_on'] != null;

  final int id;

  /// The chore's code and display name.
  final String chore;
  final String choreLabel;
  final DateTime when;

  /// Who did it; empty = not recorded.
  final List<String> doneBy;
  final String? reporter;
  final String? notes;

  /// When it was started (null = not known), and how long it took from then.
  final DateTime? startedOn;
  final Duration? took;
  final String? modifiedBy;
  final bool deleted;
}

/// One page of GET /chore_events; [next] is for Load more.
class ChoreEventsPage {
  ChoreEventsPage.fromJson(Map<String, dynamic> j)
      : events = [
          for (final e in (j['events'] as List? ?? const []))
            ChoreEvent.fromJson(e as Map<String, dynamic>)
        ],
        next = j['next'] as String?;

  final List<ChoreEvent> events;
  final String? next;
}

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
        location = (j['location'] as Map?)?['label_name'] as String?,
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

  /// Which litterbox (display name), for visits where it's known.
  final String? location;
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
/// One channel's entry of GET /app_update: the APK the server has for the app's Update
/// button (release) or the Settings page's prerelease offer.
class AppUpdateInfo {
  AppUpdateInfo.fromJson(this.channel, Map<String, dynamic> j)
      : version = j['version'] as String,
        notes = (j['notes'] as String?) ?? '',
        sha256 = j['sha256'] as String,
        size = (j['size'] as num).toInt();

  /// "release" or "prerelease": part of the download address.
  final String channel;

  /// The release tag, e.g. v1.4.4.
  final String version;

  /// The release notes (plain text, may be empty).
  final String notes;

  /// The APK's SHA-256 (hex); checked before installing.
  final String sha256;

  /// The APK's size in bytes.
  final int size;
}

/// GET /app_update: what the server has to offer, per channel (null = nothing).
class AppUpdates {
  AppUpdates.fromJson(Map<String, dynamic> j)
      : release = _channel('release', j['release']),
        prerelease = _channel('prerelease', j['prerelease']);

  static AppUpdateInfo? _channel(String name, dynamic v) =>
      v is Map<String, dynamic> ? AppUpdateInfo.fromJson(name, v) : null;

  final AppUpdateInfo? release;
  final AppUpdateInfo? prerelease;
}

class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// Thrown by [CatApi.downloadApk] when the person cancels the download.
class DownloadCancelled implements Exception {
  const DownloadCancelled();
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
  /// [photoPath] is optional: the server keeps the photo (inbox, for labeling), links it to
  /// the event and attaches it to the Discord post. [when] is when it happened (sent as
  /// `event_time` in UTC; the server uses it as the event's time); null means now.
  Future<void> cough(String cat, String info, {String? photoPath, DateTime? when}) =>
      _report('/cough', cat, info, photoPath, when, 'cough');

  /// POST /litterbox with `cat`: a litterbox visit reported by hand. Same as [cough]: the
  /// server records the event now and posts it to the litterbox Discord channel.
  /// [location] is a [LitterboxLocation.name]; null means not known.
  Future<void> litterbox(String cat, String info,
          {String? photoPath, DateTime? when, String? location}) =>
      _report('/litterbox', cat, info, photoPath, when, 'litterbox',
          extra: {'location': ?location});

  Future<void> _report(String path, String cat, String info, String? photoPath,
      DateTime? when, String what, {Map<String, String> extra = const {}}) async {
    final r = await _guard(() async {
      final req = http.MultipartRequest('POST', _uri(path))
        ..fields['cat'] = cat
        ..fields['key'] = apiKey
        ..fields.addAll(extra);
      if (info.trim().isNotEmpty) req.fields['info'] = info.trim();
      req.fields['event_time'] = (when ?? DateTime.now()).toUtc().toIso8601String();
      final user = _user;
      if (user != null) req.fields['user'] = user;
      if (photoPath != null) {
        req.files.add(await http.MultipartFile.fromPath('file', photoPath));
      }
      // A photo goes through the model on the server, like identify().
      final streamed = await req
          .send()
          .timeout(Duration(seconds: photoPath == null ? 30 : 90));
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
      // The server answers 200 with nothing when that Discord webhook isn't set.
      throw ApiException(
          'The $what was saved, but the server has no $what Discord webhook set, so nothing was posted.');
    }
    _json(r); // not 200: throws the matching error
  }

  /// POST /litterbox_clean: a litterbox was cleaned. [location] is a
  /// [LitterboxLocation.name]; [when] as in [cough]; [cleanedBy] is who did it (one of
  /// [ChoreList.people]; null = not sent, the server then uses `user`). Nothing goes to
  /// Discord.
  Future<void> litterboxClean(String location,
      {required bool bagChanged, String info = '', DateTime? when, String? cleanedBy}) async {
    final r = await _guard(() async {
      final req = http.MultipartRequest('POST', _uri('/litterbox_clean'))
        ..fields['location'] = location
        ..fields['bag_changed'] = bagChanged ? 'true' : 'false'
        ..fields['key'] = apiKey
        ..fields['event_time'] = (when ?? DateTime.now()).toUtc().toIso8601String();
      if (info.trim().isNotEmpty) req.fields['info'] = info.trim();
      final user = _user;
      if (user != null) req.fields['user'] = user;
      if (cleanedBy != null) req.fields['cleaned_by'] = cleanedBy;
      final streamed = await req.send().timeout(const Duration(seconds: 30));
      return http.Response.fromStream(streamed);
    });
    _detailBody(r, 'litterbox cleaning'); // throws on anything but 200
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

  // ---------- chores (server: chores_api.py) ----------

  Map<String, dynamic> _choreJson(http.Response r) {
    final body = _detailBody(r, 'chores');
    if (body is! Map<String, dynamic>) {
      throw ApiException('The server sent something unexpected.');
    }
    return body;
  }

  /// GET /chores; [includeInactive] adds the hidden chores.
  Future<ChoreList> chores({bool includeInactive = false}) async {
    final r = await _guard(() => http
        .get(_uri('/chores', includeInactive ? {'include_inactive': 'true'} : null),
            headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return ChoreList.fromJson(_choreJson(r));
  }

  /// POST /chores: a new chore. [thresholdDays] null = no reminder.
  Future<Chore> addChore(String label, int? thresholdDays) async {
    final r = await _guard(() => http
        .post(_uri('/chores'),
            headers: _jsonHeaders,
            body: jsonEncode(
                {'user': _user, 'label_name': label, 'warning_threshold_days': thresholdDays}))
        .timeout(const Duration(seconds: 15)));
    return Chore.fromJson(_choreJson(r));
  }

  /// PATCH /chores/{id} with only what changed: label_name, warning_threshold_days (null =
  /// no reminder), active.
  Future<Chore> editChore(int id, Map<String, dynamic> changes) async {
    final r = await _guard(() => http
        .patch(_uri('/chores/$id'),
            headers: _jsonHeaders, body: jsonEncode({...changes, 'user': _user}))
        .timeout(const Duration(seconds: 15)));
    return Chore.fromJson(_choreJson(r));
  }

  /// GET /chore_events, newest first. [chore] (a [Chore.name]) null = every chore;
  /// [before] is the previous page's [ChoreEventsPage.next].
  Future<ChoreEventsPage> choreEvents(
      {String? chore, bool includeDeleted = false, String? before, int limit = 50}) async {
    final query = {
      'chore': ?chore,
      if (includeDeleted) 'include_deleted': 'true',
      'before': ?before,
      'limit': '$limit',
    };
    final r = await _guard(() => http
        .get(_uri('/chore_events', query), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return ChoreEventsPage.fromJson(_choreJson(r));
  }

  /// POST /chore_events: [chore] (a [Chore.name]) was done. [when] null = now; [doneBy]
  /// empty = not recorded; [startedAt] when it was started (null = not known). Ends the
  /// chore's start and closes its request.
  Future<ChoreEvent> addChoreEvent(String chore,
      {DateTime? when, List<String> doneBy = const [], String notes = '', DateTime? startedAt}) async {
    final r = await _guard(() => http
        .post(_uri('/chore_events'),
            headers: _jsonHeaders,
            body: jsonEncode({
              'user': _user,
              'chore': chore,
              'event_time': (when ?? DateTime.now()).toUtc().toIso8601String(),
              'done_by': doneBy,
              'notes': notes.trim(),
              'started_at': startedAt?.toUtc().toIso8601String(),
            }))
        .timeout(const Duration(seconds: 15)));
    return ChoreEvent.fromJson(_choreJson(r));
  }

  /// PATCH /chore_events/{id} with any of chore, event_time (UTC ISO), done_by, notes.
  Future<ChoreEvent> editChoreEvent(int id, Map<String, dynamic> changes) async {
    final r = await _guard(() => http
        .patch(_uri('/chore_events/$id'),
            headers: _jsonHeaders, body: jsonEncode({...changes, 'user': _user}))
        .timeout(const Duration(seconds: 15)));
    return ChoreEvent.fromJson(_choreJson(r));
  }

  /// DELETE /chore_events/{id}: a soft delete; [restoreChoreEvent] undoes it.
  Future<ChoreEvent> deleteChoreEvent(int id) async {
    final r = await _guard(() => http
        .delete(_uri('/chore_events/$id', _userQuery), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return ChoreEvent.fromJson(_choreJson(r));
  }

  Future<ChoreEvent> restoreChoreEvent(int id) async {
    final r = await _guard(() => http
        .post(_uri('/chore_events/$id/restore', _userQuery), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return ChoreEvent.fromJson(_choreJson(r));
  }

  /// POST /chore_starts: someone is doing [chore] now. [doers] empty = not recorded;
  /// [startedAt] null = now. The server posts it to the chores Discord channel. 409 if it's
  /// already in progress.
  Future<ChoreStart> startChore(String chore,
      {List<String> doers = const [], DateTime? startedAt, String notes = ''}) async {
    final r = await _guard(() => http
        .post(_uri('/chore_starts'),
            headers: _jsonHeaders,
            body: jsonEncode({
              'user': _user,
              'chore': chore,
              'doers': doers,
              'started_at': startedAt?.toUtc().toIso8601String(),
              'notes': notes.trim(),
            }))
        .timeout(const Duration(seconds: 15)));
    return ChoreStart.fromJson(_choreJson(r));
  }

  /// PATCH /chore_starts/{id}: any of doers (join / take over), started_at (a DateTime),
  /// notes. In-progress only.
  Future<ChoreStart> editChoreStart(int id, Map<String, dynamic> changes) async {
    final body = {
      for (final e in changes.entries)
        e.key: e.value is DateTime ? (e.value as DateTime).toUtc().toIso8601String() : e.value,
      'user': _user,
    };
    final r = await _guard(() => http
        .patch(_uri('/chore_starts/$id'), headers: _jsonHeaders, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15)));
    return ChoreStart.fromJson(_choreJson(r));
  }

  /// POST /chore_starts/{id}/stop: gave up without finishing.
  Future<ChoreStart> stopChoreStart(int id) async {
    final r = await _guard(() => http
        .post(_uri('/chore_starts/$id/stop', _userQuery), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return ChoreStart.fromJson(_choreJson(r));
  }

  /// "2026-11-20" for a day.
  static String _day(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';

  /// GET /chore_requests, newest first. [chore] null = every chore; [status] open, done,
  /// cancelled or null (all).
  Future<ChoreRequestsPage> choreRequests(
      {String? chore, String? status, String? before, int limit = 50}) async {
    final query = {'chore': ?chore, 'status': ?status, 'before': ?before, 'limit': '$limit'};
    final r = await _guard(() => http
        .get(_uri('/chore_requests', query), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return ChoreRequestsPage.fromJson(_choreJson(r));
  }

  /// POST /chore_requests: mark [chore] (a [Chore.name]) as needed. The server posts it to
  /// the chores Discord channel. 409 if it already has an open request.
  Future<ChoreRequest> addChoreRequest(String chore,
      {String notes = '', double? quantity, String unit = '', DateTime? neededBy}) async {
    final r = await _guard(() => http
        .post(_uri('/chore_requests'),
            headers: _jsonHeaders,
            body: jsonEncode({
              'user': _user,
              'chore': chore,
              'notes': notes.trim(),
              'quantity': quantity,
              'unit': unit.trim(),
              'needed_by': neededBy == null ? null : _day(neededBy),
            }))
        .timeout(const Duration(seconds: 15)));
    return ChoreRequest.fromJson(_choreJson(r));
  }

  /// PATCH /chore_requests/{id}: any of notes, quantity, unit, needed_by (a DateTime, or null
  /// to clear). Open requests only.
  Future<ChoreRequest> editChoreRequest(int id, Map<String, dynamic> changes) async {
    final body = {
      for (final e in changes.entries)
        e.key: e.value is DateTime ? _day(e.value as DateTime) : e.value,
      'user': _user,
    };
    final r = await _guard(() => http
        .patch(_uri('/chore_requests/$id'), headers: _jsonHeaders, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15)));
    return ChoreRequest.fromJson(_choreJson(r));
  }

  /// POST /chore_requests/{id}/cancel.
  Future<ChoreRequest> cancelChoreRequest(int id) async {
    final r = await _guard(() => http
        .post(_uri('/chore_requests/$id/cancel', _userQuery), headers: _jsonHeaders)
        .timeout(const Duration(seconds: 15)));
    return ChoreRequest.fromJson(_choreJson(r));
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

  // ---------- app updates (server: app_update_api.py) ----------

  /// GET /app_update. An older server without it: ApiException.
  Future<AppUpdates> appUpdates() async {
    final r = await _guard(() => http
        .get(_uri('/app_update'), headers: {'X-API-Key': apiKey})
        .timeout(const Duration(seconds: 10)));
    final body = _detailBody(r, 'app updates');
    if (body is! Map<String, dynamic>) {
      throw ApiException('The server sent something unexpected.');
    }
    return AppUpdates.fromJson(body);
  }

  /// Downloads [update]'s APK (GET /app_update/{channel}/apk) into [dest], calling
  /// [onProgress] with the bytes received so far. Stops early (and throws
  /// [DownloadCancelled]) when [cancelled] returns true. A short download throws.
  Future<void> downloadApk(AppUpdateInfo update, File dest,
      {void Function(int received)? onProgress, bool Function()? cancelled}) async {
    final client = http.Client();
    try {
      final req = http.Request('GET', _uri('/app_update/${update.channel}/apk'))
        ..headers['X-API-Key'] = apiKey;
      final http.StreamedResponse r;
      try {
        r = await client.send(req).timeout(const Duration(seconds: 30));
      } on TimeoutException {
        throw ApiException('${server.address} took too long to answer.');
      } on SocketException {
        throw _unreachable();
      } on http.ClientException {
        throw _unreachable();
      }
      if (r.statusCode != 200) {
        await r.stream.drain<void>();
        throw ApiException(r.statusCode == 401
            ? 'Wrong API key for this server. Fix it under Servers.'
            : r.statusCode == 404
                ? "The server doesn't have that update any more. Pull to refresh and try again."
                : 'Download failed (server error ${r.statusCode}).');
      }
      final sink = dest.openWrite();
      var received = 0;
      try {
        await for (final chunk in r.stream.timeout(const Duration(seconds: 30))) {
          if (cancelled?.call() ?? false) throw const DownloadCancelled();
          sink.add(chunk);
          received += chunk.length;
          onProgress?.call(received);
        }
      } on TimeoutException {
        throw ApiException('The download stalled. Check the connection and try again.');
      } on SocketException {
        throw ApiException('The download was cut off. Check the connection and try again.');
      } on http.ClientException {
        throw ApiException('The download was cut off. Check the connection and try again.');
      } finally {
        await sink.close();
      }
      if (received != update.size) {
        throw ApiException('The download was incomplete. Try again.');
      }
    } finally {
      client.close();
    }
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
    } on HandshakeException {
      // HTTPS (Tailscale Serve) only: the certificate couldn't be checked.
      throw ApiException(
          "Couldn't make a secure connection to ${server.address}. Check that HTTPS "
          'certificates are turned on for the tailnet and the address is right.');
    } on http.ClientException {
      throw _unreachable();
    }
  }

  ApiException _unreachable() => ApiException(
      "Can't reach ${server.address}. ${server.reachHint}");

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
