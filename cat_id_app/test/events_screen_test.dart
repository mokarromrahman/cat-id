import 'dart:convert';

import 'package:cat_id_app/api.dart';
import 'package:cat_id_app/screens/events_screen.dart';
import 'package:cat_id_app/server_store.dart';
import 'package:cat_id_app/who_am_i.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

String day(DateTime d) => isoDay(d);
DateTime today() {
  final n = DateTime.now();
  return DateTime(n.year, n.month, n.day);
}

/// A fake server for /event_types and /events that records each request.
class FakeServer {
  final requests = <Uri>[];

  /// Two pages of events: the first page has `next`, the second doesn't.
  Map<String, dynamic> event(int id, String type, String cat, {bool photo = false, String? notes}) => {
        'id': id,
        'type': type,
        'type_name': type == 'cough' ? 'Cough' : 'Litterbox',
        'cat': cat,
        'event_timestamp': DateTime.now().toUtc().subtract(Duration(hours: id)).toIso8601String(),
        'reporter': type == 'cough' ? 'Mac' : 'pi',
        'notes': notes,
        'picture': photo
            ? {'id': id, 'source': 'litterbox', 'status': 'labeled', 'best_guess': cat,
               'confidence': 0.93, 'labeled_by': 'Ashley', 'has_image': true}
            : null,
      };

  late final client = MockClient((req) async {
    if (req.url.path == '/event_types') {
      requests.add(req.url);
      return _json([
        {'type': 'litterbox', 'name': 'Litterbox'},
        {'type': 'cough', 'name': 'Cough'},
      ]);
    }
    if (req.url.path == '/events') {
      requests.add(req.url);
      final q = req.url.queryParameters;
      if (q['before'] != null) {
        return _json({'events': [event(9, 'litterbox', 'Shinx', photo: true)], 'next': null});
      }
      final from = DateTime.parse(q['from']!), to = DateTime.parse(q['to']!);
      final days = to.difference(from).inDays + 1;
      final cats = q['cat'] == null ? ['Litten', 'Shinx'] : [q['cat']!];
      final types = q['type'] == null ? ['litterbox', 'cough'] : [q['type']!];
      final buckets = days == 1
          ? [for (var h = 0; h < 24; h++) '${q['from']}T${h.toString().padLeft(2, '0')}:00-07:00']
          : [for (var i = 0; i < days; i++) day(from.add(Duration(days: i)))];
      return _json({
        'events': [
          event(1, 'cough', 'Shinx', notes: 'after breakfast'),
          event(2, 'litterbox', 'Litten', photo: true),
        ],
        'next': '123_2',
        'range': {'from': q['from'], 'to': q['to'], 'days': days, 'time_zone': 'America/Edmonton'},
        'totals': {
          'all': 3,
          'by_cat': {for (final c in cats) c: c == 'Litten' ? 2 : 1},
          'by_type': {
            for (final t in types) t: {for (final c in cats) c: t == 'cough' ? 1 : 2}
          },
        },
        'chart': {
          'kind': days > 31 ? 'line' : 'bar',
          'bucket': days == 1 ? 'hour' : 'day',
          'buckets': buckets,
          'series': {
            for (final t in types)
              t: {for (final c in cats) c: [for (var i = 0; i < buckets.length; i++) i == 0 ? 1 : 0]}
          },
        },
      });
    }
    return http.Response('{"detail":"Not Found"}', 404);
  });

  List<Uri> get eventsCalls => requests.where((u) => u.path == '/events').toList();

  static http.Response _json(Object body) =>
      http.Response(jsonEncode(body), 200, headers: {'content-type': 'application/json'});
}

Future<ServerStore> _store() async {
  SharedPreferences.setMockInitialValues({
    'servers': jsonEncode([
      {'id': '1', 'name': 'Home', 'address': '192.168.1.116:8000'}
    ]),
    'selected_server': '1',
    'who_am_i': 'Mac',
  });
  FlutterSecureStorage.setMockInitialValues({'apikey_1': 'test'});
  await WhoAmI.load();
  return ServerStore.load();
}

Future<void> _pump(WidgetTester tester, ServerStore store) async {
  tester.view.physicalSize = const Size(412, 915);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: EventsScreen(store: store, server: store.selected!)),
  ));
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

void main() {
  WidgetController.hitTestWarningShouldBeFatal = true;

  group('date presets', () {
    final now = DateTime(2026, 11, 13, 21, 30);
    test('presets end today and count back from it', () {
      expect(rangeFor(DateRangeChoice.today, now, null), (DateTime(2026, 11, 13), DateTime(2026, 11, 13)));
      expect(rangeFor(DateRangeChoice.last7, now, null), (DateTime(2026, 11, 7), DateTime(2026, 11, 13)));
      expect(rangeFor(DateRangeChoice.last30, now, null), (DateTime(2026, 10, 15), DateTime(2026, 11, 13)));
      expect(rangeFor(DateRangeChoice.thisMonth, now, null), (DateTime(2026, 11, 1), DateTime(2026, 11, 13)));
    });
    test('custom uses the picked range', () {
      final picked = DateTimeRange(start: DateTime(2026, 8, 15), end: DateTime(2026, 11, 13));
      expect(rangeFor(DateRangeChoice.custom, now, picked), (DateTime(2026, 8, 15), DateTime(2026, 11, 13)));
    });
  });

  test('chart labels for hours and days', () {
    final hours = EventChart.fromJson({
      'kind': 'bar', 'bucket': 'hour',
      'buckets': ['2026-11-13T00:00-07:00', '2026-11-13T13:00-07:00'],
      'series': <String, dynamic>{},
    });
    expect(axisLabel(hours, 0), '12a');
    expect(axisLabel(hours, 1), '1p');
    expect(bucketTitle(hours, 1), 'Fri, Nov 13 · 1 PM');
    final days = EventChart.fromJson({
      'kind': 'bar', 'bucket': 'day', 'buckets': ['2026-11-11', '2026-11-12'],
      'series': <String, dynamic>{},
    });
    expect(axisLabel(days, 0), 'Wed');
    expect(bucketTitle(days, 0), 'Wed, Nov 11');
  });

  testWidgets('opens on the last 7 days, both cats, all events', (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      await _pump(tester, await _store());
      final q = server.eventsCalls.single.queryParameters;
      expect(q['from'], day(today().subtract(const Duration(days: 6))));
      expect(q['to'], day(today()));
      expect(q.containsKey('cat'), isFalse);
      expect(q.containsKey('type'), isFalse);

      expect(find.text('3 events'), findsOneWidget);
      expect(find.text('Litten 2 · Shinx 1'), findsOneWidget);
      // The first chart page is Litterbox, with its own totals.
      expect(find.text('Litterbox · Litten'), findsOneWidget); // the photo event's card
      expect(find.text('Litten 2 · Shinx 2'), findsOneWidget);
      expect(find.text('“after breakfast”', skipOffstage: false), findsOneWidget);
      // The cough has no photo: its cat's art, dimmed, with "No photo".
      expect(find.text('No photo', skipOffstage: false), findsWidgets);
    }, () => server.client);
  });

  testWidgets('cat and event filters send one value, Both and All send none', (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      await _pump(tester, await _store());
      await _tap(tester, find.text('Litten').first);
      expect(server.eventsCalls.last.queryParameters['cat'], 'Litten');
      await _tap(tester, find.text('Cough').first);
      expect(server.eventsCalls.last.queryParameters['type'], 'cough');
      expect(server.eventsCalls.last.queryParameters['cat'], 'Litten');
      await _tap(tester, find.text('Both'));
      await _tap(tester, find.text('All'));
      expect(server.eventsCalls.last.queryParameters.containsKey('cat'), isFalse);
      expect(server.eventsCalls.last.queryParameters.containsKey('type'), isFalse);
    }, () => server.client);
  });

  testWidgets('swiping the chart changes only the chart', (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      await _pump(tester, await _store());
      final calls = server.eventsCalls.length;
      expect(find.text('Litten 2 · Shinx 2'), findsOneWidget); // litterbox totals
      await tester.drag(find.byType(PageView), const Offset(-380, 0));
      await tester.pumpAndSettle();
      expect(find.text('Litten 1 · Shinx 1'), findsOneWidget); // cough totals
      expect(server.eventsCalls.length, calls); // no new request
      // the list is unchanged: both the cough and the litterbox event are still there
      expect(find.text('Cough · Shinx', skipOffstage: false), findsOneWidget);
      expect(find.text('Litterbox · Litten', skipOffstage: false), findsOneWidget);
    }, () => server.client);
  });

  testWidgets('the Dates dropdown sends each preset range', (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      await _pump(tester, await _store());
      await _tap(tester, find.text('Last 7 days'));
      await _tap(tester, find.text('Last 30 days'));
      expect(server.eventsCalls.last.queryParameters['from'], day(today().subtract(const Duration(days: 29))));
      await _tap(tester, find.text('Last 30 days'));
      await _tap(tester, find.text('Today'));
      expect(server.eventsCalls.last.queryParameters['from'], day(today()));
      expect(server.eventsCalls.last.queryParameters['to'], day(today()));
      // Today is counted per hour.
      expect(find.text('Tap the chart to see an hour'), findsOneWidget);
    }, () => server.client);
  });

  testWidgets('Load more asks for the next page and adds it to the list', (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      await _pump(tester, await _store());
      await _tap(tester, find.text('Load more'));
      expect(server.eventsCalls.last.queryParameters['before'], '123_2');
      expect(find.text('Litterbox · Shinx', skipOffstage: false), findsOneWidget);
      expect(find.text('Load more', skipOffstage: false), findsNothing); // that was the last page
    }, () => server.client);
  });

  testWidgets('Add cough opens the cough form', (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      await _pump(tester, await _store());
      await _tap(tester, find.text('Add cough'));
      expect(find.text('Who coughed?'), findsOneWidget);
    }, () => server.client);
  });
}
