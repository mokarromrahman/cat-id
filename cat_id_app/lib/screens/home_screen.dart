import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../camera_recovery.dart';
import '../pets/pet_layer.dart';
import '../pets/pet_settings.dart';
import '../pets/pet_settings_sheet.dart';
import '../server_store.dart';
import '../who_am_i.dart';
import 'chores_screen.dart';
import 'events_screen.dart';
import 'health_screen.dart';
import 'identify_screen.dart';
import 'label_screen.dart';
import 'servers_screen.dart';
import 'settings_screen.dart';
import 'vet_screen.dart';

/// Cough has no tab of its own: the Events tab's "Add event" menu opens the cough or
/// litterbox form.
enum AppTab { identify, label, health, events, vet }

/// The order of the buttons along the bottom, left to right.
/// To reorder them, change only this list. The first one is the tab shown at start-up.
const List<AppTab> kTabOrder = [
  AppTab.health,
  AppTab.identify,
  AppTab.events,
  AppTab.vet,
  AppTab.label,
];

/// Pages in the menu (the ☰ button in the app bar), for things that don't need a tab.
/// To add one: add it here and to [kMenuOrder], and give it a case in
/// _HomeScreenState._menuItem and _HomeScreenState._menuPage.
enum MenuPage { chores, settings }

/// The order of the menu entries, top to bottom.
const List<MenuPage> kMenuOrder = [MenuPage.chores, MenuPage.settings];

/// The tabs (Health, Identify, Events, Vet, Label) for the selected server, and the menu
/// (Chores, Settings) for pages without a tab.
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
  /// (Identify, Events and Vet keep what you typed, picked or filtered.)
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

  /// The menu entry's (icon, label).
  (IconData, String) _menuItem(MenuPage p) => switch (p) {
        MenuPage.chores => (Icons.cleaning_services_outlined, 'Chores'),
        MenuPage.settings => (Icons.settings_outlined, 'Settings'),
      };

  Widget _menuPage(MenuPage p, Server server) => switch (p) {
        MenuPage.chores => ChoresScreen(store: widget.store, server: server),
        MenuPage.settings => SettingsScreen(store: widget.store),
      };

  /// Opens a menu page full screen (with its own back button). Health shows chore
  /// warnings, so it reloads when you come back; Label reloads if Who am I was changed
  /// (on Settings), since its address carries the name.
  Future<void> _openPage(MenuPage p) async {
    final server = widget.store.selected!;
    final who = WhoAmI.current;
    await Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => _menuPage(p, server)));
    if (!mounted) return;
    setState(() {
      _gen[AppTab.health] = _gen[AppTab.health]! + 1;
      if (WhoAmI.current != who) _gen[AppTab.label] = _gen[AppTab.label]! + 1;
    });
  }

  Widget _drawer(Server server) {
    return NavigationDrawer(
      selectedIndex: null,
      onDestinationSelected: (i) {
        Navigator.of(context).pop(); // close the menu
        _openPage(kMenuOrder[i]);
      },
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(28, 16, 16, 10),
          child: Text(server.label, style: Theme.of(context).textTheme.titleSmall),
        ),
        for (final p in kMenuOrder)
          NavigationDrawerDestination(
            icon: Icon(_menuItem(p).$1),
            label: Text(_menuItem(p).$2),
          ),
      ],
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
          store: widget.store,
          onOpenLabel: () => _goTo(AppTab.label),
          onOpenChores: () => _openPage(MenuPage.chores),
        );
      case AppTab.events:
        return EventsScreen(key: ValueKey('events-$tag'), store: widget.store, server: server);
      case AppTab.vet:
        return VetScreen(key: ValueKey('vet-$tag'), store: widget.store, server: server);
    }
  }

  /// "Who am I" picker: who is using this phone, sent with every request.
  Future<void> _pickWhoAmI() async {
    final who = WhoAmI.instance;
    final choice = await showDialog<String>(
      context: context,
      builder: (context) => SimpleDialog(
        title: const Text('Who are you?'),
        children: [
          for (final p in WhoAmI.people)
            ListTile(
              leading: Icon(p == who.name ? Icons.radio_button_checked : Icons.radio_button_off),
              title: Text(p),
              onTap: () => Navigator.of(context).pop(p),
            ),
          const Padding(
            padding: EdgeInsets.fromLTRB(24, 8, 24, 4),
            child: Text(
                'Saved on this phone. The server records it on photos, labels, coughs and vet visits.'),
          ),
        ],
      ),
    );
    if (choice != null && choice != who.name) {
      await who.set(choice);
      // The Label tab reloads with the new name in its address.
      setState(() => _gen[AppTab.label] = _gen[AppTab.label]! + 1);
    }
  }

  /// The walking-cats settings (on/off, normal or shiny).
  void _openPetSettings() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (_) => const PetSettingsSheet(),
    );
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
      case AppTab.events:
        return const NavigationDestination(
          icon: Icon(Icons.event_note_outlined),
          selectedIcon: Icon(Icons.event_note),
          label: 'Events',
        );
      case AppTab.vet:
        return const NavigationDestination(
          icon: Icon(Icons.local_hospital_outlined),
          selectedIcon: Icon(Icons.local_hospital),
          label: 'Vet',
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
      drawer: _drawer(server),
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
          ListenableBuilder(
            listenable: WhoAmI.instance,
            builder: (context, _) => TextButton.icon(
              icon: const Icon(Icons.person_outline),
              label: Text(WhoAmI.instance.name ?? 'Who am I?'),
              onPressed: _pickWhoAmI,
            ),
          ),
          if (PetSettings.current != null)
            IconButton(
              tooltip: 'Walking cats',
              icon: const Icon(Icons.pets),
              onPressed: _openPetSettings,
            ),
          IconButton(
            tooltip: 'Servers',
            icon: const Icon(Icons.dns_outlined),
            onPressed: _openServers,
          ),
        ],
      ),
      // Shinx and Litten walk on a strip under the tabs (see lib/pets/).
      body: WithPets(
        child: IndexedStack(
          index: kTabOrder.indexOf(_tab),
          children: [for (final t in kTabOrder) _body(t, server, tag)],
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: kTabOrder.indexOf(_tab),
        onDestinationSelected: (i) => _goTo(kTabOrder[i]),
        destinations: [for (final t in kTabOrder) _destination(t)],
      ),
    );
  }
}