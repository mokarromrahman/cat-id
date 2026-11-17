import 'package:flutter/material.dart';

import '../api.dart';
import '../app_update.dart';
import '../pets/pet_settings.dart';
import '../pets/pet_settings_sheet.dart';
import '../server_store.dart';
import '../who_am_i.dart';
import 'health_screen.dart';
import 'servers_screen.dart';

/// Menu > Settings. The app and server versions, updates ("Show prereleases" and its
/// offer; "Install latest release" on a dev build), and copies of settings that also live
/// elsewhere: Who am I (app bar), Walking cats (paw button) and the saved servers (Servers
/// screen). The copies change the same settings, so both places always agree.
class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.store});

  final ServerStore store;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  CatApi? _api;
  Map<String, dynamic>? _health;
  AppUpdates? _updates;
  String? _updateError;
  bool _loading = false;
  bool _showPrereleases = false;

  /// Which server the versions above are for (picking another server reloads them).
  String? _loadedFor;

  ServerStore get _store => widget.store;

  @override
  void initState() {
    super.initState();
    _store.addListener(_onStoreChanged);
    UpdatePrefs.showPrereleases().then((on) {
      if (mounted) setState(() => _showPrereleases = on);
    });
    _load();
  }

  @override
  void dispose() {
    _store.removeListener(_onStoreChanged);
    super.dispose();
  }

  String? _tag(Server? s) => s == null ? null : '${s.id}-${s.address}';

  void _onStoreChanged() {
    if (_tag(_store.selected) != _loadedFor) _load();
  }

  Future<void> _load() async {
    final server = _store.selected;
    _loadedFor = _tag(server);
    if (server == null) return;
    setState(() {
      _loading = true;
      _updateError = null;
    });
    final api = CatApi(server, await _store.keyFor(server.id));
    Map<String, dynamic>? health;
    AppUpdates? updates;
    String? error;
    await Future.wait([
      api.health().then((h) => health = h).catchError((_) => <String, dynamic>{}),
      api.appUpdates().then((u) => updates = u).catchError((Object e) {
        error = e is ApiException ? e.message : 'Something went wrong: $e';
        return AppUpdates.fromJson(const {});
      }),
    ]);
    // Another server was picked while this one was loading.
    if (!mounted || _tag(server) != _loadedFor) return;
    setState(() {
      _api = api;
      _health = health;
      _updates = updates;
      _updateError = error;
      _loading = false;
    });
  }

  Future<void> _setShowPrereleases(bool on) async {
    setState(() => _showPrereleases = on);
    await UpdatePrefs.setShowPrereleases(on);
  }

  void _update(AppUpdateInfo update, {String? title}) {
    final api = _api;
    if (api != null) startAppUpdate(context, api, update, title: title);
  }

  Widget _heading(String text) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 24, 16, 4),
        child: Text(text,
            style: Theme.of(context)
                .textTheme
                .titleSmall
                ?.copyWith(color: Theme.of(context).colorScheme.primary)),
      );

  List<Widget> _appSection() {
    final health = _health;
    final (serverTitle, serverDetail) = health == null
        ? (_loading ? 'Server version' : 'Server version unknown',
            _loading ? 'Loading…' : "Couldn't reach the server.")
        : serverVersionText(health);
    return [
      _heading('App'),
      ListTile(
        leading: const Icon(Icons.phone_android),
        title: Text(isDevBuild ? 'This is a dev build' : 'Kitten Dex $installedAppVersion'),
        subtitle: Text(isDevBuild
            ? 'Built on a computer, not a release. The Health tab never offers it updates; '
                'use "Install latest release" below to get back onto a release.'
            : 'Installed version'),
      ),
      ListTile(
        leading: const Icon(Icons.dns_outlined),
        title: Text(serverTitle),
        subtitle: Text(serverDetail),
      ),
    ];
  }

  List<Widget> _updatesSection() {
    final updates = _updates;
    final release = updates?.release;
    final offer = updates == null ? null : healthUpdateOffer(updates);
    final pre = updates == null ? null : prereleaseOffer(updates);
    final theme = Theme.of(context);
    return [
      _heading('Updates'),
      if (_loading) const LinearProgressIndicator(),
      if (_updateError != null)
        ListTile(
          leading: Icon(Icons.error_outline, color: theme.colorScheme.error),
          title: Text(_updateError!),
          trailing: TextButton(onPressed: _load, child: const Text('Try again')),
        )
      else if (updates != null) ...[
        if (isDevBuild)
          ListTile(
            leading: const Icon(Icons.system_update),
            title: const Text('Install latest release'),
            subtitle: Text(release == null
                ? 'The server has no release APK yet.'
                : 'Replaces this dev build with ${release.version}.'),
            trailing: FilledButton.tonal(
              onPressed: release == null
                  ? null
                  : () => _update(release, title: 'Install ${release.version}'),
              child: const Text('Install'),
            ),
          )
        else if (offer != null)
          ListTile(
            leading: const Icon(Icons.system_update),
            title: Text('Update available: ${offer.version}'),
            subtitle: const Text('Also on the Health tab.'),
            trailing:
                FilledButton(onPressed: () => _update(offer), child: const Text('Update')),
          )
        else
          ListTile(
            leading: const Icon(Icons.check_circle_outline, color: Colors.greenAccent),
            title: const Text('Up to date'),
            subtitle: Text(release == null
                ? 'The server has no release APK yet.'
                : 'Newest release on the server: ${release.version}'),
          ),
      ],
      SwitchListTile(
        secondary: const Icon(Icons.science_outlined),
        title: const Text('Show prereleases'),
        subtitle: const Text(
            'Test versions (tags like v1.5.0-test). Offered only here, never on the Health tab.'),
        value: _showPrereleases,
        onChanged: _setShowPrereleases,
      ),
      if (_showPrereleases && updates != null && _updateError == null)
        pre == null
            ? const ListTile(
                leading: SizedBox(width: 24),
                title: Text('No newer prerelease'),
              )
            : ListTile(
                leading: Icon(Icons.new_releases_outlined, color: theme.colorScheme.tertiary),
                title: Text('Prerelease ${pre.version} available'),
                trailing: FilledButton.tonal(
                  onPressed: () => _update(pre, title: 'Install prerelease ${pre.version}'),
                  child: const Text('Update'),
                ),
              ),
    ];
  }

  List<Widget> _whoAmISection() {
    final who = WhoAmI.loaded;
    if (who == null) return const [];
    return [
      _heading('Who am I'),
      ListenableBuilder(
        listenable: who,
        builder: (context, _) => Column(
          children: [
            for (final p in WhoAmI.people)
              ListTile(
                leading: Icon(
                    p == who.name ? Icons.radio_button_checked : Icons.radio_button_off),
                title: Text(p),
                onTap: () => who.set(p),
              ),
          ],
        ),
      ),
      const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16),
        child: Text(
            'Saved on this phone. The server records it on photos, labels, coughs and vet visits. '
            'Same setting as the name in the top bar.'),
      ),
    ];
  }

  List<Widget> _petsSection() {
    if (PetSettings.current == null) return const [];
    return [_heading('Walking cats'), const PetSettingsControls()];
  }

  List<Widget> _serversSection() {
    return [
      _heading('Servers'),
      ListenableBuilder(
        listenable: _store,
        builder: (context, _) {
          final selectedId = _store.selected?.id;
          return Column(
            children: [
              for (final s in _store.servers)
                ListTile(
                  leading:
                      Icon(s.id == selectedId ? Icons.check_circle : Icons.circle_outlined),
                  title: Text(s.label),
                  subtitle: s.name.isEmpty ? null : Text(s.address),
                  onTap: () => _store.select(s.id),
                ),
              ListTile(
                leading: const Icon(Icons.edit_outlined),
                title: const Text('Manage servers'),
                subtitle: const Text('Add, edit or remove a server'),
                onTap: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(builder: (_) => ServersScreen(store: _store))),
              ),
            ],
          );
        },
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.only(bottom: 16 + MediaQuery.paddingOf(context).bottom),
          children: [
            ..._appSection(),
            ..._updatesSection(),
            ..._whoAmISection(),
            ..._petsSection(),
            ..._serversSection(),
          ],
        ),
      ),
    );
  }
}
