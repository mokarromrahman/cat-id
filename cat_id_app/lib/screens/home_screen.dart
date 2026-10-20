import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../camera_recovery.dart';
import '../server_store.dart';
import 'cough_screen.dart';
import 'health_screen.dart';
import 'identify_screen.dart';
import 'label_screen.dart';
import 'servers_screen.dart';

enum AppTab { identify, label, health, cough }

/// The order of the buttons along the bottom, left to right.
/// To reorder them, change only this list. The first one is the tab shown at start-up.
const List<AppTab> kTabOrder = [
  AppTab.health,
  AppTab.identify,
  AppTab.cough,
  AppTab.label,
];

/// The tabs (Identify, Label, Health, Cough) for the selected server.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.store});

  final ServerStore store;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  AppTab _tab = kTabOrder.first;

  /// Tabs are built the first time you open them (the Label tab loads a web page).
  final Set<AppTab> _visited = {kTabOrder.first};

  /// A camera photo from before Android closed the app (see camera_recovery.dart).
  LostDataResponse? _recoveredPhoto;

  @override
  void initState() {
    super.initState();
    CameraRecovery.recover().then((lost) {
      if (lost == null || !mounted) return;
      _recoveredPhoto = lost;
      _goTo(AppTab.identify);
    });
  }

  /// Bumped each time you arrive on Label or Health, so they load fresh from the server.
  /// (Identify and Cough keep what you typed or picked.)
  final Map<AppTab, int> _gen = {AppTab.label: 0, AppTab.health: 0};

  void _goTo(AppTab t) => setState(() {
        if (t != _tab && _gen.containsKey(t)) _gen[t] = _gen[t]! + 1;
        _tab = t;
        _visited.add(t);
      });

  void _openServers() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => ServersScreen(store: widget.store)),
    );
  }

  Widget _body(AppTab t, Server server, String tag) {
    if (!_visited.contains(t)) return const SizedBox.shrink();
    switch (t) {
      case AppTab.identify:
        return IdentifyScreen(
            key: ValueKey('identify-$tag'),
            store: widget.store,
            server: server,
            recoveredPhoto: _recoveredPhoto);
      case AppTab.label:
        return LabelScreen(key: ValueKey('label-$tag-${_gen[t]}'), server: server);
      case AppTab.health:
        return HealthScreen(
          key: ValueKey('health-$tag-${_gen[t]}'),
          server: server,
          onOpenLabel: () => _goTo(AppTab.label),
        );
      case AppTab.cough:
        return CoughScreen(
            key: ValueKey('cough-$tag'), store: widget.store, server: server);
    }
  }

  NavigationDestination _destination(AppTab t) {
    switch (t) {
      case AppTab.identify:
        return const NavigationDestination(
          icon: Icon(Icons.photo_camera_outlined),
          selectedIcon: Icon(Icons.photo_camera),
          label: 'Identify',
        );
      case AppTab.label:
        return const NavigationDestination(
          icon: Icon(Icons.label_outline),
          selectedIcon: Icon(Icons.label),
          label: 'Label',
        );
      case AppTab.health:
        return const NavigationDestination(
          icon: Icon(Icons.favorite_border),
          selectedIcon: Icon(Icons.favorite),
          label: 'Health',
        );
      case AppTab.cough:
        return const NavigationDestination(
          icon: Icon(Icons.healing_outlined),
          selectedIcon: Icon(Icons.healing),
          label: 'Cough',
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final server = widget.store.selected!;
    // Changing the selected server (or its address) gives the tabs new keys,
    // so they start fresh against the new address.
    final tag = '${server.id}-${server.address}';

    return Scaffold(
      appBar: AppBar(
        title: InkWell(
          onTap: _openServers,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(child: Text(server.label, overflow: TextOverflow.ellipsis)),
              const Icon(Icons.arrow_drop_down),
            ],
          ),
        ),
        actions: [
          IconButton(
            tooltip: 'Servers',
            icon: const Icon(Icons.dns_outlined),
            onPressed: _openServers,
          ),
        ],
      ),
      body: IndexedStack(
        index: kTabOrder.indexOf(_tab),
        children: [for (final t in kTabOrder) _body(t, server, tag)],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: kTabOrder.indexOf(_tab),
        onDestinationSelected: (i) => _goTo(kTabOrder[i]),
        destinations: [for (final t in kTabOrder) _destination(t)],
      ),
    );
  }
}