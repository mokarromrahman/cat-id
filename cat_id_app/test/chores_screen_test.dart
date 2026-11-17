import 'dart:convert';

import 'package:cat_id_app/api.dart';
import 'package:cat_id_app/screens/chores_screen.dart';
import 'package:cat_id_app/screens/home_screen.dart';
import 'package:cat_id_app/server_store.dart';
import 'package:cat_id_app/who_am_i.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

final _now = DateTime.now().toUtc();
String _ago(Duration d) => _now.subtract(d).toIso8601String();

Map<String, dynamic> chore(int id, String name, String label, int? days,
        {String? lastDone, List<String> by = const [], String? due, bool overdue = false}) =>
    {
      'id': id, 'name': name, 'label_name': label, 'warning_threshold_days': days,
      'active': true, 'last_done': lastDone, 'last_done_by': by, 'due_at': due,
      'overdue': overdue,
    };

Map<String, dynamic> request(int id, String chore, String label,
        {String by = 'Mac', double? quantity, String? unit, String? neededBy, String? notes,
        String status = 'open', bool overdue = false}) =>
    {
      'id': id, 'chore_id': 3, 'chore': chore, 'chore_label': label,
      'requested_on': _ago(const Duration(hours: 2)), 'requested_by': by, 'notes': notes,
      'quantity': quantity, 'unit': unit, 'needed_by': neededBy, 'status': status,
      'done_on': null, 'chore_event_id': null, 'done_by': [], 'cancelled_on': null,
      'closed_by': null, 'overdue': overdue,
    };

final _startedAt = _ago(const Duration(minutes: 20));

Map<String, dynamic> start(int id, String chore, String label,
        {List<String> doers = const ['Ashley', 'Mac'], String? notes, String status = 'in_progress'}) =>
    {
      'id': id, 'chore_id': 1, 'chore': chore, 'chore_label': label, 'started_on': _startedAt,
      'doers': doers, 'reporter': 'Ashley', 'notes': notes, 'status': status, 'ended_on': null,
      'ended_by': null, 'chore_event_id': null,
    };

/// A fake server for /chores, /chore_events, /chore_requests and /chore_starts that records
/// what the app sends. [withRequest]: Cat Food Pickup has an open request. [withStart]:
/// Vacuum is in progress (Ashley and Mac, 20 min ago).
class FakeServer {
  FakeServer({bool withRequest = false, bool withStart = false}) {
    if (withStart) {
      chores[0]['in_progress'] = start(5, 'vacuum', 'Vacuum', notes: 'upstairs first');
    }
    if (withRequest) {
      chores[2]['request'] = request(7, 'cat_food_pickup', 'Cat Food Pickup',
          quantity: 2, unit: 'bags', neededBy: '2099-11-20', notes: 'Royal Canin renal');
    }
  }

  final requests = <http.Request>[];
  final chores = <Map<String, dynamic>>[
    chore(1, 'vacuum', 'Vacuum', 7,
        lastDone: _ago(const Duration(days: 2)), by: ['Ashley'],
        due: _now.add(const Duration(days: 5)).toIso8601String()),
    chore(2, 'mopping', 'Mopping', 14,
        lastDone: _ago(const Duration(days: 17)), by: ['Mac'],
        due: _ago(const Duration(days: 3)), overdue: true),
    chore(3, 'cat_food_pickup', 'Cat Food Pickup', null),
    chore(4, 'bed_sheets', 'Bed Sheets', 14, overdue: true),
  ];

  late final client = MockClient((req) async {
    requests.add(req);
    if (req.method == 'GET' && req.url.path == '/chores') {
      return _json({'chores': chores, 'people': ['Ashley', 'Mac']});
    }
    if (req.method == 'POST' && req.url.path == '/chore_events') {
      final b = jsonDecode(req.body) as Map<String, dynamic>;
      final c = chores.firstWhere((c) => c['name'] == b['chore']);
      return _json({
        'id': 1, 'chore': c['name'], 'chore_label': c['label_name'],
        'event_timestamp': b['event_time'], 'done_by': b['done_by'], 'reporter': b['user'],
        'notes': b['notes'], 'deleted_on': null, 'modified_by': b['user'],
      });
    }
    if (req.method == 'POST' && req.url.path == '/chore_starts') {
      final b = jsonDecode(req.body) as Map<String, dynamic>;
      final c = chores.firstWhere((c) => c['name'] == b['chore']);
      return _json(start(6, c['name'] as String, c['label_name'] as String,
          doers: [for (final d in b['doers'] as List) d as String], notes: b['notes'] as String?));
    }
    if (req.method == 'PATCH' && req.url.path.startsWith('/chore_starts/')) {
      return _json(start(5, 'vacuum', 'Vacuum'));
    }
    if (req.method == 'POST' && req.url.path.endsWith('/stop')) {
      return _json(start(5, 'vacuum', 'Vacuum', status: 'stopped'));
    }
    if (req.method == 'POST' && req.url.path == '/chore_requests') {
      final b = jsonDecode(req.body) as Map<String, dynamic>;
      final c = chores.firstWhere((c) => c['name'] == b['chore']);
      return _json(request(8, c['name'] as String, c['label_name'] as String,
          by: b['user'] as String, quantity: (b['quantity'] as num?)?.toDouble(),
          unit: b['unit'] as String?, neededBy: b['needed_by'] as String?,
          notes: b['notes'] as String?));
    }
    if (req.method == 'PATCH' && req.url.path.startsWith('/chore_requests/')) {
      return _json(request(7, 'cat_food_pickup', 'Cat Food Pickup'));
    }
    if (req.method == 'POST' && req.url.path.endsWith('/cancel')) {
      return _json(request(7, 'cat_food_pickup', 'Cat Food Pickup', status: 'cancelled'));
    }
    if (req.method == 'POST' && req.url.path == '/chores') {
      final b = jsonDecode(req.body) as Map<String, dynamic>;
      final c = chore(chores.length + 1, 'x', b['label_name'] as String,
          b['warning_threshold_days'] as int?, overdue: b['warning_threshold_days'] != null);
      chores.add(c);
      return _json(c);
    }
    return http.Response('{"detail":"Not Found"}', 404);
  });

  static http.Response _json(Object body) =>
      http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});
}

Future<ServerStore> _store() async {
  SharedPreferences.setMockInitialValues({
    'servers': jsonEncode([
      {'id': '1', 'name': 'Home', 'address': '192.168.1.116:8000'}
    ]),
    'selected_server': '1',
    'who_am_i': 'Ashley',
  });
  FlutterSecureStorage.setMockInitialValues({'apikey_1': 'test'});
  await WhoAmI.load();
  return ServerStore.load();
}

Future<void> _pump(WidgetTester tester, ServerStore store, {double height = 915}) async {
  tester.view.physicalSize = Size(412, height);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(home: ChoresScreen(store: store, server: store.selected!)));
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

Chore _c(Map<String, dynamic> j) => Chore.fromJson(j);

void main() {
  WidgetController.hitTestWarningShouldBeFatal = true;

  test('the menu lists Chores, then Settings', () {
    expect(kMenuOrder, [MenuPage.chores, MenuPage.settings]);
  });

  group('chore text', () {
    final now = DateTime(2026, 11, 15, 12);
    Chore at({int? days = 7, DateTime? last, DateTime? due, bool overdue = false}) => _c(chore(
        1, 'vacuum', 'Vacuum', days,
        lastDone: last?.toUtc().toIso8601String(), due: due?.toUtc().toIso8601String(),
        overdue: overdue));

    test('no threshold, never done, overdue, due', () {
      expect(choreDueText(at(days: null), now), 'No reminder');
      expect(choreDueText(at(overdue: true), now), 'Never done (every 7 days)');
      expect(
          choreDueText(
              at(last: now.subtract(const Duration(days: 10)),
                  due: now.subtract(const Duration(days: 3)), overdue: true),
              now),
          'Overdue by 3 days (every 7 days)');
      expect(
          choreDueText(
              at(days: 1, last: now.subtract(const Duration(hours: 19)),
                  due: now.add(const Duration(hours: 5))),
              now),
          'Due in 5 h (every day)');
    });

    test('overdue first (never done before the rest), then by due date, then no reminder', () {
      final list = [
        _c(chore(1, 'a', 'A', null)),
        _c(chore(2, 'b', 'B', 7, due: now.add(const Duration(days: 3)).toUtc().toIso8601String(),
            lastDone: now.toUtc().toIso8601String())),
        _c(chore(3, 'c', 'C', 7, due: now.subtract(const Duration(days: 1)).toUtc().toIso8601String(),
            lastDone: now.toUtc().toIso8601String(), overdue: true)),
        _c(chore(4, 'd', 'D', 7, overdue: true)),
        _c(chore(5, 'e', 'E', 7, due: now.add(const Duration(days: 1)).toUtc().toIso8601String(),
            lastDone: now.toUtc().toIso8601String())),
      ];
      expect([for (final c in sortChores(list)) c.name], ['d', 'c', 'e', 'b', 'a']);
    });

    test('needed chores come after the overdue ones, soonest needed-by first', () {
      Map<String, dynamic> withRequest(Map<String, dynamic> c, String? neededBy) =>
          c..['request'] = request(c['id'] as int, c['name'] as String, c['label_name'] as String,
              neededBy: neededBy);
      final list = [
        _c(chore(1, 'a', 'A', null)),
        _c(withRequest(chore(2, 'b', 'B', null), null)),
        _c(withRequest(chore(3, 'c', 'C', null), '2099-01-02')),
        _c(chore(4, 'd', 'D', 7, overdue: true)),
        _c(chore(5, 'e', 'E', 7, due: now.add(const Duration(days: 1)).toUtc().toIso8601String(),
            lastDone: now.toUtc().toIso8601String())),
      ];
      expect([for (final c in sortChores(list)) c.name], ['d', 'c', 'b', 'e', 'a']);
    });

    test('a request overdue by its needed-by day leaves the reminder line alone', () {
      final c = _c(chore(1, 'vacuum', 'Vacuum', 7,
          lastDone: now.subtract(const Duration(days: 2)).toUtc().toIso8601String(),
          due: now.add(const Duration(days: 5)).toUtc().toIso8601String(), overdue: true)
        ..['request'] = request(1, 'vacuum', 'Vacuum', neededBy: '2026-11-14', overdue: true));
      expect(choreDueText(c, now), 'Due in 5 days (every 7 days)');
      expect(thresholdOverdue(c, now), isFalse);
      expect(c.request!.overdue, isTrue);
    });

    test('time taken text', () {
      expect(tookText(const Duration(seconds: 10)), 'under a minute');
      expect(tookText(const Duration(seconds: 40)), '1 min');
      expect(tookText(const Duration(minutes: 45)), '45 min');
      expect(tookText(const Duration(hours: 1)), '1 h');
      expect(tookText(const Duration(hours: 1, minutes: 20)), '1 h 20 min');
      expect(tookText(const Duration(days: 1)), '1 day');
      expect(tookText(const Duration(days: 2, hours: 3, minutes: 5)), '2 days 3 h');
    });

    test('a Done keeps its start time and how long it took', () {
      final e = ChoreEvent.fromJson({
        'id': 1, 'chore': 'vacuum', 'chore_label': 'Vacuum',
        'event_timestamp': '2026-11-15T19:00:00Z', 'started_on': '2026-11-15T18:15:00Z',
        'took_seconds': 2700, 'done_by': ['Mac'],
      });
      expect(e.startedOn, DateTime.utc(2026, 11, 15, 18, 15).toLocal());
      expect(e.took, const Duration(minutes: 45));
      final old = ChoreEvent.fromJson(
          {'id': 2, 'chore': 'vacuum', 'event_timestamp': '2026-11-15T19:00:00Z'});
      expect(old.startedOn, isNull);
      expect(old.took, isNull);
    });

    test('quantity text', () {
      ChoreRequest r(double? q, String? u) =>
          ChoreRequest.fromJson(request(1, 'x', 'X', quantity: q, unit: u));
      expect(r(2, 'bags').quantityText, '2 bags');
      expect(r(1.5, null).quantityText, '1.5');
      expect(r(null, 'bags').quantityText, 'bags');
      expect(r(null, null).quantityText, isNull);
    });
  });

  testWidgets('lists the chores, overdue ones first and highlighted', (tester) async {
    final server = FakeServer();
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      expect(find.text('2 overdue'), findsOneWidget);
      final order = [
        for (final t in ['Bed Sheets', 'Mopping', 'Vacuum', 'Cat Food Pickup'])
          tester.getTopLeft(find.text(t)).dy
      ];
      expect(order, [...order]..sort());
      expect(find.text('Never done (every 14 days)'), findsOneWidget);
      expect(find.text('Overdue by 3 days (every 14 days)'), findsOneWidget);
      expect(find.text('No reminder'), findsOneWidget);
      expect(find.textContaining('by Ashley (2 days ago)'), findsOneWidget);
      expect(find.byIcon(Icons.warning_amber), findsNWidgets(2));
      expect(server.requests.first.headers['X-API-Key'] ?? server.requests.first.headers['x-api-key'],
          'test');
    }, () => server.client);
  });

  testWidgets("every Done button sits at its card's right edge, request or not", (tester) async {
    final server = FakeServer(); // Cat Food Pickup has an open request (no Needed button)
    final store = await _store();
    await http.runWithClient(() async {
      // A narrow phone, so Done moves to a second row under a short first row.
      tester.view.physicalSize = const Size(340, 4000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(home: ChoresScreen(store: store, server: store.selected!)));
      await tester.pumpAndSettle();
      final dones = find.widgetWithText(FilledButton, 'Done');
      expect(dones, findsAtLeastNWidgets(2));
      for (final e in dones.evaluate()) {
        final done = find.byWidget(e.widget);
        final card = find.ancestor(of: done, matching: find.byType(Card)).first;
        // The card's own padding on the right is 8 (plus the button's margin).
        expect(tester.getRect(card).right - tester.getRect(done).right, lessThan(20),
            reason: 'Done should be at the right edge of its card');
      }
    }, () => server.client);
  });

  testWidgets('Done records the chore, done by you unless changed', (tester) async {
    final server = FakeServer();
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      // The Vacuum card's Done button (the 3rd card in sorted order).
      final vacuumCard = find.ancestor(of: find.text('Vacuum'), matching: find.byType(Card));
      await _tap(tester, find.descendant(of: vacuumCard, matching: find.text('Done')));
      expect(find.text('Vacuum done'), findsOneWidget);
      // Ashley (who am I) is picked already; add Mac.
      await _tap(tester, find.widgetWithText(FilterChip, 'Mac'));
      await tester.enterText(find.widgetWithText(TextField, 'Notes (optional)'), 'upstairs only');
      await _tap(tester, find.widgetWithText(FilledButton, 'Save'));

      final post = server.requests.singleWhere((r) => r.method == 'POST');
      final body = jsonDecode(post.body) as Map<String, dynamic>;
      expect(post.url.path, '/chore_events');
      expect(body['chore'], 'vacuum');
      expect(body['done_by'], ['Ashley', 'Mac']);
      expect(body['notes'], 'upstairs only');
      expect(body['user'], 'Ashley');
      expect(DateTime.parse(body['event_time'] as String).isUtc, isTrue);
      expect(find.text('Vacuum recorded.'), findsOneWidget);
      // The list reloads after saving.
      expect(server.requests.where((r) => r.url.path == '/chores').length, 2);
    }, () => server.client);
  });

  testWidgets('Add chore sends the name and threshold', (tester) async {
    final server = FakeServer();
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      await _tap(tester, find.text('Add chore'));
      await tester.enterText(find.widgetWithText(TextField, 'Name'), 'Clean Fridge');
      await tester.enterText(find.widgetWithText(TextField, 'Warn after (days)'), '30');
      await _tap(tester, find.widgetWithText(FilledButton, 'Save'));

      final post = server.requests.singleWhere((r) => r.method == 'POST');
      expect(post.url.path, '/chores');
      expect(jsonDecode(post.body), {'user': 'Ashley', 'label_name': 'Clean Fridge',
                                      'warning_threshold_days': 30});
      expect(find.text('Clean Fridge added.'), findsOneWidget);
    }, () => server.client);
  });

  testWidgets('a chore without a threshold can be added (blank days)', (tester) async {
    final server = FakeServer();
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      await _tap(tester, find.text('Add chore'));
      await tester.enterText(find.widgetWithText(TextField, 'Name'), 'Descale Kettle');
      await _tap(tester, find.widgetWithText(FilledButton, 'Save'));
      final post = server.requests.singleWhere((r) => r.method == 'POST');
      expect((jsonDecode(post.body) as Map)['warning_threshold_days'], isNull);
    }, () => server.client);
  });

  testWidgets('Needed sends the quantity, unit, day and note', (tester) async {
    final server = FakeServer();
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      final vacuumCard = find.ancestor(of: find.text('Vacuum'), matching: find.byType(Card));
      await _tap(tester, find.descendant(of: vacuumCard, matching: find.text('Needed')));
      expect(find.text('Vacuum needed'), findsOneWidget);
      await tester.enterText(find.widgetWithText(TextField, 'Quantity (optional)'), '1,5');
      await tester.enterText(find.widgetWithText(TextField, 'Unit (optional)'), 'rooms');
      await tester.enterText(find.widgetWithText(TextField, 'Notes (optional)'), 'guests Friday');
      await _tap(tester, find.text('Needed by'));
      await _tap(tester, find.text('OK')); // today
      await _tap(tester, find.widgetWithText(FilledButton, 'Save and tell Discord'));

      final post = server.requests.singleWhere((r) => r.method == 'POST');
      expect(post.url.path, '/chore_requests');
      final body = jsonDecode(post.body) as Map<String, dynamic>;
      final today = DateTime.now();
      expect(body, {
        'user': 'Ashley', 'chore': 'vacuum', 'notes': 'guests Friday', 'quantity': 1.5,
        'unit': 'rooms',
        'needed_by': '${today.year}-${today.month.toString().padLeft(2, '0')}-'
            '${today.day.toString().padLeft(2, '0')}',
      });
      expect(find.text('Vacuum marked as needed.'), findsOneWidget);
    }, () => server.client);
  });

  testWidgets('a bad quantity is refused before sending', (tester) async {
    final server = FakeServer();
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      final vacuumCard = find.ancestor(of: find.text('Vacuum'), matching: find.byType(Card));
      await _tap(tester, find.descendant(of: vacuumCard, matching: find.text('Needed')));
      await tester.enterText(find.widgetWithText(TextField, 'Quantity (optional)'), '0');
      await _tap(tester, find.widgetWithText(FilledButton, 'Save and tell Discord'));
      expect(find.textContaining('Quantity must be a number above 0'), findsOneWidget);
      expect(server.requests.where((r) => r.method == 'POST'), isEmpty);
    }, () => server.client);
  });

  testWidgets('an open request shows on its card and in the Done sheet', (tester) async {
    final server = FakeServer(withRequest: true);
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store, height: 1400); // all four cards built
      expect(find.text('2 overdue · 1 needed'), findsOneWidget);
      // Overdue ones, then the needed one, then the rest.
      final order = [
        for (final t in ['Bed Sheets', 'Mopping', 'Cat Food Pickup', 'Vacuum'])
          tester.getTopLeft(find.text(t)).dy
      ];
      expect(order, [...order]..sort());
      expect(find.text('Needed: asked by Mac (2 h ago)'), findsOneWidget);
      expect(find.text('2 bags'), findsOneWidget);
      expect(find.text('Royal Canin renal'), findsOneWidget);
      expect(find.byIcon(Icons.shopping_cart_outlined), findsOneWidget);
      // No "Needed" button while one is open; Edit request / Cancel request instead.
      final foodCard = find.ancestor(of: find.text('Cat Food Pickup'), matching: find.byType(Card));
      expect(find.descendant(of: foodCard, matching: find.text('Needed')), findsNothing);
      expect(find.descendant(of: foodCard, matching: find.text('Cancel request')), findsOneWidget);

      await _tap(tester, find.descendant(of: foodCard, matching: find.text('Done')));
      expect(find.text('Cat Food Pickup done'), findsOneWidget);
      expect(find.text('Saving this closes the request.'), findsOneWidget);
      expect(find.text('Royal Canin renal'), findsNWidgets(2)); // card + sheet
    }, () => server.client);
  });

  testWidgets('Edit request sends only what changed', (tester) async {
    final server = FakeServer(withRequest: true);
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      await _tap(tester, find.text('Edit request'));
      expect(find.widgetWithText(TextField, '2'), findsOneWidget);
      await tester.enterText(find.widgetWithText(TextField, 'Quantity (optional)'), '3');
      await _tap(tester, find.widgetWithText(FilledButton, 'Save changes'));
      final patch = server.requests.singleWhere((r) => r.method == 'PATCH');
      expect(patch.url.path, '/chore_requests/7');
      expect(jsonDecode(patch.body), {'quantity': 3.0, 'user': 'Ashley'});
      expect(find.text('Request saved.'), findsOneWidget);
    }, () => server.client);
  });

  testWidgets('Cancel request asks first, then cancels', (tester) async {
    final server = FakeServer(withRequest: true);
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      await _tap(tester, find.widgetWithText(TextButton, 'Cancel request'));
      expect(find.text('Cancel the Cat Food Pickup request?'), findsOneWidget);
      await _tap(tester, find.widgetWithText(FilledButton, 'Cancel request'));
      final post = server.requests.singleWhere((r) => r.method == 'POST');
      expect(post.url.path, '/chore_requests/7/cancel');
      expect(post.url.queryParameters['user'], 'Ashley');
      expect(find.text('Request cancelled.'), findsOneWidget);
    }, () => server.client);
  });

  testWidgets('Start sends you as the one doing it, now, and the note', (tester) async {
    final server = FakeServer();
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store);
      final vacuumCard = find.ancestor(of: find.text('Vacuum'), matching: find.byType(Card));
      await _tap(tester, find.descendant(of: vacuumCard, matching: find.text('Start')));
      expect(find.text('Start Vacuum'), findsOneWidget);
      expect(tester.widget<FilterChip>(find.widgetWithText(FilterChip, 'Ashley')).selected, isTrue);
      await tester.enterText(find.widgetWithText(TextField, 'Notes (optional)'), 'upstairs first');
      await _tap(tester, find.widgetWithText(FilledButton, 'Start and tell Discord'));

      final post = server.requests.singleWhere((r) => r.method == 'POST');
      expect(post.url.path, '/chore_starts');
      expect(jsonDecode(post.body), {
        'user': 'Ashley', 'chore': 'vacuum', 'doers': ['Ashley'], 'started_at': null,
        'notes': 'upstairs first',
      });
      expect(find.text('Vacuum started.'), findsOneWidget);
    }, () => server.client);
  });

  testWidgets('a chore in progress shows who and since when; Done takes over its start',
      (tester) async {
    final server = FakeServer(withStart: true);
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store, height: 1400);
      expect(find.text('2 overdue · 1 in progress'), findsOneWidget);
      expect(find.textContaining('In progress: Ashley and Mac, since'), findsOneWidget);
      expect(find.textContaining('(20 min)'), findsOneWidget);
      expect(find.text('upstairs first'), findsOneWidget);
      final vacuumCard = find.ancestor(of: find.text('Vacuum'), matching: find.byType(Card)).first;
      expect(find.descendant(of: vacuumCard, matching: find.text('Start')), findsNothing);

      await _tap(tester, find.descendant(of: vacuumCard, matching: find.text('Done')));
      // Done by = whoever started it; Started = the start's time, with the time it took.
      expect(tester.widget<FilterChip>(find.widgetWithText(FilterChip, 'Mac')).selected, isTrue);
      expect(tester.widget<FilterChip>(find.widgetWithText(FilterChip, 'Ashley')).selected, isTrue);
      expect(find.textContaining('took 20 min'), findsOneWidget);
      await _tap(tester, find.widgetWithText(FilledButton, 'Save'));

      final post = server.requests.singleWhere((r) => r.method == 'POST');
      final body = jsonDecode(post.body) as Map<String, dynamic>;
      expect(body['done_by'], ['Ashley', 'Mac']);
      expect(DateTime.parse(body['started_at'] as String), DateTime.parse(_startedAt));
    }, () => server.client);
  });

  testWidgets('clearing Started sends no start time', (tester) async {
    final server = FakeServer(withStart: true);
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store, height: 1400);
      final vacuumCard = find.ancestor(of: find.text('Vacuum'), matching: find.byType(Card)).first;
      await _tap(tester, find.descendant(of: vacuumCard, matching: find.text('Done')));
      await _tap(tester, find.widgetWithText(TextButton, 'Clear'));
      expect(find.text('Not recorded: no time taken'), findsOneWidget);
      await _tap(tester, find.widgetWithText(FilledButton, 'Save'));
      final body = jsonDecode(server.requests.singleWhere((r) => r.method == 'POST').body) as Map;
      expect(body.containsKey('started_at'), isTrue);
      expect(body['started_at'], isNull);
    }, () => server.client);
  });

  testWidgets('joining a chore in progress sends the new people only', (tester) async {
    final server = FakeServer(withStart: true);
    server.chores[0]['in_progress'] = start(5, 'vacuum', 'Vacuum', doers: ['Mac']);
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store, height: 1400);
      await _tap(tester, find.text('Who / when'));
      expect(find.text('Vacuum in progress'), findsOneWidget);
      await _tap(tester, find.widgetWithText(FilterChip, 'Ashley'));
      await _tap(tester, find.widgetWithText(FilledButton, 'Save changes'));
      final patch = server.requests.singleWhere((r) => r.method == 'PATCH');
      expect(patch.url.path, '/chore_starts/5');
      expect(jsonDecode(patch.body), {'doers': ['Ashley', 'Mac'], 'user': 'Ashley'});
    }, () => server.client);
  });

  testWidgets('Stop asks first, then stops', (tester) async {
    final server = FakeServer(withStart: true);
    final store = await _store();
    await http.runWithClient(() async {
      await _pump(tester, store, height: 1400);
      await _tap(tester, find.widgetWithText(TextButton, 'Stop'));
      expect(find.text('Stop Vacuum?'), findsOneWidget);
      await _tap(tester, find.widgetWithText(FilledButton, 'Stop'));
      final post = server.requests.singleWhere((r) => r.method == 'POST');
      expect(post.url.path, '/chore_starts/5/stop');
      expect(post.url.queryParameters['user'], 'Ashley');
      expect(find.text('Vacuum stopped.'), findsOneWidget);
    }, () => server.client);
  });
}
