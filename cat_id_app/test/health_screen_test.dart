import 'dart:convert';

import 'package:cat_id_app/screens/health_screen.dart';
import 'package:cat_id_app/server_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Map<String, dynamic> health({Object? version = _absent, Object? commit = _absent}) => {
      'model_loaded': true,
      'classes': ['Litten', 'Shinx', 'neither'],
      'photos': {'Litten': 912, 'Shinx': 703, 'neither': 42},
      'waiting_in_inbox': 3,
      if (version != _absent) 'version': version,
      if (commit != _absent) 'commit': commit,
    };

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
}
