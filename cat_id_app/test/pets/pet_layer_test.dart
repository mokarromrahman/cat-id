import 'dart:math';

import 'package:cat_id_app/pets/pet.dart';
import 'package:cat_id_app/pets/pet_events.dart';
import 'package:cat_id_app/pets/pet_layer.dart';
import 'package:cat_id_app/pets/pet_painter.dart';
import 'package:cat_id_app/pets/pet_settings.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const layerHeight = PetLayer.floorHeight + PetLayer.headroom;

/// A button sitting under the cat strip, with the cat layer on top (like HomeScreen).
Widget harness(VoidCallback onButton) => MaterialApp(
      home: Scaffold(
        body: Stack(
          children: [
            Positioned(
              left: 0,
              right: 0,
              bottom: 20,
              child: Center(
                child: ElevatedButton(onPressed: onButton, child: const Text('Under the cats')),
              ),
            ),
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              height: layerHeight,
              child: PetLayer(random: Random(7), loadSprites: false),
            ),
          ],
        ),
      ),
    );

PetLayerState layer(WidgetTester tester) => tester.state<PetLayerState>(find.byType(PetLayer));

Pet pet(WidgetTester tester, String cat) => layer(tester).pets.firstWhere((p) => p.cat == cat);

/// The middle of [cat]'s body, in screen coordinates.
Offset bodyCentre(WidgetTester tester, String cat) {
  final box = tester.getRect(find.byType(PetLayer));
  return box.topLeft + bodyRect(pet(tester, cat), box.size).center;
}

/// Runs the app for [seconds] in 100 ms frames (one long pump would be capped at 0.1 s).
Future<void> runFor(WidgetTester tester, double seconds) async {
  for (var i = 0; i < (seconds * 10).round(); i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

Future<void> pumpCats(WidgetTester tester, VoidCallback onButton) async {
  await tester.pumpWidget(harness(onButton));
  await tester.pump();
  // Button is in the middle (x 400 on the 800 px test screen): keep the cats away from it.
  layer(tester).debugPlace('Shinx', 100);
  layer(tester).debugPlace('Litten', 700);
  await tester.pump();
}

void main() {
  testWidgets('taps away from the cats reach the content underneath', (tester) async {
    var tapped = false;
    await pumpCats(tester, () => tapped = true);
    await tester.tap(find.text('Under the cats'));
    expect(tapped, isTrue);
    expect(pet(tester, 'Shinx').heartAge, isNull);
    expect(pet(tester, 'Litten').heartAge, isNull);
  });

  testWidgets('tapping a cat shows its heart and stops it', (tester) async {
    var tapped = false;
    await pumpCats(tester, () => tapped = true);
    await tester.tapAt(bodyCentre(tester, 'Shinx'));
    await tester.pump();
    expect(pet(tester, 'Shinx').state, PetState.love);
    expect(pet(tester, 'Shinx').heartAge, isNotNull);
    expect(pet(tester, 'Litten').heartAge, isNull);
    expect(tapped, isFalse);

    await runFor(tester, 1.0);
    expect(pet(tester, 'Shinx').heartAge, isNotNull);
    await runFor(tester, 1.1);
    expect(pet(tester, 'Shinx').heartAge, isNull, reason: 'the heart is gone after 2 s');
    expect(pet(tester, 'Shinx').state, PetState.idle);
  });

  testWidgets('Identify recognising Shinx makes only Shinx hop', (tester) async {
    await pumpCats(tester, () {});
    PetEvents.instance.celebrate('Shinx');
    await tester.pump();
    expect(pet(tester, 'Shinx').state, PetState.hop);
    expect(pet(tester, 'Litten').state, PetState.idle);

    PetEvents.instance.celebrate('uncertain');
    PetEvents.instance.celebrate('neither');
    await tester.pump();
    expect(pet(tester, 'Litten').state, PetState.idle);
  });

  testWidgets('after the Add event form closes, each cat reacts once, one after the other',
      (tester) async {
    await pumpCats(tester, () {});
    PetEvents.instance.afterReports([
      (cat: 'Shinx', reaction: PetReaction.nod), // cough...
      (cat: 'Litten', reaction: PetReaction.hop),
      (cat: 'Shinx', reaction: PetReaction.hop), // ...then litterbox: the hop wins
      (cat: 'uncertain', reaction: PetReaction.hop), // ignored
    ]);
    await tester.pump();
    expect(pet(tester, 'Shinx').state, PetState.idle, reason: 'waits for the form to slide away');
    await runFor(tester, 0.4); // Shinx goes at 0.3 s
    expect(pet(tester, 'Shinx').state, PetState.hop);
    expect(pet(tester, 'Litten').state, PetState.idle);
    await runFor(tester, 0.8); // Litten goes at 1.1 s
    expect(pet(tester, 'Litten').state, PetState.hop);
  });

  testWidgets('a reported cough makes the cat nod, without a heart', (tester) async {
    await pumpCats(tester, () {});
    PetEvents.instance.afterReports([(cat: 'Litten', reaction: PetReaction.nod)]);
    await runFor(tester, 0.4);
    expect(pet(tester, 'Litten').state, PetState.nod);
    expect(pet(tester, 'Litten').heartAge, isNull);
    expect(pet(tester, 'Shinx').state, PetState.idle);
  });

  testWidgets('nothing sent, nothing happens', (tester) async {
    await pumpCats(tester, () {});
    PetEvents.instance.afterReports(const []);
    await runFor(tester, 2);
    expect(pet(tester, 'Shinx').state, PetState.idle);
    expect(pet(tester, 'Litten').state, PetState.idle);
  });

  testWidgets('the cats stay on the strip as time passes', (tester) async {
    await tester.pumpWidget(harness(() {}));
    await runFor(tester, 60);
    final width = tester.getSize(find.byType(PetLayer)).width;
    for (final p in layer(tester).pets) {
      expect(p.x, inInclusiveRange(24, width - 24));
    }
  });

  group('settings', () {
    setUpAll(() async {
      SharedPreferences.setMockInitialValues({});
      await PetSettings.load(random: Random(1));
    });

    testWidgets('switching the cats off removes the strip but keeps the content', (tester) async {
      final key = GlobalKey();
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: WithPets(child: SizedBox.expand(key: key))),
      ));
      expect(find.byType(PetLayer), findsOneWidget);
      final contentState = key.currentContext;

      await PetSettings.instance.setEnabled(false);
      await tester.pump();
      expect(find.byType(PetLayer), findsNothing);
      expect(key.currentContext, same(contentState), reason: 'tabs keep their state');

      await PetSettings.instance.setEnabled(true);
      await tester.pump();
      expect(find.byType(PetLayer), findsOneWidget);
    });

    testWidgets('reduce motion hides the cats', (tester) async {
      await tester.pumpWidget(MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: child!,
        ),
        home: const Scaffold(body: WithPets(child: SizedBox.expand())),
      ));
      expect(find.byType(PetLayer), findsNothing);
    });

    test('shiny modes are saved and Auto uses the launch roll', () async {
      final s = PetSettings.instance;
      await s.setMode('Shinx', ShinyMode.shiny);
      await s.setMode('Litten', ShinyMode.normal);
      expect(s.isShiny('Shinx'), isTrue);
      expect(s.isShiny('Litten'), isFalse);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getString('pets_shiny_Shinx'), 'shiny');
      await s.setMode('Shinx', ShinyMode.auto);
      expect(s.isShiny('Shinx'), s.rolledShiny('Shinx'));
    });
  });
}
