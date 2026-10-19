import 'package:flutter/material.dart';

import '../api.dart';
import '../server_store.dart';

/// GET /health: model status, training photos per class, captures waiting in the
/// inbox. Also the Retrain button (POST /api/retrain).
class HealthScreen extends StatefulWidget {
  const HealthScreen({super.key, required this.server, required this.onOpenLabel});

  final Server server;

  /// Switches to the Label tab.
  final VoidCallback onOpenLabel;

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