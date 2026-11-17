import 'package:flutter/material.dart';

import 'pet_settings.dart';

/// The "Walking cats" settings, opened from the paw button in the app bar.
class PetSettingsSheet extends StatelessWidget {
  const PetSettingsSheet({super.key});

  @override
  Widget build(BuildContext context) {
    return const SafeArea(
      child: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(0, 8, 0, 16),
        child: PetSettingsControls(),
      ),
    );
  }
}

/// The walking-cats controls (on/off, each cat's colours, sprite credits): the paw
/// button's sheet and the Settings page both show these, for the same setting.
class PetSettingsControls extends StatelessWidget {
  const PetSettingsControls({super.key});

  @override
  Widget build(BuildContext context) {
    final settings = PetSettings.current;
    if (settings == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final reduceMotion = MediaQuery.disableAnimationsOf(context);

    return ListenableBuilder(
      listenable: settings,
      builder: (context, _) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SwitchListTile(
            title: const Text('Walking cats'),
            subtitle: Text(
              reduceMotion
                  ? "Hidden while your phone's reduce-motion setting is on."
                  : 'Shinx and Litten walk along the bottom of the screen. Tap one for a heart.',
            ),
            value: settings.enabled,
            onChanged: settings.setEnabled,
          ),
          for (final cat in PetSettings.cats)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('$cat colours', style: theme.textTheme.titleSmall),
                  const SizedBox(height: 8),
                  SegmentedButton<ShinyMode>(
                    segments: const [
                      ButtonSegment(value: ShinyMode.auto, label: Text('Auto')),
                      ButtonSegment(
                        value: ShinyMode.normal,
                        label: Text('Normal'),
                      ),
                      ButtonSegment(
                        value: ShinyMode.shiny,
                        label: Text('Shiny'),
                      ),
                    ],
                    selected: {settings.modeFor(cat)},
                    onSelectionChanged: (s) => settings.setMode(cat, s.first),
                  ),
                  if (settings.modeFor(cat) == ShinyMode.auto)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        settings.rolledShiny(cat)
                            ? 'Shiny this time (1 in ${PetSettings.shinyOdds} each launch).'
                            : 'Normal this time; 1 in ${PetSettings.shinyOdds} launches is shiny.',
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
            child: Text(
              'Sprites: PMD SpriteCollab, CC BY-NC 4.0. Shinx by Chunsoft, shiny Shinx by '
              'Reppamon, Litten by Top_Kec, shiny Litten by Emboarger.',
              style: theme.textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
