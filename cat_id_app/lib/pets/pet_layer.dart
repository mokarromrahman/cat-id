import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import 'pet.dart';
import 'pet_events.dart';
import 'pet_painter.dart';
import 'pet_settings.dart';
import 'sprite_sheet.dart';

/// Puts [child] (the tab content) above a strip where Shinx and Litten walk, when the
/// walking cats are switched on and the phone's reduce-motion setting is off.
///
/// The tree keeps the same shape when the cats are switched on or off, so the tabs keep
/// their state.
class WithPets extends StatelessWidget {
  const WithPets({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final settings = PetSettings.current;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    if (settings == null) return _build(!reduceMotion);
    return ListenableBuilder(
      listenable: settings,
      builder: (context, _) => _build(settings.enabled && !reduceMotion),
    );
  }

  Widget _build(bool on) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Padding(
          padding: EdgeInsets.only(bottom: on ? PetLayer.floorHeight : 0),
          child: child,
        ),
        if (on)
          const Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: PetLayer.floorHeight + PetLayer.headroom,
            child: PetLayer(),
          ),
      ],
    );
  }
}

/// The walking cats. Fill a box [floorHeight] + [headroom] tall: the cats walk along the
/// bottom, and the headroom (over the tab content) leaves space for hops and hearts. Only
/// the cats themselves catch taps; taps anywhere else go through to what's underneath.
class PetLayer extends StatefulWidget {
  const PetLayer({super.key, this.random, this.loadSprites = true});

  /// Space kept free under the tab content.
  static const double floorHeight = 60;

  /// Space above the strip, over the content, that hops and hearts can use.
  static const double headroom = 48;

  final Random? random;

  /// Tests turn this off: the cats still move and take taps, they just aren't drawn.
  final bool loadSprites;

  @override
  State<PetLayer> createState() => PetLayerState();
}

class PetLayerState extends State<PetLayer> with SingleTickerProviderStateMixin {
  static const double _edgeMargin = 24;

  late final Random _random = widget.random ?? Random();
  late final Ticker _ticker;
  late final AppLifecycleListener _lifecycle;
  StreamSubscription<PetCue>? _cues;
  final ValueNotifier<int> _frame = ValueNotifier(0);
  final Map<String, CatSprites> _sprites = {};
  List<Pet>? _pets;
  Size _size = Size.zero;
  Duration _last = Duration.zero;
  bool _disposed = false;

  /// Seconds the cats have been running (paused in the background), for delayed reactions.
  double _clock = 0;
  final List<({double at, String cat, PetReaction reaction})> _scheduled = [];

  @visibleForTesting
  List<Pet> get pets => _pets ?? const [];

  /// Puts [cat] at [x], standing still. Tests only.
  @visibleForTesting
  void debugPlace(String cat, double x) {
    final p = pets.firstWhere((p) => p.cat == cat);
    p.x = x;
    p.debugSetState(PetState.idle);
  }

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_tick)..start();
    _lifecycle = AppLifecycleListener(onStateChange: _onLifecycle);
    _cues = PetEvents.instance.cues.listen(_onCue);
    if (widget.loadSprites) _loadSprites();
  }

  Future<void> _loadSprites() async {
    for (final cat in PetSettings.cats) {
      for (final shiny in [false, true]) {
        try {
          final s = await CatSprites.load(cat, shiny);
          if (_disposed) {
            s.dispose();
            return;
          }
          _sprites[PetPainter.spriteKey(cat, shiny)] = s;
        } catch (e) {
          debugPrint('Walking cats: could not load $cat (shiny: $shiny): $e');
        }
      }
    }
  }

  /// Pauses the cats while the app isn't on screen, so they don't use battery.
  void _onLifecycle(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      if (!_ticker.isActive) {
        _last = Duration.zero;
        _ticker.start();
      }
    } else if (_ticker.isActive) {
      _ticker.stop();
    }
  }

  void _onCue(PetCue c) {
    if (c.delay <= Duration.zero) {
      _react(c.cat, c.reaction);
    } else {
      _scheduled.add((at: _clock + c.delay.inMicroseconds / 1e6, cat: c.cat, reaction: c.reaction));
    }
  }

  void _react(String cat, PetReaction reaction) {
    for (final p in pets) {
      if (p.cat != cat) continue;
      switch (reaction) {
        case PetReaction.hop:
          p.hop();
        case PetReaction.nod:
          p.nod();
      }
    }
  }

  (double, double) get _bounds => (_edgeMargin, _size.width - _edgeMargin);

  void _tick(Duration elapsed) {
    // At most 0.1 s per step, so a slow frame doesn't teleport the cats.
    final dt = ((elapsed - _last).inMicroseconds / 1e6).clamp(0.0, 0.1).toDouble();
    _last = elapsed;
    _clock += dt;
    if (_scheduled.isNotEmpty) {
      final due = _scheduled.where((s) => s.at <= _clock).toList();
      _scheduled.removeWhere((s) => s.at <= _clock);
      for (final s in due) {
        _react(s.cat, s.reaction);
      }
    }
    final (minX, maxX) = _bounds;
    for (final p in pets) {
      p.update(dt, minX, maxX);
    }
    _frame.value++;
  }

  void _ensurePets(Size size) {
    _size = size;
    if (_pets != null || size.width <= 0) return;
    final (minX, maxX) = _bounds;
    _pets = [
      for (final cat in PetSettings.cats)
        Pet(cat: cat, random: _random, x: minX + (maxX - minX) * _random.nextDouble()),
    ];
  }

  /// The cat under [position], if any. Later cats are drawn on top, so they're checked first.
  Pet? _petAt(Offset position) {
    for (final p in pets.reversed) {
      if (bodyRect(p, _size).contains(position)) return p;
    }
    return null;
  }

  bool _isShiny(String cat) => PetSettings.current?.isShiny(cat) ?? false;

  @override
  void dispose() {
    _disposed = true;
    _ticker.dispose();
    _lifecycle.dispose();
    _cues?.cancel();
    _frame.dispose();
    for (final s in _sprites.values) {
      s.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        _ensurePets(constraints.biggest);
        return GestureDetector(
          behavior: HitTestBehavior.deferToChild,
          onTapUp: (d) => _petAt(d.localPosition)?.love(),
          child: CustomPaint(
            size: constraints.biggest,
            painter: PetPainter(
              pets: () => pets,
              sprites: _sprites,
              isShiny: _isShiny,
              hits: (position) => _petAt(position) != null,
              repaint: _frame,
            ),
          ),
        );
      },
    );
  }
}
