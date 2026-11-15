import 'dart:convert';
import 'dart:ui' as ui;

import 'package:flutter/services.dart';

/// Sprite sheets from PMD SpriteCollab (copied by tool/fetch_sprites.py).
///
/// Each sheet has the frames of one animation going across and one row per facing
/// direction. Sheets with a single row (Sleep) look the same from every side.
class SheetRow {
  static const viewer = 0;
  static const right = 2;
  static const left = 6;
}

/// Frame durations in the sheets are in ticks of 1/60 s (the games' frame rate).
const double kTicksPerSecond = 60;

/// In every sheet the cat's position is the centre of the frame, and its feet are this many
/// sprite pixels below the centre (true for Walk, Idle, Sleep, Hop and Nod of both cats).
/// A hop moves the cat up inside its (taller) frame, so drawing every frame centred on the
/// same point keeps the feet on the floor and makes the jump show.
const double kFeetBelowCentre = 7;

/// The size and timing of one animation (one entry of anim.json).
class AnimInfo {
  const AnimInfo({
    required this.frameWidth,
    required this.frameHeight,
    required this.frames,
    required this.rows,
    required this.durations,
  });

  factory AnimInfo.fromJson(Map<String, dynamic> j) => AnimInfo(
        frameWidth: j['frameWidth'] as int,
        frameHeight: j['frameHeight'] as int,
        frames: j['frames'] as int,
        rows: j['rows'] as int,
        durations: [for (final d in j['durations'] as List) d as int],
      );

  final int frameWidth;
  final int frameHeight;
  final int frames;
  final int rows;

  /// How long each frame shows, in ticks.
  final List<int> durations;

  int get totalTicks => durations.fold(0, (a, b) => a + b);

  /// One play of the animation, in seconds.
  double get seconds => totalTicks / kTicksPerSecond;

  /// The frame to show [elapsed] seconds in. Loops, unless [loop] is false: then it stays on
  /// the last frame.
  int frameAt(double elapsed, {bool loop = true}) {
    var tick = (elapsed * kTicksPerSecond).floor();
    if (tick < 0) tick = 0;
    final total = totalTicks;
    if (total <= 0) return 0;
    if (loop) {
      tick %= total;
    } else if (tick >= total) {
      return durations.length - 1;
    }
    for (var i = 0; i < durations.length; i++) {
      if (tick < durations[i]) return i;
      tick -= durations[i];
    }
    return durations.length - 1;
  }

  /// Where [frame] facing [row] (a [SheetRow]) sits in the sheet image.
  ui.Rect source(int frame, int row) {
    final r = rows == 1 ? 0 : row;
    return ui.Rect.fromLTWH(
      (frame * frameWidth).toDouble(),
      (r * frameHeight).toDouble(),
      frameWidth.toDouble(),
      frameHeight.toDouble(),
    );
  }
}

/// All the animations of one cat in one colour.
class CatSprites {
  CatSprites(this.anims, this.images);

  final Map<String, AnimInfo> anims;
  final Map<String, ui.Image> images;

  /// The asset folder, e.g. assets/sprites/shinx/shiny.
  static String folder(String cat, bool shiny) =>
      'assets/sprites/${cat.toLowerCase()}/${shiny ? 'shiny' : 'default'}';

  static Future<CatSprites> load(String cat, bool shiny, {AssetBundle? bundle}) async {
    final b = bundle ?? rootBundle;
    final dir = folder(cat, shiny);
    final json = jsonDecode(await b.loadString('$dir/anim.json')) as Map<String, dynamic>;
    final anims = {
      for (final e in json.entries) e.key: AnimInfo.fromJson(e.value as Map<String, dynamic>),
    };
    final images = <String, ui.Image>{};
    for (final name in anims.keys) {
      final data = await b.load('$dir/$name.png');
      final codec = await ui.instantiateImageCodec(
          data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes));
      images[name] = (await codec.getNextFrame()).image;
      codec.dispose();
    }
    return CatSprites(anims, images);
  }

  void dispose() {
    for (final image in images.values) {
      image.dispose();
    }
  }
}
