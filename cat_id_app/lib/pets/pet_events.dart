import 'dart:async';

/// How a walking cat reacts to something that happened elsewhere in the app.
enum PetReaction {
  /// Three happy hops: Identify recognised the cat, or a litterbox visit was reported.
  hop,

  /// Faces you and nods: a cough was reported.
  nod,
}

/// One reaction for one cat, starting after [delay].
typedef PetCue = ({String cat, PetReaction reaction, Duration delay});

/// One event reported in the Add event form.
typedef PetReport = ({String cat, PetReaction reaction});

/// Things that happen elsewhere in the app that the walking cats react to. The pet layer
/// listens to [cues]. Only "Litten" and "Shinx" do anything ("uncertain", "neither" don't).
class PetEvents {
  PetEvents._();

  static final PetEvents instance = PetEvents._();

  static const cats = ['Litten', 'Shinx'];

  /// After the Add event form closes, the first reaction waits this long, so it starts once
  /// the form has slid away.
  static const afterFormCloses = Duration(milliseconds: 300);

  /// Gap between two cats' reactions, so they go one after the other.
  static const stagger = Duration(milliseconds: 800);

  final _cues = StreamController<PetCue>.broadcast();

  Stream<PetCue> get cues => _cues.stream;

  /// Identify recognised [cat]: it hops now.
  void celebrate(String cat) => cue(cat, PetReaction.hop);

  void cue(String cat, PetReaction reaction, {Duration delay = Duration.zero}) {
    if (cats.contains(cat)) _cues.add((cat: cat, reaction: reaction, delay: delay));
  }

  /// The Add event form closed after sending [reports] (litterbox = hop, cough = nod). The
  /// form covers the cat strip while it's open, so the cats react now, where you can see
  /// them: one reaction per cat (a hop beats a nod), in the order they were first reported,
  /// one after the other. Nothing was sent, nothing happens.
  void afterReports(Iterable<PetReport> reports) {
    final order = <String>[];
    final best = <String, PetReaction>{};
    for (final r in reports) {
      if (!cats.contains(r.cat)) continue;
      if (!best.containsKey(r.cat)) order.add(r.cat);
      if (best[r.cat] != PetReaction.hop) best[r.cat] = r.reaction;
    }
    for (var i = 0; i < order.length; i++) {
      cue(order[i], best[order[i]]!, delay: afterFormCloses + stagger * i);
    }
  }
}
