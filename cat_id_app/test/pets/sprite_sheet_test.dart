import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:cat_id_app/pets/pet_settings.dart';
import 'package:cat_id_app/pets/sprite_sheet.dart';
import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';

const walk = AnimInfo(frameWidth: 32, frameHeight: 40, frames: 5, rows: 8, durations: [6, 4, 4, 4, 6]);

/// Width and height from a PNG's header.
(int, int) pngSize(File f) {
  final b = ByteData.sublistView(f.readAsBytesSync());
  return (b.getUint32(16), b.getUint32(20));
}

void main() {
  test('frame timing (Litten walk: 6,4,4,4,6 ticks)', () {
    expect(walk.totalTicks, 24);
    expect(walk.seconds, closeTo(0.4, 1e-9));
    expect(walk.frameAt(0), 0);
    expect(walk.frameAt(5.9 / 60), 0);
    expect(walk.frameAt(6 / 60), 1);
    expect(walk.frameAt(0.399), 4);
    expect(walk.frameAt(0.4), 0, reason: 'loops');
    expect(walk.frameAt(0.4, loop: false), 4, reason: 'holds the last frame');
    expect(walk.frameAt(10, loop: false), 4);
  });

  test('source rectangles: frames across, directions down', () {
    expect(walk.source(0, SheetRow.viewer), const Rect.fromLTWH(0, 0, 32, 40));
    expect(walk.source(2, SheetRow.right), const Rect.fromLTWH(64, 80, 32, 40));
    expect(walk.source(2, SheetRow.left), const Rect.fromLTWH(64, 240, 32, 40));
    const sleep = AnimInfo(frameWidth: 24, frameHeight: 16, frames: 2, rows: 1, durations: [30, 35]);
    expect(sleep.source(1, SheetRow.left), const Rect.fromLTWH(24, 0, 24, 16),
        reason: 'one-row sheets ignore the direction');
  });

  test('every copied sheet matches its anim.json', () {
    for (final cat in PetSettings.cats) {
      for (final shiny in [false, true]) {
        final dir = CatSprites.folder(cat, shiny);
        final json = jsonDecode(File('$dir/anim.json').readAsStringSync()) as Map<String, dynamic>;
        expect(json.keys, containsAll(['Walk', 'Idle', 'Sleep', 'Hop', 'Nod']), reason: dir);
        for (final e in json.entries) {
          final a = AnimInfo.fromJson(e.value as Map<String, dynamic>);
          final (w, h) = pngSize(File('$dir/${e.key}.png'));
          expect(w, a.frames * a.frameWidth, reason: '$dir/${e.key}.png width');
          expect(h, a.rows * a.frameHeight, reason: '$dir/${e.key}.png height');
          expect(a.durations.length, a.frames, reason: '$dir/${e.key} durations');
          expect(a.rows == 8 || a.rows == 1, isTrue, reason: '$dir/${e.key} rows');
        }
      }
    }
  });

  testWidgets('every sprite set loads from the app bundle', (tester) async {
    await tester.runAsync(() async {
      for (final cat in PetSettings.cats) {
        for (final shiny in [false, true]) {
          final s = await CatSprites.load(cat, shiny);
          expect(s.images.keys, containsAll(['Walk', 'Idle', 'Sleep', 'Hop', 'Nod']));
          final w = s.anims['Walk']!;
          expect(s.images['Walk']!.width, w.frames * w.frameWidth);
          s.dispose();
        }
      }
    });
  });
}
