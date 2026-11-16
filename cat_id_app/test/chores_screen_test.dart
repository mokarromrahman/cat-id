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

/// A fake server for /chores and /chore_events that records what the app sends.
class FakeServer {
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

Future<void> _pump(WidgetTester tester, ServerStore store) async {
  tester.view.physicalSize = const Size(412, 915);
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

  test('the menu lists Chores', () {
    expect(kMenuOrder, [MenuPage.chores]);
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
}
