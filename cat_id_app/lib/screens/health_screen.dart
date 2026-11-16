import 'package:flutter/material.dart';

import '../api.dart';
import '../server_store.dart';
import 'chores_screen.dart';

/// The "Server version" card's (title, detail) from GET /health's `version` (the release
/// tag, or "dev" for a local build) and `commit` (full hash; shown shortened).
(String, String) serverVersionText(Map<String, dynamic> health) {
  final version = health['version'] as String?;
  final commit = health['commit'] as String?;
  final short = commit == null || commit.isEmpty ? null : commit.substring(0, commit.length < 7 ? commit.length : 7);
  if (version == null) {
    return ('Server version unknown', 'This server is older than the version display. Update it to see its version.');
  }
  final title = version == 'dev' ? 'Server: local build' : 'Server $version';
  return (title, short == null ? 'No commit recorded' : 'Commit $short');
}

/// A litterbox counts as overdue for a clean after this long (or if it was never cleaned).
const kCleanOverdueAfter = Duration(hours: 24);

bool cleanOverdue(DateTime? lastCleaned, DateTime now) =>
    lastCleaned == null || now.difference(lastCleaned) > kCleanOverdueAfter;

/// "just now", "25 min ago", "5 h ago", "1 day ago", "3 days ago".
String agoText(DateTime when, DateTime now) {
  final d = now.difference(when);
  if (d.inMinutes < 1) return 'just now';
  if (d.inHours < 1) return '${d.inMinutes} min ago';
  if (d.inDays < 1) return '${d.inHours} h ago';
  return d.inDays == 1 ? '1 day ago' : '${d.inDays} days ago';
}

/// "Today, 9:12 AM", "Yesterday, 11:05 PM" or "Nov 12, 2026, 8:00 AM".
String dayTimeText(BuildContext context, DateTime when) {
  final loc = MaterialLocalizations.of(context);
  final now = DateTime.now();
  final days = DateTime(now.year, now.month, now.day)
      .difference(DateTime(when.year, when.month, when.day))
      .inDays;
  final day = switch (days) {
    0 => 'Today',
    1 => 'Yesterday',
    _ => loc.formatMediumDate(when),
  };
  return '$day, ${loc.formatTimeOfDay(TimeOfDay.fromDateTime(when))}';
}

/// GET /health: model status, training photos per class, captures waiting in the
/// inbox, when each litterbox was last cleaned and its bag last changed, which chores are
/// overdue, and which server build this is. Also the Retrain button (POST /api/retrain).
class HealthScreen extends StatefulWidget {
  const HealthScreen(
      {super.key, required this.server, required this.onOpenLabel, this.onOpenChores});

  final Server server;

  /// Switches to the Label tab.
  final VoidCallback onOpenLabel;

  /// Opens the Chores page (the Chores card's button); null = no button.
  final VoidCallback? onOpenChores;

  @override
  State<HealthScreen> createState() => _HealthScreenState();
}

class _HealthScreenState extends State<HealthScreen> {
  Map<String, dynamic>? _data;
  String? _error;
  bool _loading = false;
  bool _retraining = false;

  CatApi get _api => CatApi(widget.server, '');

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final d = await _api.health();
      if (!mounted) return;
      setState(() => _data = d);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _data = null;
        _error = e.message;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _data = null;
        _error = 'Something went wrong: $e';
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _retrain() async {
    final go = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Retrain the model?'),
        content: const Text(
          'The server trains again on all the photos in its data folders. '
          'This can take a few minutes, and identifying is slow until it finishes.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Retrain')),
        ],
      ),
    );
    if (go != true || !mounted) return;

    setState(() => _retraining = true);
    String message;
    try {
      await _api.retrain();
      message = 'Retrain finished. The new model is loaded.';
    } on ApiException catch (e) {
      message = 'Retrain failed: ${e.message}';
    } catch (e) {
      message = 'Retrain failed: $e';
    }
    if (!mounted) return;
    setState(() => _retraining = false);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    _load();
  }

  String _dayTime(DateTime when) => dayTimeText(context, when);

  /// One section per litterbox: when it was last cleaned (highlighted when overdue, see
  /// [kCleanOverdueAfter]) and when its bag was last changed.
  Widget _litterboxCard(bool dbDown, List<LitterboxStatus> boxes, ThemeData theme) {
    final now = DateTime.now();
    final scheme = theme.colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Litterboxes', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            if (dbDown) const Text("The server's database isn't reachable right now."),
            for (final (i, b) in boxes.indexed) ...[
              if (i > 0) const Divider(),
              Builder(builder: (context) {
                final overdue = cleanOverdue(b.lastCleaned, now);
                final cleaned = b.lastCleaned;
                final bag = b.bagLastChanged;
                final warn = overdue ? scheme.error : null;
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                            child: Text(b.name,
                                style: theme.textTheme.titleSmall?.copyWith(color: warn))),
                        if (overdue)
                          Icon(Icons.warning_amber, size: 20, color: scheme.error),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      cleaned == null
                          ? 'Never cleaned (none recorded yet)'
                          : 'Last cleaned ${_dayTime(cleaned)} (${agoText(cleaned, now)})',
                      style: TextStyle(color: warn),
                    ),
                    Text(bag == null
                        ? 'Bag change not recorded yet'
                        : 'Bag was last changed ${_dayTime(bag)}'),
                  ],
                );
              }),
            ],
          ],
        ),
      ),
    );
  }

  /// The overdue chores (see Chore.overdue), longest overdue first, or "Nothing overdue".
  Widget _choreCard(bool dbDown, List<Chore> chores, ThemeData theme) {
    final now = DateTime.now();
    final scheme = theme.colorScheme;
    final overdue = sortChores(chores).where((c) => c.overdue).toList();
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 8, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text('Chores', style: theme.textTheme.titleMedium)),
                if (widget.onOpenChores != null)
                  TextButton(onPressed: widget.onOpenChores, child: const Text('Open')),
              ],
            ),
            if (dbDown)
              const Text("The server's database isn't reachable right now.")
            else if (overdue.isEmpty)
              const Row(
                children: [
                  Icon(Icons.check_circle_outline, size: 20, color: Colors.greenAccent),
                  SizedBox(width: 8),
                  Text('Nothing overdue'),
                ],
              )
            else
              for (final (i, c) in overdue.indexed) ...[
                if (i > 0) const Divider(),
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                              child: Text(c.label,
                                  style: theme.textTheme.titleSmall?.copyWith(color: scheme.error))),
                          Icon(Icons.warning_amber, size: 20, color: scheme.error),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(choreDueText(c, now), style: TextStyle(color: scheme.error)),
                      Text(lastDoneText(context, c, now)),
                    ],
                  ),
                ),
              ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final theme = Theme.of(context);

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        // Always scrollable, so pull-to-refresh works even when the content is short.
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          if (_loading && data == null) const Center(child: CircularProgressIndicator()),
          if (_error != null)
            Card(
              color: theme.colorScheme.errorContainer,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
                    const SizedBox(height: 12),
                    FilledButton.tonal(onPressed: _load, child: const Text('Try again')),
                  ],
                ),
              ),
            ),
          if (data != null) ..._content(data, theme),
        ],
      ),
    );
  }

  List<Widget> _content(Map<String, dynamic> data, ThemeData theme) {
    final loaded = data['model_loaded'] == true;
    final classes = ((data['classes'] as List?) ?? const []).cast<String>();
    final photos = ((data['photos'] as Map?) ?? const {})
        .map((k, v) => MapEntry(k as String, (v as num).toInt()));
    final waiting = (data['waiting_in_inbox'] as num?)?.toInt() ?? 0;
    final total = photos.values.fold<int>(0, (a, b) => a + b);
    final (versionTitle, versionDetail) = serverVersionText(data);
    // Older servers don't send `litterboxes` (no card); null means its database is down.
    final hasLitterboxes = data.containsKey('litterboxes');
    final litterboxes = [
      for (final l in (data['litterboxes'] as List?) ?? const [])
        LitterboxStatus.fromJson(l as Map<String, dynamic>)
    ];
    // Same for `chores` (older servers: no card; null: database down).
    final hasChores = data.containsKey('chores');
    final chores = [
      for (final c in (data['chores'] as List?) ?? const []) Chore.fromJson(c as Map<String, dynamic>)
    ];

    return [
      Card(
        child: ListTile(
          leading: Icon(
            loaded ? Icons.check_circle : Icons.warning_amber,
            color: loaded ? Colors.greenAccent : Colors.orangeAccent,
          ),
          title: Text(loaded ? 'Model loaded' : 'No model loaded'),
          subtitle: Text(loaded
              ? 'Knows: ${classes.join(', ')}'
              : 'Train it on the server, then pull to refresh.'),
        ),
      ),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Training photos', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              if (photos.isEmpty) const Text('None found in the data folder.'),
              for (final e in photos.entries)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2),
                  child: Row(
                    children: [
                      Expanded(child: Text(e.key)),
                      Text('${e.value}', style: theme.textTheme.titleMedium),
                    ],
                  ),
                ),
              if (photos.isNotEmpty) ...[
                const Divider(),
                Row(
                  children: [
                    const Expanded(child: Text('Total')),
                    Text('$total', style: theme.textTheme.titleMedium),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
      Card(
        child: ListTile(
          leading: const Icon(Icons.inbox_outlined),
          title: Text('$waiting waiting to be sorted'),
          subtitle: const Text('New captures in the inbox'),
          trailing: waiting > 0
              ? TextButton(onPressed: widget.onOpenLabel, child: const Text('Sort'))
              : null,
        ),
      ),
      if (hasLitterboxes) _litterboxCard(data['litterboxes'] == null, litterboxes, theme),
      if (hasChores) _choreCard(data['chores'] == null, chores, theme),
      Card(
        child: ListTile(
          leading: const Icon(Icons.dns_outlined),
          title: Text(versionTitle),
          subtitle: Text(versionDetail),
        ),
      ),
      const SizedBox(height: 8),
      if (_retraining) ...[
        const LinearProgressIndicator(),
        const SizedBox(height: 8),
        const Text(
          'Retraining… this can take several minutes. You can leave this screen open.',
          textAlign: TextAlign.center,
        ),
      ] else
        OutlinedButton.icon(
          icon: const Icon(Icons.autorenew),
          label: const Text('Retrain model'),
          onPressed: _retrain,
        ),
    ];
  }
}