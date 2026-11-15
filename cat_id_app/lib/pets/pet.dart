import 'dart:math';

import 'package:flutter/foundation.dart';

/// What a cat on the floor strip is doing.
///
/// The first four are its everyday states: when one ends, the next is picked at random from
/// [kNextStates] (the same idea as vscode-pokemon). [hop], [love] and [nod] interrupt
/// whatever the cat was doing; when they end, it goes back to it (a sleeping cat wakes up
/// instead).
enum PetState { idle, walkLeft, walkRight, sleep, hop, love, nod }

/// Which everyday state can follow which.
const Map<PetState, List<PetState>> kNextStates = {
  PetState.idle: [PetState.walkLeft, PetState.walkRight, PetState.sleep],
  PetState.walkLeft: [PetState.idle, PetState.walkRight],
  PetState.walkRight: [PetState.idle, PetState.walkLeft],
  PetState.sleep: [PetState.idle],
};

/// A hop when Identify recognises the cat: three hops of 0.4 s.
const double kHopSeconds = 1.2;

/// After a tap: the cat faces you, nods and shows a heart.
const double kLoveSeconds = 2.0;
const double kHeartSeconds = 2.0;

/// After a cough is reported: the cat faces you and nods, no heart.
const double kNodSeconds = 1.0;

/// While walking, the chance of stopping early in each 0.1 s.
const double kStopChancePerTenth = 0.01;

/// One cat on the strip. Pure logic, no drawing: [update] moves it on by some time.
class Pet {
  Pet({required this.cat, required Random random, required this.x, double baseSpeed = 40})
      : _random = random,
        speed = baseSpeed * (0.7 + 0.6 * random.nextDouble()) {
    _enter(PetState.idle);
  }

  /// "Shinx" or "Litten".
  final String cat;
  final Random _random;

  /// Walking speed in logical pixels per second (randomised per cat).
  final double speed;

  /// Horizontal centre, in the strip's coordinates.
  double x;

  PetState _state = PetState.idle;
  double _time = 0;
  double _hold = 0;
  bool _facingRight = true;

  PetState? _savedState;
  double _savedTime = 0;
  double _savedHold = 0;

  double? _heartAge;

  PetState get state => _state;

  /// Seconds since the current state started.
  double get stateTime => _time;

  bool get facingRight => _facingRight;

  /// Seconds since the heart appeared, or null when there's no heart.
  double? get heartAge => _heartAge;

  /// Moves the cat on by [dt] seconds, keeping its centre between [minX] and [maxX].
  void update(double dt, double minX, double maxX) {
    if (maxX < minX) maxX = minX;

    final heart = _heartAge;
    if (heart != null) {
      _heartAge = heart + dt >= kHeartSeconds ? null : heart + dt;
    }

    _time += dt;
    var done = _time >= _hold;
    switch (_state) {
      case PetState.walkRight:
        _facingRight = true;
        x += speed * dt;
        if (x >= maxX) done = true;
        if (_stopsNow(dt)) done = true;
      case PetState.walkLeft:
        _facingRight = false;
        x -= speed * dt;
        if (x <= minX) done = true;
        if (_stopsNow(dt)) done = true;
      default:
        break;
    }
    x = x.clamp(minX, maxX).toDouble();
    if (done) _finish();
  }

  /// Hop (Identify recognised this cat, or a litterbox visit was reported).
  void hop() => _interrupt(PetState.hop);

  /// Face the viewer and nod (a cough was reported).
  void nod() => _interrupt(PetState.nod);

  /// Face the viewer, nod and show a heart (tapped).
  void love() {
    _interrupt(PetState.love);
    _heartAge = 0;
  }

  /// Puts the cat straight into [state] for [hold] seconds. Tests only.
  @visibleForTesting
  void debugSetState(PetState state, {double hold = 1e9}) {
    _savedState = null;
    _state = state;
    _time = 0;
    _hold = hold;
  }

  bool _stopsNow(double dt) =>
      _random.nextDouble() < 1 - pow(1 - kStopChancePerTenth, dt / 0.1);

  void _interrupt(PetState s) {
    // A new interrupt during one restarts it; the cat still goes back to what it was doing
    // before the first one.
    if (_savedState == null) {
      _savedState = _state;
      _savedTime = _time;
      _savedHold = _hold;
    }
    _enter(s);
  }

  void _finish() {
    final saved = _savedState;
    if (saved != null) {
      _savedState = null;
      if (saved == PetState.sleep) {
        _enter(PetState.idle); // woken up
      } else {
        _state = saved;
        _time = _savedTime;
        _hold = _savedHold;
      }
      return;
    }
    final next = kNextStates[_state] ?? const [PetState.idle];
    _enter(next[_random.nextInt(next.length)]);
  }

  void _enter(PetState s) {
    _state = s;
    _time = 0;
    _hold = _holdFor(s);
  }

  double _between(double lo, double hi) => lo + (hi - lo) * _random.nextDouble();

  double _holdFor(PetState s) {
    switch (s) {
      case PetState.idle:
        return _between(2, 5);
      case PetState.walkLeft:
      case PetState.walkRight:
        return _between(3, 8);
      case PetState.sleep:
        return _between(8, 16);
      case PetState.hop:
        return kHopSeconds;
      case PetState.love:
        return kLoveSeconds;
      case PetState.nod:
        return kNodSeconds;
    }
  }
}
