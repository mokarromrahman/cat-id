import 'dart:math';

import 'package:cat_id_app/pets/pet.dart';
import 'package:flutter_test/flutter_test.dart';

const dt = 1 / 60;
const minX = 20.0, maxX = 380.0;
const everyday = {PetState.idle, PetState.walkLeft, PetState.walkRight, PetState.sleep};

/// Runs [p] for [seconds] in 1/60 s steps; returns how long it took for [until] to be true
/// (or the full time).
double run(Pet p, double seconds, {bool Function()? until}) {
  var t = 0.0;
  while (t < seconds - 1e-9) {
    p.update(dt, minX, maxX);
    t += dt;
    if (until != null && until()) break;
  }
  return t;
}

void main() {
  test('wanders for 20 minutes inside the strip, making only allowed moves', () {
    for (var seed = 1; seed <= 5; seed++) {
      final p = Pet(cat: 'Shinx', random: Random(seed), x: 200);
      final seen = <PetState>{p.state};
      var prev = p.state;
      for (var i = 0; i < 60 * 60 * 20; i++) {
        p.update(dt, minX, maxX);
        expect(p.x, inInclusiveRange(minX, maxX));
        expect(everyday, contains(p.state));
        if (p.state != prev) {
          expect(kNextStates[prev], contains(p.state), reason: '$prev -> ${p.state} (seed $seed)');
          prev = p.state;
        }
        seen.add(p.state);
      }
      expect(seen, everyday, reason: 'seed $seed should idle, walk both ways and sleep');
    }
  });

  test('speed is randomised between 0.7x and 1.3x', () {
    for (var seed = 0; seed < 50; seed++) {
      final p = Pet(cat: 'Litten', random: Random(seed), x: 100);
      expect(p.speed, inInclusiveRange(28, 52));
    }
  });

  test('a walk ends at the edge of the strip', () {
    final p = Pet(cat: 'Shinx', random: Random(1), x: 370)..debugSetState(PetState.walkRight);
    p.update(1.0, minX, maxX);
    expect(p.x, maxX);
    expect(p.state, isNot(PetState.walkRight));

    final q = Pet(cat: 'Shinx', random: Random(1), x: 30)..debugSetState(PetState.walkLeft);
    q.update(1.0, minX, maxX);
    expect(q.x, minX);
    expect(q.state, isNot(PetState.walkLeft));
  });

  test('a hop lasts 1.2 s, then the cat carries on walking', () {
    final p = Pet(cat: 'Shinx', random: Random(2), x: 200)..debugSetState(PetState.walkRight);
    p.hop();
    expect(p.state, PetState.hop);
    final xBefore = p.x;
    final took = run(p, 5, until: () => p.state != PetState.hop);
    expect(took, closeTo(kHopSeconds, 2 * dt));
    expect(p.state, PetState.walkRight);
    expect(p.x, xBefore, reason: "it doesn't move while hopping");
  });

  test('a hop wakes a sleeping cat', () {
    final p = Pet(cat: 'Litten', random: Random(3), x: 200)..debugSetState(PetState.sleep);
    p.hop();
    run(p, kHopSeconds + 0.1);
    expect(p.state, PetState.idle);
  });

  test('a second hop restarts the first instead of stacking', () {
    final p = Pet(cat: 'Litten', random: Random(4), x: 200)..debugSetState(PetState.idle);
    p.hop();
    run(p, 1.0);
    p.hop();
    run(p, 1.0);
    expect(p.state, PetState.hop, reason: 'only 1.0 s into the second hop');
    run(p, 0.3);
    expect(p.state, PetState.idle);
  });

  test('a tap shows a heart for 2 s, then the cat carries on', () {
    final p = Pet(cat: 'Shinx', random: Random(5), x: 200)..debugSetState(PetState.idle);
    expect(p.heartAge, isNull);
    p.love();
    expect(p.state, PetState.love);
    expect(p.heartAge, 0);
    run(p, 1.0);
    expect(p.heartAge, closeTo(1.0, 2 * dt));
    run(p, 1.1);
    expect(p.heartAge, isNull);
    expect(p.state, PetState.idle);
  });

  test('a tap during a hop still goes back to what the cat was doing first', () {
    final p = Pet(cat: 'Litten', random: Random(6), x: 200)..debugSetState(PetState.walkLeft);
    p.hop();
    run(p, 0.5);
    p.love();
    // Check the moment the heart ends: walking on, the cat may stop at random.
    final took = run(p, 5, until: () => p.state != PetState.love);
    expect(took, closeTo(kLoveSeconds, 2 * dt));
    expect(p.state, PetState.walkLeft);
  });

  test('a nod (cough reported) faces you for 1 s with no heart, then carries on', () {
    final p = Pet(cat: 'Shinx', random: Random(7), x: 200)..debugSetState(PetState.walkRight);
    p.nod();
    expect(p.state, PetState.nod);
    expect(p.heartAge, isNull);
    final xBefore = p.x;
    final took = run(p, 5, until: () => p.state != PetState.nod);
    expect(took, closeTo(kNodSeconds, 2 * dt));
    expect(p.state, PetState.walkRight);
    expect(p.x, xBefore, reason: "it doesn't move while nodding");
    expect(p.heartAge, isNull);
  });
}
