import 'package:flutter/material.dart';

import '../api.dart';
import '../server_store.dart';
import 'chores_screen.dart';
import 'health_screen.dart';

/// When chores were done, newest first: one chore's ([chore]) or every chore's. Each entry
/// can be edited (when, who, notes, which chore), deleted (a soft delete) and, with "Show
/// deleted", restored. 50 at a time with Load more. The Requests view lists the times a
/// chore was marked as needed (open, done or cancelled), also newest first.
class ChoreHistoryScreen extends StatefulWidget {
  const ChoreHistoryScreen({
    super.key,
    required this.store,
    required this.server,
    required this.chores,
    required this.people,
    this.chore,
  });

  final ServerStore store;
  final Server server;

  /// Null = every chore.
  final Chore? chore;

  /// For the edit form's chore and people choices.
  final List<Chore> chores;
  final List<String> people;

  @override
  State<ChoreHistoryScreen> createState() => _ChoreHistoryScreenState();
}

class _ChoreHistoryScreenState extends State<ChoreHistoryScreen> {
  final _events = <ChoreEvent>[];
  final _requests = <ChoreRequest>[];
  bool _showRequests = false;
  String? _next;
  String? _error;
  bool _loading = false;
  bool _loaded = false;
  bool _showDeleted = false;

  Future<CatApi> _api() async =>
      CatApi(widget.server, await widget.store.keyFor(widget.server.id));

  @override
  void initState() {
    super.initState();
    _load();
  }

  /// The first page, or the next one when [more].
  Future<void> _load({bool more = false}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = await _api();
      if (_showRequests) {
        final requests =
            await api.choreRequests(chore: widget.chore?.name, before: more ? _next : null);
        if (!mounted) return;
        setState(() {
          if (!more) _requests.clear();
          _requests.addAll(requests.requests);
          _next = requests.next;
          _loaded = true;
        });
        return;
      }
      final page = await api.choreEvents(
          chore: widget.chore?.name, includeDeleted: _showDeleted, before: more ? _next : null);
      if (!mounted) return;
      setState(() {
        if (!more) _events.clear();
        _events.addAll(page.events);
        _next = page.next;
        _loaded = true;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _toast(String text) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

  Future<void> _edit(ChoreEvent e) async {
    final saved = await showChoreEventSheet(context,
        api: _api, chore: null, chores: widget.chores, people: widget.people, initial: e);
    if (saved == null) return;
    if (mounted) _toast('Saved.');
    _load();
  }

  Future<void> _delete(ChoreEvent e) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this entry?'),
        content: Text('${e.choreLabel} · ${dayTimeText(context, e.when)}\n\n'
            'You can bring it back with "Show deleted" and Restore.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    await _change(() async => (await _api()).deleteChoreEvent(e.id), 'Deleted.');
  }

  Future<void> _restore(ChoreEvent e) =>
      _change(() async => (await _api()).restoreChoreEvent(e.id), 'Restored.');

  Future<void> _change(Future<void> Function() call, String done) async {
    try {
      await call();
      if (mounted) _toast(done);
    } on ApiException catch (e) {
      if (mounted) _toast(e.message);
    } catch (e) {
      if (mounted) _toast('Something went wrong: $e');
    }
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final now = DateTime.now();
    return Scaffold(
      appBar: AppBar(title: Text(widget.chore == null ? 'Chore history' : widget.chore!.label)),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          children: [
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: false, label: Text('Done'), icon: Icon(Icons.check)),
                ButtonSegment(
                    value: true, label: Text('Requests'), icon: Icon(Icons.shopping_cart_outlined)),
              ],
              selected: {_showRequests},
              onSelectionChanged: (v) {
                setState(() {
                  _showRequests = v.first;
                  _loaded = false;
                  _next = null;
                });
                _load();
              },
            ),
            if (_showRequests)
              const SizedBox(height: 12)
            else
              Row(
                children: [
                  const Spacer(),
                  const Text('Show deleted'),
                  Switch(
                    value: _showDeleted,
                    onChanged: (on) {
                      setState(() => _showDeleted = on);
                      _load();
                    },
                  ),
                ],
              ),
            if (_loading && !_loaded) const Center(child: CircularProgressIndicator()),
            if (_error != null)
              Card(
                color: theme.colorScheme.errorContainer,
                child: ListTile(
                  leading: Icon(Icons.error_outline, color: theme.colorScheme.onErrorContainer),
                  title: Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
                  trailing: IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
                ),
              ),
            if (_loaded && (_showRequests ? _requests : _events).isEmpty && _error == null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 24),
                child: Text(_showRequests ? 'Never marked as needed.' : 'Nothing recorded yet.',
                    textAlign: TextAlign.center),
              ),
            if (_showRequests)
              for (final r in _requests)
                _RequestCard(request: r, showChore: widget.chore == null, now: now),
            if (!_showRequests)
              for (final e in _events)
                _EventCard(
                  event: e,
                  showChore: widget.chore == null,
                  when: '${dayTimeText(context, e.when)} (${agoText(e.when, now)})',
                  onEdit: () => _edit(e),
                  onDelete: () => _delete(e),
                  onRestore: () => _restore(e),
                ),
            if (_next != null)
              Center(
                child: _loading
                    ? const CircularProgressIndicator()
                    : OutlinedButton(
                        onPressed: () => _load(more: true), child: const Text('Load more')),
              ),
          ],
        ),
      ),
    );
  }
}

/// A past or open request: when and by whom, its details, and how it ended.
class _RequestCard extends StatelessWidget {
  const _RequestCard({required this.request, required this.showChore, required this.now});

  final ChoreRequest request;
  final bool showChore;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final r = request;
    final when = '${dayTimeText(context, r.requestedOn)} (${agoText(r.requestedOn, now)})';
    final String status;
    String? ended;
    switch (r.status) {
      case 'done':
        status = 'Done';
        final by = r.doneBy.isNotEmpty ? r.doneBy.join(' and ') : (r.closedBy ?? 'someone');
        ended = 'Done by $by${r.doneOn != null ? ', ${dayTimeText(context, r.doneOn!)}' : ''}';
      case 'cancelled':
        status = 'Cancelled';
        ended = 'Cancelled by ${r.closedBy ?? 'someone'}'
            '${r.cancelledOn != null ? ', ${dayTimeText(context, r.cancelledOn!)}' : ''}';
      default:
        status = r.overdue ? 'Overdue' : 'Open';
    }
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(showChore ? '${r.choreLabel} · $when' : when,
                      style: theme.textTheme.titleSmall),
                ),
                Chip(label: Text(status), visualDensity: VisualDensity.compact),
              ],
            ),
            Text('Asked by ${r.requestedBy ?? 'someone'}'),
            for (final l in requestDetailLines(context, r)) Text(l),
            if (ended != null) Text(ended),
          ],
        ),
      ),
    );
  }
}

class _EventCard extends StatelessWidget {
  const _EventCard({
    required this.event,
    required this.showChore,
    required this.when,
    required this.onEdit,
    required this.onDelete,
    required this.onRestore,
  });

  final ChoreEvent event;
  final bool showChore;
  final String when;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onRestore;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = event;
    final lines = [
      e.doneBy.isEmpty ? 'Who did it: not recorded' : 'Done by ${e.doneBy.join(' and ')}',
      if (e.startedOn != null && e.took != null)
        'Started ${dayTimeText(context, e.startedOn!)} · took ${tookText(e.took!)}',
      if (e.notes != null) e.notes!,
      'Added by ${e.reporter ?? 'unknown'}'
          '${e.modifiedBy != null && e.modifiedBy != e.reporter ? ' · last changed by ${e.modifiedBy}' : ''}',
    ];
    return Opacity(
      opacity: e.deleted ? 0.55 : 1,
      child: Card(
        margin: const EdgeInsets.only(bottom: 12),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(showChore ? '${e.choreLabel} · $when' : when,
                        style: theme.textTheme.titleSmall),
                  ),
                  if (e.deleted)
                    const Chip(label: Text('Deleted'), visualDensity: VisualDensity.compact),
                ],
              ),
              const SizedBox(height: 4),
              for (final l in lines)
                Padding(padding: const EdgeInsets.only(bottom: 2), child: Text(l)),
              Align(
                alignment: Alignment.centerRight,
                child: e.deleted
                    ? TextButton.icon(
                        icon: const Icon(Icons.restore), label: const Text('Restore'), onPressed: onRestore)
                    : OverflowBar(
                        spacing: 4,
                        children: [
                          TextButton.icon(
                              icon: const Icon(Icons.edit_outlined), label: const Text('Edit'), onPressed: onEdit),
                          TextButton.icon(
                              icon: const Icon(Icons.delete_outline),
                              label: const Text('Delete'),
                              onPressed: onDelete),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
