import 'package:flutter/material.dart';

import 'pet.dart';
import 'sprite_sheet.dart';

/// Sprite pixels per logical pixel.
const double kPixelScale = 2;

/// Where the cats' feet are: this far above the bottom of the pet layer.
const double kFloorInset = 10;

/// Each cat's body inside its frame, in sprite pixels from the frame centre (measured from
/// the Walk sheets facing left and right). Used for taps, the shadow and placing the heart.
const Map<String, Rect> kBodyBox = {
  'Shinx': Rect.fromLTRB(-17, -20, 16, 6),
  'Litten': Rect.fromLTRB(-14, -16, 13, 6),
};

const Map<String, Color> kHeartColour = {
  'Litten': Color(0xFFD62828), // the label page's Litten red
  'Shinx': Color(0xFFF4C20D), // the label page's Shinx gold
};

/// A pixel heart, drawn in code (no image file).
const List<String> _heart = [
  '.XX.XX.',
  'XXXXXXX',
  'XXXXXXX',
  '.XXXXX.',
  '..XXX..',
  '...X...',
];

double floorY(Size size) => size.height - kFloorInset;

/// The point every frame is centred on.
Offset frameCentre(Pet p, Size size) =>
    Offset(p.x.roundToDouble(), (floorY(size) - kFeetBelowCentre * kPixelScale).roundToDouble());

/// The cat's body on screen while standing (not mid-hop), a little larger so it's easy to tap.
Rect bodyRect(Pet p, Size size) {
  final box = kBodyBox[p.cat] ?? const Rect.fromLTRB(-14, -16, 14, 6);
  final c = frameCentre(p, size);
  return Rect.fromLTRB(
    c.dx + box.left * kPixelScale,
    c.dy + box.top * kPixelScale,
    c.dx + box.right * kPixelScale,
    c.dy + box.bottom * kPixelScale,
  ).inflate(6);
}

typedef Pose = ({String anim, int row, double time, bool loop});

/// Which animation, facing which way, and how far into it.
Pose poseFor(Pet p, double nodSeconds) {
  final facing = p.facingRight ? SheetRow.right : SheetRow.left;
  switch (p.state) {
    case PetState.idle:
      return (anim: 'Idle', row: facing, time: p.stateTime, loop: true);
    case PetState.walkLeft:
      return (anim: 'Walk', row: SheetRow.left, time: p.stateTime, loop: true);
    case PetState.walkRight:
      return (anim: 'Walk', row: SheetRow.right, time: p.stateTime, loop: true);
    case PetState.sleep:
      return (anim: 'Sleep', row: SheetRow.viewer, time: p.stateTime, loop: true);
    case PetState.hop:
      return (anim: 'Hop', row: facing, time: p.stateTime, loop: true);
    case PetState.love:
    case PetState.nod:
      if (p.stateTime < nodSeconds) {
        return (anim: 'Nod', row: SheetRow.viewer, time: p.stateTime, loop: false);
      }
      return (anim: 'Idle', row: SheetRow.viewer, time: p.stateTime - nodSeconds, loop: true);
  }
}

/// Draws the cats, their shadows and hearts. Repaints when [repaint] ticks.
class PetPainter extends CustomPainter {
  PetPainter({
    required this.pets,
    required this.sprites,
    required this.isShiny,
    required this.hits,
    required Listenable repaint,
  }) : super(repaint: repaint);

  final List<Pet> Function() pets;

  /// Keyed by [spriteKey]. Missing entries (still loading) are skipped.
  final Map<String, CatSprites> sprites;
  final bool Function(String cat) isShiny;

  /// Whether a point is on a cat. Anywhere else, taps go through to what's underneath.
  final bool Function(Offset position) hits;

  static String spriteKey(String cat, bool shiny) => '$cat/${shiny ? 'shiny' : 'default'}';

  static final Paint _pixels = Paint()
    ..filterQuality = FilterQuality.none
    ..isAntiAlias = false;

  @override
  void paint(Canvas canvas, Size size) {
    for (final p in pets()) {
      _paintShadow(canvas, p, size);
      final s = sprites[spriteKey(p.cat, isShiny(p.cat))];
      if (s != null) _paintCat(canvas, p, size, s);
    }
    for (final p in pets()) {
      final age = p.heartAge;
      if (age != null) _paintHeart(canvas, p, size, age);
    }
  }

  void _paintShadow(Canvas canvas, Pet p, Size size) {
    final box = kBodyBox[p.cat]!;
    canvas.drawOval(
      Rect.fromCenter(
        center: Offset(p.x, floorY(size) - 1),
        width: box.width * kPixelScale * 0.6,
        height: 3 * kPixelScale,
      ),
      Paint()..color = const Color(0x40000000),
    );
  }

  void _paintCat(Canvas canvas, Pet p, Size size, CatSprites s) {
    final nod = s.anims['Nod']?.seconds ?? 0.3;
    final pose = poseFor(p, nod);
    final info = s.anims[pose.anim];
    final image = s.images[pose.anim];
    if (info == null || image == null) return;
    final frame = info.frameAt(pose.time, loop: pose.loop);
    final dst = Rect.fromCenter(
      center: frameCentre(p, size),
      width: info.frameWidth * kPixelScale,
      height: info.frameHeight * kPixelScale,
    );
    canvas.drawImageRect(image, info.source(frame, pose.row), dst, _pixels);
  }

  void _paintHeart(Canvas canvas, Pet p, Size size, double age) {
    const cell = kPixelScale * 1.5;
    final t = age / kHeartSeconds;
    final opacity = t < 0.5 ? 1.0 : (1 - t) * 2;
    final colour = kHeartColour[p.cat] ?? Colors.pink;
    final head = bodyRect(p, size).top + 6; // undo the tap margin
    final width = _heart.first.length * cell;
    final left = p.x - width / 2;
    final top = head - 4 - _heart.length * cell - 10 * t; // floats up 10 px
    final fill = Paint()..color = colour.withValues(alpha: opacity);
    final edge = Paint()..color = Colors.black.withValues(alpha: opacity * 0.6);
    for (var row = 0; row < _heart.length; row++) {
      for (var col = 0; col < _heart[row].length; col++) {
        if (_heart[row][col] != 'X') continue;
        final r = Rect.fromLTWH(left + col * cell, top + row * cell, cell, cell);
        canvas.drawRect(r.inflate(1), edge);
      }
    }
    for (var row = 0; row < _heart.length; row++) {
      for (var col = 0; col < _heart[row].length; col++) {
        if (_heart[row][col] != 'X') continue;
        canvas.drawRect(Rect.fromLTWH(left + col * cell, top + row * cell, cell, cell), fill);
      }
    }
  }

  @override
  bool? hitTest(Offset position) => hits(position);

  @override
  bool shouldRepaint(PetPainter oldDelegate) => true;
}
