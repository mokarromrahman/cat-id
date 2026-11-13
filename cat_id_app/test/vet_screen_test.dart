import 'dart:convert';

import 'package:cat_id_app/screens/home_screen.dart';
import 'package:cat_id_app/screens/vet_screen.dart';
import 'package:cat_id_app/server_store.dart';
import 'package:cat_id_app/who_am_i.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A fake server for the /vet_visit routes that records what the app sends.
class FakeServer {
  final requests = <http.Request>[];
  final visits = <Map<String, dynamic>>[];

  late final client = MockClient((req) async {
    requests.add(req);
    if (req.method == 'GET' && req.url.path == '/vet_visit') {
      return _json({'visits': visits});
    }
    if (req.method == 'POST' && req.url.path == '/vet_visit') {
      final body = jsonDecode(req.body) as Map<String, dynamic>;
      final saved = [
        for (final v in body['visits'] as List)
          {
            ...v as Map<String, dynamic>,
            'id': visits.length + 1,
            'clinic': (v['clinic'] as String?)?.isNotEmpty == true ? v['clinic'] : 'unknown',
            'reporter': body['user'],
            'modified_by': body['user'],
            'deleted_on': null,
          }
      ];
      visits.addAll(saved);
      return _json({'visits': saved});
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

Future<void> _pumpVet(WidgetTester tester, ServerStore store) async {
  // A phone-shaped screen (logical 412 x 915), so the form's buttons fit like on a phone.
  tester.view.physicalSize = const Size(412, 915);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(body: VetScreen(store: store, server: store.selected!)),
  ));
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

String _today() {
  final d = DateTime.now();
  return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}

void main() {
  // A tap that misses its widget fails the test instead of only printing a warning.
  WidgetController.hitTestWarningShouldBeFatal = true;

  test('tab order: Events replaced Cough, Vet comes after it', () {
    expect(kTabOrder, [AppTab.health, AppTab.identify, AppTab.events, AppTab.vet, AppTab.label]);
  });

  testWidgets('"Both" saves one visit per cat in a single request', (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      final store = await _store();
      await _pumpVet(tester, store);
      // The list is below the form, so look past the visible part of the screen too.
      expect(find.text('No visits yet. Add the first one above.', skipOffstage: false),
          findsOneWidget);

      await _tap(tester, find.text('Both'));
      // Two sets of per-cat fields now: reasons differ per cat.
      expect(find.text('checkup'), findsNWidgets(2));
      await _tap(tester, find.text('checkup').first);
      await _tap(tester, find.text('shots').first);
      await _tap(tester, find.text('checkup').last);
      await tester.enterText(find.widgetWithText(TextField, 'Weight').first, '4.35');
      await tester.enterText(find.widgetWithText(TextField, 'Cost').last, '60');
      await _tap(tester, find.text('Save 2 visits'));

      final posts = server.requests.where((r) => r.method == 'POST').toList();
      expect(posts, hasLength(1));
      final body = jsonDecode(posts.single.body) as Map<String, dynamic>;
      expect(body['user'], 'Ashley');
      final visits = body['visits'] as List;
      expect(visits, hasLength(2));
      expect(visits[0]['cat'], 'Litten');
      expect(visits[1]['cat'], 'Shinx');
      expect(visits[0]['reason'], ['checkup', 'shots']);
      expect(visits[1]['reason'], ['checkup']);
      expect(visits[0]['weight_kg'], '4.35');
      expect(visits[1]['weight_kg'], isNull);
      expect(visits[1]['cost'], '60');
      for (final v in visits) {
        expect(v['clinic'], kDefaultClinic);
        expect(v['visit_date'], _today());
        expect(v['appointment_time'], isNull);
      }
      expect(posts.single.headers['content-type'], contains('application/json'));
      expect(posts.single.headers['x-api-key'] ?? posts.single.headers['X-API-Key'], 'test');

      // The list reloads and shows both saved visits.
      expect(server.requests.where((r) => r.method == 'GET'), hasLength(2));
      await tester.scrollUntilVisible(find.textContaining('Shinx · '), 300,
          scrollable: find.byType(Scrollable).first); // the tab's list, not a text field's
      expect(find.textContaining('Litten · ', skipOffstage: false), findsOneWidget);
      expect(find.textContaining('Shinx · '), findsOneWidget);
      expect(find.textContaining('Added by Ashley', skipOffstage: false), findsNWidgets(2));
    }, () => server.client);
  });

  testWidgets('a visit needs at least one reason, and nothing is sent without one',
      (tester) async {
    final server = FakeServer();
    await http.runWithClient(() async {
      final store = await _store();
      await _pumpVet(tester, store);
      await _tap(tester, find.text('No cat'));
      expect(find.text('For pickups or anything not for one cat.'), findsOneWidget);
      await _tap(tester, find.text('Save visit'));
      expect(find.text('Pick at least one reason.'), findsOneWidget);
      expect(server.requests.where((r) => r.method == 'POST'), isEmpty);

      await _tap(tester, find.text('food pickup'));
      await _tap(tester, find.text('Save visit'));
      final body = jsonDecode(server.requests.lastWhere((r) => r.method == 'POST').body);
      expect(body['visits'].single['cat'], isNull);
      expect(body['visits'].single['reason'], ['food pickup']);
    }, () => server.client);
  });
}
