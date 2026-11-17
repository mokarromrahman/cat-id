import 'dart:convert';

import 'package:cat_id_app/screens/health_screen.dart';
import 'package:cat_id_app/server_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> health(
        {Object? version = _absent,
         Object? commit = _absent,
         Object? litterboxes = _absent,
         Object? chores = _absent}) =>
    {
      'model_loaded': true,
      'classes': ['Litten', 'Shinx', 'neither'],
      'photos': {'Litten': 912, 'Shinx': 703, 'neither': 42},
      'waiting_in_inbox': 3,
      if (version != _absent) 'version': version,
      if (commit != _absent) 'commit': commit,
      if (litterboxes != _absent) 'litterboxes': litterboxes,
      if (chores != _absent) 'chores': chores,
    };

Future<void> _pumpHealth(WidgetTester tester, Map<String, dynamic> body) async {
  final client = MockClient((req) async => http.Response(jsonEncode(body), 200,
      headers: {'content-type': 'application/json'}));
  await http.runWithClient(() async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: HealthScreen(
          server: Server(id: '1', name: 'Home', address: '192.168.1.116:8000'),
          onOpenLabel: () {},
        ),
      ),
    ));
    await tester.pumpAndSettle();
  }, () => client);
}

const _absent = Object();

void main() {
  group('server version text', () {
    test('a release shows its tag and the short commit', () {
      expect(serverVersionText(health(version: 'v0.2.0', commit: '433c2538f1e2d3c4b5a6')),
          ('Server v0.2.0', 'Commit 433c253'));
    });
    test('a local build says so', () {
      expect(serverVersionText(health(version: 'dev', commit: null)), ('Server: local build', 'No commit recorded'));
      expect(serverVersionText(health(version: 'dev', commit: 'abc1234def')), ('Server: local build', 'Commit abc1234'));
    });
    test('an older server without the fields', () {
      expect(serverVersionText(health()).$1, 'Server version unknown');
    });
  });

  testWidgets('the Health tab shows the server version from /health', (tester) async {
    final client = MockClient((req) async {
      expect(req.url.path, '/health');
      return http.Response(jsonEncode(health(version: 'v0.2.0', commit: '433c2538f1e2d3c4b5a6')), 200,
          headers: {'content-type': 'application/json'});
    });
    await http.runWithClient(() async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: HealthScreen(
            server: Server(id: '1', name: 'Home', address: '192.168.1.116:8000'),
            onOpenLabel: () {},
          ),
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.text('Server v0.2.0', skipOffstage: false), findsOneWidget);
      expect(find.text('Commit 433c253', skipOffstage: false), findsOneWidget);
      expect(find.text('Model loaded'), findsOneWidget); // the rest of the tab still shows
    }, () => client);
  });

  group('litterbox cleaning', () {
    final now = DateTime(2026, 11, 15, 12);
    test('overdue after 24 hours or when never cleaned', () {
      expect(cleanOverdue(null, now), isTrue);
      expect(cleanOverdue(now.subtract(const Duration(hours: 23)), now), isFalse);
      expect(cleanOverdue(now.subtract(const Duration(hours: 25)), now), isTrue);
    });
    test('ago text', () {
      expect(agoText(now.subtract(const Duration(seconds: 20)), now), 'just now');
      expect(agoText(now.subtract(const Duration(minutes: 25)), now), '25 min ago');
      expect(agoText(now.subtract(const Duration(hours: 5)), now), '5 h ago');
      expect(agoText(now.subtract(const Duration(hours: 30)), now), '1 day ago');
      expect(agoText(now.subtract(const Duration(days: 3)), now), '3 days ago');
    });
  });

  testWidgets('the Health tab shows each litterbox, highlighting an overdue one', (tester) async {
    final now = DateTime.now().toUtc();
    await _pumpHealth(tester, health(litterboxes: [
      {
        'location': 'basement', 'name': 'Basement',
        'last_cleaned': now.subtract(const Duration(hours: 2)).toIso8601String(),
        'last_cleaned_by': 'Ashley',
        'bag_last_changed': now.subtract(const Duration(days: 3)).toIso8601String(),
      },
      {'location': 'master_bathroom', 'name': 'Master Bathroom',
       'last_cleaned': now.subtract(const Duration(hours: 30)).toIso8601String(),
       'bag_last_changed': null},
    ]));
    expect(find.text('Litterboxes', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('(2 h ago) by Ashley', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('(1 day ago) by', skipOffstage: false), findsNothing); // not known
    expect(find.textContaining('Bag was last changed', skipOffstage: false), findsOneWidget);
    expect(find.text('Bag change not recorded yet', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('(1 day ago)', skipOffstage: false), findsOneWidget);
    expect(find.byIcon(Icons.warning_amber, skipOffstage: false), findsOneWidget); // bathroom only
  });

  testWidgets('no Litterboxes card for an older server', (tester) async {
    await _pumpHealth(tester, health());
    expect(find.text('Litterboxes', skipOffstage: false), findsNothing);
    expect(find.text('Model loaded'), findsOneWidget);
  });

  testWidgets("a note when the server's database is down", (tester) async {
    await _pumpHealth(tester, health(litterboxes: null));
    expect(find.text('Litterboxes', skipOffstage: false), findsOneWidget);
    expect(find.textContaining("database isn't reachable", skipOffstage: false), findsOneWidget);
  });

  group('chores card', () {
    Map<String, dynamic> c(String label, {bool overdue = false, String? lastDone, String? due}) => {
          'id': 1, 'name': label.toLowerCase(), 'label_name': label,
          'warning_threshold_days': 7, 'active': true, 'last_done': lastDone,
          'last_done_by': ['Mac'], 'due_at': due, 'overdue': overdue,
        };

    testWidgets('lists only the overdue chores', (tester) async {
      final now = DateTime.now().toUtc();
      await _pumpHealth(tester, health(chores: [
        c('Vacuum', lastDone: now.toIso8601String(),
            due: now.add(const Duration(days: 7)).toIso8601String()),
        c('Mopping', overdue: true,
            lastDone: now.subtract(const Duration(days: 9)).toIso8601String(),
            due: now.subtract(const Duration(days: 2)).toIso8601String()),
      ]));
      expect(find.text('Chores', skipOffstage: false), findsOneWidget);
      expect(find.text('Mopping', skipOffstage: false), findsOneWidget);
      expect(find.text('Overdue by 2 days (every 7 days)', skipOffstage: false), findsOneWidget);
      expect(find.text('Vacuum', skipOffstage: false), findsNothing);
    });

    testWidgets('nothing overdue', (tester) async {
      await _pumpHealth(tester, health(chores: [c('Vacuum')..['warning_threshold_days'] = null]));
      expect(find.text('Nothing overdue or needed', skipOffstage: false), findsOneWidget);
    });

    testWidgets('a chore marked as needed is listed with its request', (tester) async {
      final now = DateTime.now().toUtc();
      await _pumpHealth(tester, health(chores: [
        c('Vacuum', lastDone: now.toIso8601String(),
            due: now.add(const Duration(days: 7)).toIso8601String()),
        {
          ...c('Cat Food Pickup'),
          'warning_threshold_days': null,
          'request': {
            'id': 1, 'chore': 'cat_food_pickup', 'chore_label': 'Cat Food Pickup',
            'requested_on': now.subtract(const Duration(hours: 3)).toIso8601String(),
            'requested_by': 'Ashley', 'notes': 'Royal Canin renal', 'quantity': 2,
            'unit': 'bags', 'needed_by': null, 'status': 'open', 'overdue': false,
          },
        },
      ]));
      expect(find.text('Cat Food Pickup', skipOffstage: false), findsOneWidget);
      expect(find.text('Needed: asked by Ashley (3 h ago)', skipOffstage: false), findsOneWidget);
      expect(find.text('2 bags', skipOffstage: false), findsOneWidget);
      expect(find.text('Royal Canin renal', skipOffstage: false), findsOneWidget);
      expect(find.text('No reminder', skipOffstage: false), findsNothing);
      expect(find.text('Vacuum', skipOffstage: false), findsNothing);
    });

    testWidgets('a chore in progress is listed with who is doing it', (tester) async {
      final now = DateTime.now().toUtc();
      await _pumpHealth(tester, health(chores: [
        {
          ...c('Vacuum', lastDone: now.toIso8601String(),
              due: now.add(const Duration(days: 7)).toIso8601String()),
          'in_progress': {
            'id': 1, 'chore': 'vacuum', 'chore_label': 'Vacuum',
            'started_on': now.subtract(const Duration(minutes: 30)).toIso8601String(),
            'doers': ['Mac'], 'status': 'in_progress',
          },
        },
      ]));
      expect(find.text('Vacuum', skipOffstage: false), findsOneWidget);
      expect(find.textContaining('In progress: Mac, since', skipOffstage: false), findsOneWidget);
      expect(find.textContaining('Due in', skipOffstage: false), findsNothing);
    });

    testWidgets('no card for an older server', (tester) async {
      await _pumpHealth(tester, health());
      expect(find.text('Chores', skipOffstage: false), findsNothing);
    });

    testWidgets("a note when the server's database is down", (tester) async {
      await _pumpHealth(tester, health(chores: null));
      expect(find.text('Chores', skipOffstage: false), findsOneWidget);
      expect(find.textContaining("database isn't reachable", skipOffstage: false), findsOneWidget);
    });
  });
}
