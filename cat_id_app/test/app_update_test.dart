import 'dart:convert';
import 'dart:io';

import 'package:cat_id_app/api.dart';
import 'package:cat_id_app/app_update.dart';
import 'package:cat_id_app/screens/health_screen.dart';
import 'package:cat_id_app/screens/settings_screen.dart';
import 'package:cat_id_app/server_store.dart';
import 'package:cat_id_app/who_am_i.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

AppVersion v(String s) => AppVersion.tryParse(s)!;

Map<String, dynamic> info(String version, {String notes = 'Fixed things', int size = 6}) =>
    {'version': version, 'notes': notes, 'sha256': 'ab' * 32, 'size': size};

AppUpdates updates({Map<String, dynamic>? release, Map<String, dynamic>? prerelease}) =>
    AppUpdates.fromJson({'release': release, 'prerelease': prerelease});

/// Stands in for the Kotlin installer.
class FakeInstaller implements ApkInstaller {
  FakeInstaller(this.dir, {this.outcome = const InstallOutcome(InstallStatus.cancelled)});

  final String dir;
  final InstallOutcome outcome;
  bool allowed = true;
  final installs = <(String, String, List<int>)>[];

  @override
  Future<String> downloadDir() async => dir;

  @override
  Future<bool> canInstall() async => allowed;

  @override
  Future<void> openInstallSettings() async {}

  @override
  Future<InstallOutcome> install(String path, String sha256) async {
    installs.add((path, sha256, File(path).readAsBytesSync()));
    return outcome;
  }
}

/// A server with /health and /app_update ([appUpdate] null = an older server: 404).
MockClient fakeServer({Map<String, dynamic>? appUpdate, List<int> apk = const [1, 2, 3, 4, 5, 6]}) =>
    MockClient((req) async {
      final json = {'content-type': 'application/json'};
      switch (req.url.path) {
        case '/health':
          return http.Response(
              jsonEncode({'model_loaded': true, 'version': 'v1.4.4', 'commit': 'abcdef1234'}), 200,
              headers: json);
        case '/app_update':
          if (appUpdate == null) return http.Response('{"detail":"Not Found"}', 404, headers: json);
          expect(req.headers['X-API-Key'], 'test');
          return http.Response(jsonEncode(appUpdate), 200, headers: json);
        case '/app_update/release/apk' || '/app_update/prerelease/apk':
          expect(req.headers['X-API-Key'], 'test');
          return http.Response.bytes(apk, 200);
      }
      return http.Response('{"detail":"Not Found"}', 404, headers: json);
    });

Future<ServerStore> _store() async {
  SharedPreferences.setMockInitialValues({
    'servers': jsonEncode([
      {'id': '1', 'name': 'Home', 'address': '192.168.1.116:8000'},
      {'id': '2', 'name': 'Away', 'address': 'https://cat-id.example.ts.net'},
    ]),
    'selected_server': '1',
    'who_am_i': 'Ashley',
  });
  FlutterSecureStorage.setMockInitialValues({'apikey_1': 'test', 'apikey_2': 'test'});
  await WhoAmI.load();
  return ServerStore.load();
}

Future<void> _pumpHealth(WidgetTester tester, ServerStore store) async {
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: HealthScreen(server: store.selected!, store: store, onOpenLabel: () {}),
    ),
  ));
  await tester.pumpAndSettle();
}

/// The download writes a real file, which the test's fake clock doesn't wait for: let
/// real time pass between frames until it's done.
Future<void> _settleIo(WidgetTester tester) async {
  for (var i = 0; i < 20; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pump();
  }
  await tester.pumpAndSettle();
}

final _updateButton = find.widgetWithText(FilledButton, 'Update to v1.4.4');

void main() {
  late Directory tmp;
  setUp(() {
    tmp = Directory.systemTemp.createTempSync('cat_id_update_test');
    installedAppVersion = 'v1.4.3';
  });
  tearDown(() {
    tmp.deleteSync(recursive: true);
    installedAppVersion = '';
  });

  group('versions', () {
    test('order like semantic versions', () {
      expect(v('v1.4.4') > v('v1.4.3'), isTrue);
      expect(v('1.10.0') > v('v1.9.9'), isTrue);
      expect(v('v2.0.0') > v('v1.99.99'), isTrue);
      expect(v('v1.5.0') > v('v1.5.0-test'), isTrue);
      expect(v('v1.5.0-test') > v('v1.4.9'), isTrue);
      expect(v('v1.5.0-beta.2') > v('v1.5.0-beta.1'), isTrue);
      expect(v('v1.5.0-beta.10') > v('v1.5.0-beta.9'), isTrue);
      expect(v('v1.5.0-beta') > v('v1.5.0-alpha'), isTrue);
      expect(v('v1.5.0-rc.1') > v('v1.5.0-rc'), isTrue);
      expect(v('v1.4.3').compareTo(v('1.4.3')), 0);
    });
    test("dev builds and junk aren't versions", () {
      for (final s in ['', 'dev', '1.4', 'v1.4.x', '1.0.0+1']) {
        expect(AppVersion.tryParse(s), isNull, reason: s);
      }
    });
    test('an empty CAT_ID_VERSION is a dev build', () {
      installedAppVersion = '';
      expect(isDevBuild, isTrue);
      installedAppVersion = 'v1.4.3';
      expect(isDevBuild, isFalse);
    });
  });

  group('what the Health tab offers', () {
    test('a newer full release', () {
      expect(healthUpdateOffer(updates(release: info('v1.4.4')))?.version, 'v1.4.4');
    });
    test('nothing when the same, older or missing', () {
      expect(healthUpdateOffer(updates(release: info('v1.4.3'))), isNull);
      expect(healthUpdateOffer(updates(release: info('v1.4.2'))), isNull);
      expect(healthUpdateOffer(updates()), isNull);
    });
    test('never a prerelease', () {
      expect(healthUpdateOffer(updates(prerelease: info('v1.5.0-test'))), isNull);
    });
    test('never on a dev build', () {
      expect(healthUpdateOffer(updates(release: info('v9.0.0')), installed: ''), isNull);
    });
    test('a phone on a prerelease is offered its full release', () {
      expect(healthUpdateOffer(updates(release: info('v1.5.0')), installed: 'v1.5.0-test')?.version,
          'v1.5.0');
    });
  });

  group('what Settings offers as a prerelease', () {
    test('a newer prerelease', () {
      expect(prereleaseOffer(updates(prerelease: info('v1.5.0-test')))?.version, 'v1.5.0-test');
    });
    test('not one older than what is installed', () {
      expect(prereleaseOffer(updates(prerelease: info('v1.4.3-test'))), isNull);
    });
    test('not one older than the full release', () {
      expect(
          prereleaseOffer(updates(release: info('v1.5.0'), prerelease: info('v1.5.0-test'))), isNull);
      expect(prereleaseOffer(updates(release: info('v1.4.4'), prerelease: info('v1.5.0-test')))?.version,
          'v1.5.0-test');
    });
    test('any prerelease on a dev build', () {
      expect(prereleaseOffer(updates(prerelease: info('v1.0.0-x')), installed: '')?.version, 'v1.0.0-x');
    });
  });

  test('install results are worded for people', () {
    expect(outcomeFrom('installed', null).status, InstallStatus.installed);
    expect(outcomeFrom('cancelled', null).status, InstallStatus.cancelled);
    expect(outcomeFrom('checksum', null).message, contains("checksum doesn't match"));
    expect(outcomeFrom('conflict', 'INSTALL_FAILED_UPDATE_INCOMPATIBLE').message,
        contains('signed with a different key'));
    expect(outcomeFrom('something new', 'x').message, 'The update failed (x).');
  });

  group('Health tab Update button', () {
    testWidgets('shows at the top when the server has a newer release', (tester) async {
      final store = await _store();
      await http.runWithClient(() async {
        await _pumpHealth(tester, store);
        expect(_updateButton, findsOneWidget);
        final top = tester.getTopLeft(_updateButton).dy;
        expect(top, lessThan(tester.getTopLeft(find.text('Model loaded')).dy));
      }, () => fakeServer(appUpdate: {'release': info('v1.4.4'), 'prerelease': null}));
    });

    for (final (name, appUpdate, installed) in [
      ('the same version', {'release': info('v1.4.3'), 'prerelease': null}, 'v1.4.3'),
      ('an older version', {'release': info('v1.4.2'), 'prerelease': null}, 'v1.4.3'),
      ('only a newer prerelease', {'release': null, 'prerelease': info('v1.5.0-test')}, 'v1.4.3'),
      ('nothing deployed', {'release': null, 'prerelease': null}, 'v1.4.3'),
      ('a dev build', {'release': info('v1.4.4'), 'prerelease': null}, ''),
      ('an older server without /app_update', null, 'v1.4.3'),
    ]) {
      testWidgets('hidden for $name', (tester) async {
        installedAppVersion = installed;
        final store = await _store();
        await http.runWithClient(() async {
          await _pumpHealth(tester, store);
          expect(find.textContaining('Update to'), findsNothing);
          expect(find.text('Model loaded'), findsOneWidget);
        }, () => fakeServer(appUpdate: appUpdate));
      });
    }

    testWidgets('hidden when the server is unreachable', (tester) async {
      final store = await _store();
      await http.runWithClient(() async {
        await _pumpHealth(tester, store);
        expect(find.textContaining('Update to'), findsNothing);
      }, () => MockClient((_) async => throw const SocketException('down')));
    });

    testWidgets('Update shows what is new, downloads, checks size and installs', (tester) async {
      final store = await _store();
      final installer = FakeInstaller(tmp.path);
      ApkInstaller.instance = installer;
      addTearDown(() => ApkInstaller.instance = const AndroidApkInstaller());
      await http.runWithClient(() async {
        await _pumpHealth(tester, store);
        await tester.tap(_updateButton);
        await tester.pumpAndSettle();
        expect(find.text("What's new"), findsOneWidget);
        expect(find.text('Fixed things'), findsOneWidget);

        // Not now: nothing happens.
        await tester.tap(find.text('Not now'));
        await tester.pumpAndSettle();
        expect(installer.installs, isEmpty);

        await tester.tap(_updateButton);
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(FilledButton, 'Update'));
        await _settleIo(tester);
        expect(installer.installs, hasLength(1));
        final (path, sha, bytes) = installer.installs.single;
        expect(path, '${tmp.path}/cat-id-update.apk');
        expect(sha, 'ab' * 32);
        expect(bytes, [1, 2, 3, 4, 5, 6]);
        expect(find.text('Update cancelled.'), findsOneWidget); // the fake's outcome
      }, () => fakeServer(appUpdate: {'release': info('v1.4.4'), 'prerelease': null}));
    });

    testWidgets('a short download is not installed', (tester) async {
      final store = await _store();
      final installer = FakeInstaller(tmp.path);
      ApkInstaller.instance = installer;
      addTearDown(() => ApkInstaller.instance = const AndroidApkInstaller());
      await http.runWithClient(() async {
        await _pumpHealth(tester, store);
        await tester.tap(_updateButton);
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(FilledButton, 'Update'));
        await _settleIo(tester);
        expect(installer.installs, isEmpty);
        expect(find.text('The download was incomplete. Try again.'), findsOneWidget);
        expect(File('${tmp.path}/cat-id-update.apk').existsSync(), isFalse);
      }, () => fakeServer(
          appUpdate: {'release': info('v1.4.4'), 'prerelease': null}, apk: [1, 2, 3]));
    });

    testWidgets('asks to allow installs first, and stops if not allowed', (tester) async {
      final store = await _store();
      final installer = FakeInstaller(tmp.path)..allowed = false;
      ApkInstaller.instance = installer;
      addTearDown(() => ApkInstaller.instance = const AndroidApkInstaller());
      await http.runWithClient(() async {
        await _pumpHealth(tester, store);
        await tester.tap(_updateButton);
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(FilledButton, 'Update'));
        await tester.pumpAndSettle();
        expect(find.text('Allow Kitten Dex to install updates'), findsOneWidget);
        await tester.tap(find.text('Cancel'));
        await tester.pumpAndSettle();
        expect(installer.installs, isEmpty);
      }, () => fakeServer(appUpdate: {'release': info('v1.4.4'), 'prerelease': null}));
    });
  });

  group('Settings page', () {
    Future<void> pumpSettings(WidgetTester tester, ServerStore store) async {
      tester.view.physicalSize = const Size(412, 2400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(home: SettingsScreen(store: store)));
      await tester.pumpAndSettle();
    }

    testWidgets('shows the versions and that it is up to date', (tester) async {
      final store = await _store();
      await http.runWithClient(() async {
        await pumpSettings(tester, store);
        expect(find.text('Kitten Dex v1.4.3'), findsOneWidget);
        expect(find.text('Server v1.4.4'), findsOneWidget);
        expect(find.text('Up to date'), findsOneWidget);
        expect(find.text('Newest release on the server: v1.4.3'), findsOneWidget);
      }, () => fakeServer(appUpdate: {'release': info('v1.4.3'), 'prerelease': info('v1.5.0-test')}));
    });

    testWidgets('a dev build says so and offers the latest release', (tester) async {
      installedAppVersion = '';
      final store = await _store();
      await http.runWithClient(() async {
        await pumpSettings(tester, store);
        expect(find.text('This is a dev build'), findsOneWidget);
        expect(find.text('Install latest release'), findsOneWidget);
        await tester.tap(find.widgetWithText(FilledButton, 'Install'));
        await tester.pumpAndSettle();
        expect(find.text('Install v1.4.4'), findsOneWidget); // the what's-new dialog
      }, () => fakeServer(appUpdate: {'release': info('v1.4.4'), 'prerelease': null}));
    });

    testWidgets('prereleases show only once turned on, and the choice is saved', (tester) async {
      final store = await _store();
      await http.runWithClient(() async {
        await pumpSettings(tester, store);
        expect(find.text('Prerelease v1.5.0-test available'), findsNothing);
        await tester.tap(find.text('Show prereleases'));
        await tester.pumpAndSettle();
        expect(find.text('Prerelease v1.5.0-test available'), findsOneWidget);
        expect(await UpdatePrefs.showPrereleases(), isTrue);
      }, () => fakeServer(appUpdate: {'release': info('v1.4.3'), 'prerelease': info('v1.5.0-test')}));
    });

    testWidgets('an older server says it has no app updates', (tester) async {
      final store = await _store();
      await http.runWithClient(() async {
        await pumpSettings(tester, store);
        expect(find.text("This server doesn't have app updates yet. Update the server."),
            findsOneWidget);
      }, () => fakeServer());
    });

    testWidgets('Who am I and the servers are the same settings as elsewhere', (tester) async {
      final store = await _store();
      await http.runWithClient(() async {
        await pumpSettings(tester, store);
        await tester.tap(find.text('Mac'));
        await tester.pumpAndSettle();
        expect(WhoAmI.current, 'Mac');
        expect((await SharedPreferences.getInstance()).getString('who_am_i'), 'Mac');

        await tester.tap(find.text('Away'));
        await tester.pumpAndSettle();
        expect(store.selected!.id, '2');
        expect(find.text('Manage servers'), findsOneWidget);
      }, () => fakeServer(appUpdate: {'release': null, 'prerelease': null}));
    });
  });
}
