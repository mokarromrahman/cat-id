import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api.dart';
import '../server_store.dart';
import '../who_am_i.dart';
import 'chore_history_screen.dart';
import 'health_screen.dart';

/// "3 days", "1 day", "5 h", "20 min" (rounded down; at least 1 min).
String spanText(Duration d) {
  if (d.inDays >= 1) return d.inDays == 1 ? '1 day' : '${d.inDays} days';
  if (d.inHours >= 1) return '${d.inHours} h';
  return '${d.inMinutes < 1 ? 1 : d.inMinutes} min';
}

/// "every 7 days" / "every day".
String everyText(int days) => days == 1 ? 'every day' : 'every $days days';

/// The reminder line on a chore: "No reminder", "Never done (every 7 days)",
/// "Overdue by 3 days (every 7 days)", "Due in 2 days (every 7 days)".
String choreDueText(Chore c, DateTime now) {
  final days = c.warningThresholdDays;
  if (days == null) return 'No reminder';
  final every = '(${everyText(days)})';
  final due = c.dueAt;
  if (c.lastDone == null || due == null) return 'Never done $every';
  if (!now.isBefore(due)) return 'Overdue by ${spanText(now.difference(due))} $every';
  return 'Due in ${spanText(due.difference(now))} $every';
}

/// Past its reminder threshold (or never done, with one), whatever its request says.
bool thresholdOverdue(Chore c, DateTime now) {
  if (c.warningThresholdDays == null) return false;
  final due = c.dueAt;
  return c.lastDone == null || due == null || !now.isBefore(due);
}

/// Overdue first (never done, then the longest overdue), then the ones marked as needed
/// (soonest "needed by" first), then the ones with a reminder by how soon they're due, then
/// the rest in the server's order.
List<Chore> sortChores(List<Chore> chores) {
  int group(Chore c) => c.overdue ? 0 : (c.request != null ? 1 : (c.dueAt != null ? 2 : 3));
  final indexed = chores.indexed.toList();
  indexed.sort((a, b) {
    final (ia, ca) = a;
    final (ib, cb) = b;
    final g = group(ca).compareTo(group(cb));
    if (g != 0) return g;
    if (group(ca) == 1) {
      final na = ca.request?.neededBy, nb = cb.request?.neededBy;
      if (na != null && nb == null) return -1;
      if (nb != null && na == null) return 1;
      if (na != null && nb != null && na != nb) return na.compareTo(nb);
    } else if (group(ca) != 3) {
      // A never-done chore has no due date: it sorts first.
      final da = ca.dueAt, db = cb.dueAt;
      if (da == null && db != null) return -1;
      if (db == null && da != null) return 1;
      if (da != null && db != null && da != db) return da.compareTo(db);
    }
    return ia.compareTo(ib);
  });
  return [for (final (_, c) in indexed) c];
}

/// "Last done Today, 9:12 AM by Ashley and Mac (3 h ago)" / "Never done".
String lastDoneText(BuildContext context, Chore c, DateTime now) {
  final last = c.lastDone;
  if (last == null) return 'Never done';
  final by = c.lastDoneBy.isEmpty ? '' : ' by ${c.lastDoneBy.join(' and ')}';
  return 'Last done ${dayTimeText(context, last)}$by (${agoText(last, now)})';
}

/// "45 min", "1 h 20 min", "2 days 3 h", "under a minute" (same as the Discord message).
String tookText(Duration d) {
  final m = d.inMinutes;
  final days = m ~/ 1440, h = (m ~/ 60) % 24, min = m % 60;
  if (days > 0) return '$days day${days == 1 ? '' : 's'}${h > 0 ? ' $h h' : ''}';
  if (h > 0) return '$h h${min > 0 ? ' $min min' : ''}';
  return d.inSeconds < 30 ? 'under a minute' : '${m < 1 ? 1 : m} min';
}

/// "In progress: Ashley and Mac, since Today, 3:10 PM (20 min)".
String startHeadText(BuildContext context, ChoreStart s, DateTime now) =>
    'In progress: ${s.doers.isEmpty ? 'someone' : s.doers.join(' and ')}, since '
    '${dayTimeText(context, s.startedOn)} (${tookText(now.difference(s.startedOn))})';

/// "Fri, Nov 20".
String dayText(BuildContext context, DateTime d) =>
    '${const ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d.weekday - 1]}, '
    '${MaterialLocalizations.of(context).formatShortMonthDay(d)}';

/// "Needed: asked by Mac (2 h ago)".
String requestHeadText(ChoreRequest r, DateTime now) =>
    'Needed: asked by ${r.requestedBy ?? 'someone'} (${agoText(r.requestedOn, now)})';

/// The request's details: "3 bags", "Needed by Fri, Nov 20", its note.
List<String> requestDetailLines(BuildContext context, ChoreRequest r) => [
      ?r.quantityText,
      if (r.neededBy != null)
        'Needed by ${dayText(context, r.neededBy!)}${r.overdue ? ' (overdue)' : ''}',
      ?r.notes,
    ];

/// Date picker, then time picker, for something that already happened. Null if cancelled;
/// a time later than now is refused with a message.
Future<DateTime?> pickPastDateTime(BuildContext context, DateTime? initial,
    {required void Function(String) onError, String helpText = 'When was it done?'}) async {
  final now = DateTime.now();
  final start = initial ?? now;
  final date = await showDatePicker(
    context: context,
    initialDate: start.isAfter(now) ? now : start,
    firstDate: DateTime(2000),
    lastDate: now,
    helpText: helpText,
  );
  if (date == null || !context.mounted) return null;
  final time = await showTimePicker(
    context: context,
    initialTime: TimeOfDay.fromDateTime(start),
    helpText: 'At what time?',
  );
  if (time == null) return null;
  final picked = DateTime(date.year, date.month, date.day, time.hour, time.minute);
  if (picked.isAfter(DateTime.now())) {
    onError("That time hasn't happened yet. Pick now or earlier.");
    return null;
  }
  return picked;
}

/// The Chores page (opened from the menu, or from the Health tab's Chores card): every
/// chore with when it was last done and whether it's overdue, a Done button to record it,
/// its history, and adding or editing chores and their reminder thresholds. Talks to the
/// server's /chores and /chore_events; nothing is kept on the phone.
class ChoresScreen extends StatefulWidget {
  const ChoresScreen({super.key, required this.store, required this.server});

  final ServerStore store;
  final Server server;

  @override
  State<ChoresScreen> createState() => _ChoresScreenState();
}

class _ChoresScreenState extends State<ChoresScreen> {
  ChoreList? _list;
  String? _error;
  bool _loading = false;
  bool _showHidden = false;

  Future<CatApi> _api() async =>
      CatApi(widget.server, await widget.store.keyFor(widget.server.id));

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
      final list = await (await _api()).chores(includeInactive: _showHidden);
      if (!mounted) return;
      setState(() => _list = list);
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

  Future<void> _done(Chore c) async {
    final saved = await showChoreEventSheet(context,
        api: _api, chore: c, chores: _list?.chores ?? [c], people: _list?.people ?? const []);
    if (saved == null) return;
    if (mounted) _toast('${saved.choreLabel} recorded.');
    _load();
  }

  Future<void> _markNeeded(Chore c) async {
    final saved = await showChoreRequestSheet(context, api: _api, chore: c, initial: c.request);
    if (saved == null) return;
    if (mounted) _toast(c.request == null ? '${c.label} marked as needed.' : 'Request saved.');
    _load();
  }

  /// Start (no start yet) or edit the one in progress: join, take over, change the time.
  Future<void> _start(Chore c) async {
    final saved = await showModalBottomSheet<ChoreStart>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
        // Keep the buttons above Android's navigation bar (edge-to-edge).
        child: SafeArea(
          top: false,
          child: ChoreStartForm(
              api: _api, chore: c, people: _list?.people ?? const [], initial: c.inProgress),
        ),
      ),
    );
    if (saved == null) return;
    if (mounted) _toast(c.inProgress == null ? '${c.label} started.' : 'Saved.');
    _load();
  }

  Future<void> _stop(Chore c) async {
    final s = c.inProgress;
    if (s == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Stop ${c.label}?'),
        content: const Text("It's marked as stopped without being finished, and Discord is told. "
            'Use Done instead if it was finished.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Keep going')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Stop')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await (await _api()).stopChoreStart(s.id);
      if (mounted) _toast('${c.label} stopped.');
    } on ApiException catch (e) {
      if (mounted) _toast(e.message);
    } catch (e) {
      if (mounted) _toast('Something went wrong: $e');
    }
    _load();
  }

  Future<void> _cancelRequest(Chore c) async {
    final r = c.request;
    if (r == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Cancel the ${c.label} request?'),
        content: const Text("It's marked as cancelled (kept in the history) and Discord is told."),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Keep it')),
          FilledButton(
              onPressed: () => Navigator.of(context).pop(true), child: const Text('Cancel request')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await (await _api()).cancelChoreRequest(r.id);
      if (mounted) _toast('Request cancelled.');
    } on ApiException catch (e) {
      if (mounted) _toast(e.message);
    } catch (e) {
      if (mounted) _toast('Something went wrong: $e');
    }
    _load();
  }

  Future<void> _editChore([Chore? c]) async {
    final saved = await showDialog<Chore>(
      context: context,
      builder: (_) => ChoreDialog(api: _api, initial: c),
    );
    if (saved == null) return;
    if (mounted) _toast(c == null ? '${saved.label} added.' : '${saved.label} saved.');
    _load();
  }

  Future<void> _history([Chore? c]) async {
    final list = _list;
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => ChoreHistoryScreen(
        store: widget.store,
        server: widget.server,
        chore: c,
        chores: list?.chores ?? [?c],
        people: list?.people ?? const [],
      ),
    ));
    _load(); // an edit or delete there can change when a chore was last done
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final list = _list;
    final chores = list == null ? <Chore>[] : sortChores(list.chores);
    final overdue = chores.where((c) => c.overdue && c.active).length;
    final needed = chores.where((c) => c.request != null && !c.overdue && c.active).length;
    final going = chores.where((c) => c.inProgress != null && c.active).length;
    final now = DateTime.now();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Chores'),
        actions: [
          IconButton(
            tooltip: 'History',
            icon: const Icon(Icons.history),
            onPressed: () => _history(),
          ),
          PopupMenuButton<String>(
            onSelected: (v) {
              if (v == 'hidden') {
                setState(() => _showHidden = !_showHidden);
                _load();
              }
            },
            itemBuilder: (_) => [
              CheckedPopupMenuItem(
                  value: 'hidden', checked: _showHidden, child: const Text('Show hidden chores')),
            ],
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        icon: const Icon(Icons.add),
        label: const Text('Add chore'),
        onPressed: () => _editChore(),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 96), // room for the button
          children: [
            if (_loading && list == null) const Center(child: CircularProgressIndicator()),
            if (_error != null)
              Card(
                color: theme.colorScheme.errorContainer,
                child: ListTile(
                  leading: Icon(Icons.error_outline, color: theme.colorScheme.onErrorContainer),
                  title: Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
                  trailing: IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
                ),
              ),
            if (list != null && _error == null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  chores.isEmpty
                      ? 'No chores yet. Add one with the button below.'
                      : needed == 0 && going == 0
                          ? (overdue == 0 ? 'Nothing overdue.' : '$overdue overdue')
                          : [
                              overdue == 0 ? 'Nothing overdue' : '$overdue overdue',
                              if (needed > 0) '$needed needed',
                              if (going > 0) '$going in progress',
                            ].join(' · '),
                  style: theme.textTheme.titleMedium
                      ?.copyWith(color: overdue > 0 ? theme.colorScheme.error : null),
                ),
              ),
            for (final c in chores)
              _ChoreCard(
                chore: c,
                lastDone: lastDoneText(context, c, now),
                due: choreDueText(c, now),
                onDone: () => _done(c),
                onHistory: () => _history(c),
                onEdit: () => _editChore(c),
                onNeeded: () => _markNeeded(c),
                onCancelRequest: () => _cancelRequest(c),
                onStart: () => _start(c),
                onStop: () => _stop(c),
              ),
          ],
        ),
      ),
    );
  }
}

class _ChoreCard extends StatelessWidget {
  const _ChoreCard({
    required this.chore,
    required this.lastDone,
    required this.due,
    required this.onDone,
    required this.onHistory,
    required this.onEdit,
    required this.onNeeded,
    required this.onCancelRequest,
    required this.onStart,
    required this.onStop,
  });

  final Chore chore;
  final String lastDone;
  final String due;
  final VoidCallback onDone;
  final VoidCallback onHistory;
  final VoidCallback onEdit;
  final VoidCallback onNeeded;
  final VoidCallback onCancelRequest;
  final VoidCallback onStart;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final warn = chore.overdue ? scheme.error : null;
    final request = chore.request;
    final border = warn ?? (request != null ? scheme.tertiary : scheme.outlineVariant);
    return Opacity(
      opacity: chore.active ? 1 : 0.55,
      child: Card(
        margin: const EdgeInsets.only(bottom: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: border, width: chore.overdue || request != null ? 2 : 1),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 8, 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(chore.label,
                        style: theme.textTheme.titleSmall?.copyWith(color: warn)),
                  ),
                  if (!chore.active)
                    const Chip(label: Text('Hidden'), visualDensity: VisualDensity.compact),
                  if (chore.overdue)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: Icon(Icons.warning_amber, size: 20, color: scheme.error),
                    )
                  else if (request != null)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: Icon(Icons.shopping_cart_outlined, size: 20, color: scheme.tertiary),
                    ),
                ],
              ),
              const SizedBox(height: 2),
              Text(lastDone),
              Text(due, style: TextStyle(color: thresholdOverdue(chore, DateTime.now()) ? warn : null)),
              if (request != null)
                _RequestBox(request: request, onEdit: onNeeded, onCancel: onCancelRequest),
              if (chore.inProgress != null)
                _StartBox(start: chore.inProgress!, onEdit: onStart, onStop: onStop),
              // Wrap, not OverflowBar: with four buttons on a narrow phone (or a big font)
              // only the last one moves to a second row instead of all of them stacking.
              Wrap(
                alignment: WrapAlignment.end,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 4,
                children: [
                  TextButton(onPressed: onHistory, child: const Text('History')),
                  TextButton(onPressed: onEdit, child: const Text('Edit')),
                  if (request == null && chore.active)
                    TextButton(onPressed: onNeeded, child: const Text('Needed')),
                  if (chore.inProgress == null && chore.active)
                    TextButton(onPressed: onStart, child: const Text('Start')),
                  FilledButton.tonalIcon(
                    icon: const Icon(Icons.check),
                    label: const Text('Done'),
                    onPressed: onDone,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// A chore in progress on its card: who and since when, its note, and Edit (join, take
/// over, change the time) / Stop.
class _StartBox extends StatelessWidget {
  const _StartBox({required this.start, required this.onEdit, required this.onStop});

  final ChoreStart start;
  final VoidCallback onEdit;
  final VoidCallback onStop;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return Container(
      margin: const EdgeInsets.only(top: 8, right: 8),
      padding: const EdgeInsets.fromLTRB(12, 8, 4, 0),
      decoration: BoxDecoration(
        color: scheme.secondaryContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.play_circle_outline, size: 18, color: scheme.onSecondaryContainer),
              const SizedBox(width: 6),
              Expanded(
                child: Text(startHeadText(context, start, DateTime.now()),
                    style: theme.textTheme.labelLarge?.copyWith(color: scheme.onSecondaryContainer)),
              ),
            ],
          ),
          if (start.notes != null)
            Text(start.notes!, style: TextStyle(color: scheme.onSecondaryContainer)),
          OverflowBar(
            alignment: MainAxisAlignment.end,
            children: [
              TextButton(onPressed: onEdit, child: const Text('Who / when')),
              TextButton(onPressed: onStop, child: const Text('Stop')),
            ],
          ),
        ],
      ),
    );
  }
}

/// Start a chore (who's doing it, default you; when, default now; a note), or edit the one
/// in progress ([initial]): add or remove people to join or take over, or change the time.
/// Starting posts to the chores Discord channel; editing doesn't. Pops the saved start.
class ChoreStartForm extends StatefulWidget {
  const ChoreStartForm({
    super.key,
    required this.api,
    required this.chore,
    required this.people,
    this.initial,
  });

  final Future<CatApi> Function() api;
  final Chore chore;
  final List<String> people;
  final ChoreStart? initial;

  @override
  State<ChoreStartForm> createState() => _ChoreStartFormState();
}

class _ChoreStartFormState extends State<ChoreStartForm> {
  late final TextEditingController _notes =
      TextEditingController(text: widget.initial?.notes ?? '');

  /// When it started; null = now (new starts only).
  late DateTime? _when = widget.initial?.startedOn;
  late final Set<String> _doers = widget.initial != null
      ? {...widget.initial!.doers}
      : {if (widget.people.contains(WhoAmI.current)) WhoAmI.current!};
  bool _busy = false;
  String? _error;

  bool get _editing => widget.initial != null;

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickWhen() async {
    final picked = await pickPastDateTime(context, _when,
        helpText: 'When did it start?', onError: (m) => setState(() => _error = m));
    if (picked != null) setState(() => _when = picked);
  }

  Future<void> _save() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final doers = [
      for (final p in widget.people) if (_doers.contains(p)) p,
      for (final p in _doers) if (!widget.people.contains(p)) p,
    ];
    try {
      final api = await widget.api();
      final i = widget.initial;
      final ChoreStart saved;
      if (i == null) {
        saved = await api.startChore(widget.chore.name,
            doers: doers, startedAt: _when, notes: _notes.text);
      } else {
        final notes = _notes.text.trim();
        saved = await api.editChoreStart(i.id, {
          'doers': doers,
          if (_when != null && _when != i.startedOn) 'started_at': _when,
          if (notes != (i.notes ?? '')) 'notes': notes,
        });
      }
      if (mounted) Navigator.of(context).pop(saved);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final when = _when;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: AbsorbPointer(
        absorbing: _busy,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_editing ? '${widget.chore.label} in progress' : 'Start ${widget.chore.label}',
                style: theme.textTheme.titleLarge),
            const SizedBox(height: 12),
            Text('Who is doing it', style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            if (widget.people.isEmpty)
              const Text("The server has no people set up (app_user.human), so who isn't recorded.")
            else
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  for (final p in {...widget.people, ..._doers})
                    FilterChip(
                      label: Text(p),
                      selected: _doers.contains(p),
                      onSelected: (on) => setState(() => on ? _doers.add(p) : _doers.remove(p)),
                    ),
                ],
              ),
            if (_editing)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Add someone to join; swap people to take over. The time it takes '
                    'still counts from the start.', style: theme.textTheme.bodySmall),
              ),
            const SizedBox(height: 12),
            Card.outlined(
              margin: EdgeInsets.zero,
              child: ListTile(
                leading: const Icon(Icons.schedule),
                title: const Text('Started'),
                subtitle: Text(when == null ? 'Now' : dayTimeText(context, when)),
                onTap: _pickWhen,
                trailing: when == null
                    ? const Icon(Icons.edit_calendar_outlined)
                    : (_editing
                        ? null
                        : TextButton(
                            onPressed: () => setState(() => _when = null),
                            child: const Text('Now'))),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _notes,
              minLines: 1,
              maxLines: 4,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Notes (optional)',
                hintText: 'e.g. kitchen first',
                border: OutlineInputBorder(),
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
              ),
            const SizedBox(height: 16),
            FilledButton.icon(
              icon: _busy
                  ? const SizedBox(
                      width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : Icon(_editing ? Icons.save_outlined : Icons.play_arrow),
              label: Text(_editing ? 'Save changes' : 'Start and tell Discord'),
              onPressed: _busy ? null : _save,
            ),
          ],
        ),
      ),
    );
  }
}

/// A chore's open request on its card: who asked and when, the details, and Edit / Cancel.
class _RequestBox extends StatelessWidget {
  const _RequestBox({required this.request, required this.onEdit, required this.onCancel});

  final ChoreRequest request;
  final VoidCallback onEdit;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final color = request.overdue ? scheme.onErrorContainer : scheme.onTertiaryContainer;
    return Container(
      margin: const EdgeInsets.only(top: 8, right: 8),
      padding: const EdgeInsets.fromLTRB(12, 8, 4, 0),
      decoration: BoxDecoration(
        color: request.overdue ? scheme.errorContainer : scheme.tertiaryContainer,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(requestHeadText(request, DateTime.now()),
              style: theme.textTheme.labelLarge?.copyWith(color: color)),
          for (final l in requestDetailLines(context, request))
            Text(l, style: TextStyle(color: color)),
          OverflowBar(
            alignment: MainAxisAlignment.end,
            children: [
              TextButton(onPressed: onEdit, child: const Text('Edit request')),
              TextButton(onPressed: onCancel, child: const Text('Cancel request')),
            ],
          ),
        ],
      ),
    );
  }
}

/// The "Needed" form in a bottom sheet: mark [chore] as needing to be done, or edit its
/// open request ([initial]). Returns the saved request, or null if closed without saving.
Future<ChoreRequest?> showChoreRequestSheet(
  BuildContext context, {
  required Future<CatApi> Function() api,
  required Chore chore,
  ChoreRequest? initial,
}) =>
    showModalBottomSheet<ChoreRequest>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
        // Keep the buttons above Android's navigation bar (edge-to-edge).
        child: SafeArea(
          top: false,
          child: ChoreRequestForm(api: api, chore: chore, initial: initial),
        ),
      ),
    );

/// Quantity (a number) and unit (free text), a "needed by" day (optional, today or later)
/// and a note. Saving a new one posts it to the chores Discord channel.
class ChoreRequestForm extends StatefulWidget {
  const ChoreRequestForm({super.key, required this.api, required this.chore, this.initial});

  final Future<CatApi> Function() api;
  final Chore chore;
  final ChoreRequest? initial;

  @override
  State<ChoreRequestForm> createState() => _ChoreRequestFormState();
}

class _ChoreRequestFormState extends State<ChoreRequestForm> {
  late final TextEditingController _quantity =
      TextEditingController(text: widget.initial?.quantityNumber ?? '');
  late final TextEditingController _unit = TextEditingController(text: widget.initial?.unit ?? '');
  late final TextEditingController _notes = TextEditingController(text: widget.initial?.notes ?? '');
  late DateTime? _neededBy = widget.initial?.neededBy;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _quantity.dispose();
    _unit.dispose();
    _notes.dispose();
    super.dispose();
  }

  Future<void> _pickDay() async {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final start = _neededBy;
    final picked = await showDatePicker(
      context: context,
      initialDate: start == null || start.isBefore(today) ? today : start,
      firstDate: today,
      lastDate: today.add(const Duration(days: 3650)),
      helpText: 'Needed by',
    );
    if (picked != null) setState(() => _neededBy = picked);
  }

  Future<void> _save() async {
    final qText = _quantity.text.trim().replaceAll(',', '.');
    final quantity = qText.isEmpty ? null : double.tryParse(qText);
    if (qText.isNotEmpty && (quantity == null || quantity <= 0)) {
      return setState(() => _error = 'Quantity must be a number above 0 (or blank).');
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = await widget.api();
      final i = widget.initial;
      final ChoreRequest saved;
      if (i == null) {
        saved = await api.addChoreRequest(widget.chore.name,
            notes: _notes.text, quantity: quantity, unit: _unit.text, neededBy: _neededBy);
      } else {
        final unit = _unit.text.trim(), notes = _notes.text.trim();
        saved = await api.editChoreRequest(i.id, {
          if (quantity != i.quantity) 'quantity': quantity,
          if (unit != (i.unit ?? '')) 'unit': unit,
          if (notes != (i.notes ?? '')) 'notes': notes,
          if (_neededBy != i.neededBy) 'needed_by': _neededBy,
        });
      }
      if (mounted) Navigator.of(context).pop(saved);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final day = _neededBy;
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: AbsorbPointer(
        absorbing: _busy,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('${widget.chore.label} needed', style: theme.textTheme.titleLarge),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _quantity,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]'))],
                    decoration: const InputDecoration(
                        labelText: 'Quantity (optional)', hintText: 'e.g. 2', border: OutlineInputBorder()),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextField(
                    controller: _unit,
                    maxLength: 30,
                    decoration: const InputDecoration(
                        labelText: 'Unit (optional)',
                        hintText: 'e.g. bags',
                        counterText: '',
                        border: OutlineInputBorder()),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Card.outlined(
              margin: EdgeInsets.zero,
              child: ListTile(
                leading: const Icon(Icons.event),
                title: const Text('Needed by'),
                subtitle: Text(day == null
                    ? 'No date (never overdue)'
                    : '${dayText(context, day)} (overdue after that day)'),
                onTap: _pickDay,
                trailing: day == null
                    ? const Icon(Icons.edit_calendar_outlined)
                    : TextButton(
                        onPressed: () => setState(() => _neededBy = null),
                        child: const Text('No date')),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _notes,
              minLines: 2,
              maxLines: 5,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Notes (optional)',
                hintText: 'e.g. Royal Canin renal, the small bags',
                border: OutlineInputBorder(),
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
              ),
            const SizedBox(height: 16),
            FilledButton.icon(
              icon: _busy
                  ? const SizedBox(
                      width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.save_outlined),
              label: Text(widget.initial == null ? 'Save and tell Discord' : 'Save changes'),
              onPressed: _busy ? null : _save,
            ),
          ],
        ),
      ),
    );
  }
}

/// Add a chore, or edit one ([initial]): its name, its reminder threshold in days (blank =
/// no reminder) and, when editing, whether it shows on the list. Pops the saved chore.
class ChoreDialog extends StatefulWidget {
  const ChoreDialog({super.key, required this.api, this.initial});

  final Future<CatApi> Function() api;
  final Chore? initial;

  @override
  State<ChoreDialog> createState() => _ChoreDialogState();
}

class _ChoreDialogState extends State<ChoreDialog> {
  late final TextEditingController _name =
      TextEditingController(text: widget.initial?.label ?? '');
  late final TextEditingController _days =
      TextEditingController(text: widget.initial?.warningThresholdDays?.toString() ?? '');
  late bool _active = widget.initial?.active ?? true;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _days.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    final daysText = _days.text.trim();
    final days = daysText.isEmpty ? null : int.tryParse(daysText);
    if (name.isEmpty) return setState(() => _error = 'Give the chore a name.');
    if (daysText.isNotEmpty && (days == null || days < 1)) {
      return setState(() => _error = 'Days must be a whole number, 1 or more (or blank).');
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = await widget.api();
      final c = widget.initial;
      final Chore saved;
      if (c == null) {
        saved = await api.addChore(name, days);
      } else {
        saved = await api.editChore(c.id, {
          if (name != c.label) 'label_name': name,
          if (days != c.warningThresholdDays) 'warning_threshold_days': days,
          if (_active != c.active) 'active': _active,
        });
      }
      if (mounted) Navigator.of(context).pop(saved);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: Text(widget.initial == null ? 'Add chore' : 'Edit chore'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _name,
              enabled: !_busy,
              autofocus: widget.initial == null,
              textCapitalization: TextCapitalization.words,
              decoration: const InputDecoration(
                  labelText: 'Name', hintText: 'e.g. Clean Fridge', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _days,
              enabled: !_busy,
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              decoration: const InputDecoration(
                labelText: 'Warn after (days)',
                helperText: 'Overdue this many days after it was last done.\nBlank = no reminder.',
                helperMaxLines: 2,
                border: OutlineInputBorder(),
              ),
            ),
            if (widget.initial != null)
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Show on the list'),
                subtitle: const Text('Off hides it. Its history is kept.'),
                value: _active,
                onChanged: _busy ? null : (v) => setState(() => _active = v),
              ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
            onPressed: _busy ? null : () => Navigator.of(context).pop(),
            child: const Text('Cancel')),
        FilledButton(onPressed: _busy ? null : _save, child: const Text('Save')),
      ],
    );
  }
}

/// The "Done" form in a bottom sheet: record [chore] as done (or edit [initial]). Returns
/// the saved event, or null if closed without saving.
Future<ChoreEvent?> showChoreEventSheet(
  BuildContext context, {
  required Future<CatApi> Function() api,
  required Chore? chore,
  required List<Chore> chores,
  required List<String> people,
  ChoreEvent? initial,
}) =>
    showModalBottomSheet<ChoreEvent>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => Padding(
        // Keep the form above the keyboard.
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom),
        // Keep the buttons above Android's navigation bar (edge-to-edge).
        child: SafeArea(
          top: false,
          child: ChoreEventForm(
              api: api, chore: chore, chores: chores, people: people, initial: initial),
        ),
      ),
    );

/// Record a chore as done: when (default now), who did it (default you, from "Who am I"),
/// and a note. When editing ([initial]) the chore itself can be changed too.
class ChoreEventForm extends StatefulWidget {
  const ChoreEventForm({
    super.key,
    required this.api,
    required this.chore,
    required this.chores,
    required this.people,
    this.initial,
  });

  final Future<CatApi> Function() api;
  final Chore? chore;
  final List<Chore> chores;
  final List<String> people;
  final ChoreEvent? initial;

  @override
  State<ChoreEventForm> createState() => _ChoreEventFormState();
}

class _ChoreEventFormState extends State<ChoreEventForm> {
  late final TextEditingController _notes =
      TextEditingController(text: widget.initial?.notes ?? '');
  late String? _chore = widget.initial?.chore ?? widget.chore?.name;

  /// When it was done; null = now (the moment Save is tapped).
  late DateTime? _when = widget.initial?.when;

  /// When it was started; null = not known. A new Done starts from the chore's start in
  /// progress, if any.
  late DateTime? _started =
      widget.initial != null ? widget.initial!.startedOn : widget.chore?.inProgress?.startedOn;

  /// Who did it: when editing, as saved; otherwise whoever started it, or you.
  late final Set<String> _doneBy = widget.initial != null
      ? {...widget.initial!.doneBy}
      : (widget.chore?.inProgress?.doers.isNotEmpty ?? false)
          ? {...widget.chore!.inProgress!.doers}
          : {if (widget.people.contains(WhoAmI.current)) WhoAmI.current!};
  bool _busy = false;
  String? _error;

  bool get _editing => widget.initial != null;

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  String _label(String name) =>
      widget.chores.where((c) => c.name == name).firstOrNull?.label ??
      widget.initial?.choreLabel ??
      name;

  Future<void> _pickWhen() async {
    final picked = await pickPastDateTime(context, _when,
        onError: (m) => setState(() => _error = m));
    if (picked != null) setState(() => _when = picked);
  }

  Future<void> _pickStarted() async {
    final picked = await pickPastDateTime(context, _started ?? _when,
        helpText: 'When did it start?', onError: (m) => setState(() => _error = m));
    if (picked != null) setState(() => _started = picked);
  }

  Future<void> _save() async {
    final chore = _chore;
    if (chore == null) return;
    final started = _started;
    if (started != null && started.isAfter(_when ?? DateTime.now())) {
      return setState(() => _error = 'The start time is after the done time. Change one of them.');
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    // In the people order, so the server and the list show them the same way.
    final doneBy = [
      for (final p in widget.people) if (_doneBy.contains(p)) p,
      for (final p in _doneBy) if (!widget.people.contains(p)) p,
    ];
    try {
      final api = await widget.api();
      final i = widget.initial;
      final ChoreEvent saved;
      if (i == null) {
        saved = await api.addChoreEvent(chore,
            when: _when, doneBy: doneBy, notes: _notes.text, startedAt: _started);
      } else {
        saved = await api.editChoreEvent(i.id, {
          if (chore != i.chore) 'chore': chore,
          if (_when != i.when) 'event_time': (_when ?? DateTime.now()).toUtc().toIso8601String(),
          'done_by': doneBy,
          'notes': _notes.text.trim(),
          if (_started != i.startedOn) 'started_at': _started?.toUtc().toIso8601String(),
        });
      }
      if (mounted) Navigator.of(context).pop(saved);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final when = _when;
    // Editing: any shown chore (and the event's own, even if it's hidden now).
    final choices = [
      for (final c in widget.chores)
        if (c.active || c.name == widget.initial?.chore) c.name,
      if (_chore != null && !widget.chores.any((c) => c.name == _chore)) _chore!,
    ];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
      child: AbsorbPointer(
        absorbing: _busy,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_editing)
              DropdownButtonFormField<String>(
                initialValue: _chore,
                decoration: const InputDecoration(labelText: 'Chore', border: OutlineInputBorder()),
                items: [
                  for (final n in choices) DropdownMenuItem(value: n, child: Text(_label(n))),
                ],
                onChanged: (v) => setState(() => _chore = v),
              )
            else
              Text('${_label(_chore ?? '')} done', style: theme.textTheme.titleLarge),
            if (!_editing && widget.chore?.request != null)
              Card(
                margin: const EdgeInsets.only(top: 12),
                color: theme.colorScheme.tertiaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(requestHeadText(widget.chore!.request!, DateTime.now()),
                          style: theme.textTheme.labelLarge),
                      for (final l in requestDetailLines(context, widget.chore!.request!)) Text(l),
                      const SizedBox(height: 4),
                      Text('Saving this closes the request.', style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 12),
            Card.outlined(
              margin: EdgeInsets.zero,
              child: ListTile(
                leading: const Icon(Icons.schedule),
                title: const Text('When'),
                subtitle: Text(when == null ? 'Now' : dayTimeText(context, when)),
                onTap: _pickWhen,
                trailing: when == null
                    ? const Icon(Icons.edit_calendar_outlined)
                    : (_editing
                        ? null
                        : TextButton(
                            onPressed: () => setState(() => _when = null),
                            child: const Text('Now'))),
              ),
            ),
            const SizedBox(height: 8),
            Card.outlined(
              margin: EdgeInsets.zero,
              child: ListTile(
                leading: const Icon(Icons.play_arrow_outlined),
                title: const Text('Started (optional)'),
                subtitle: Text(_started == null
                    ? 'Not recorded: no time taken'
                    : '${dayTimeText(context, _started!)}'
                        '${_started!.isAfter(when ?? DateTime.now()) ? '' : ' · took ${tookText((when ?? DateTime.now()).difference(_started!))}'}'),
                onTap: _pickStarted,
                trailing: _started == null
                    ? const Icon(Icons.edit_calendar_outlined)
                    : TextButton(
                        onPressed: () => setState(() => _started = null), child: const Text('Clear')),
              ),
            ),
            const SizedBox(height: 16),
            Text('Done by', style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            if (widget.people.isEmpty)
              const Text("The server has no people set up (app_user.human), so who did it isn't recorded.")
            else
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  for (final p in {...widget.people, ..._doneBy})
                    FilterChip(
                      label: Text(p),
                      selected: _doneBy.contains(p),
                      onSelected: (on) => setState(() => on ? _doneBy.add(p) : _doneBy.remove(p)),
                    ),
                ],
              ),
            if (_doneBy.isEmpty && widget.people.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Nobody picked: saved without who did it.',
                    style: theme.textTheme.bodySmall),
              ),
            const SizedBox(height: 16),
            TextField(
              controller: _notes,
              minLines: 2,
              maxLines: 5,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Notes (optional)',
                hintText: 'e.g. upstairs only, used the new detergent',
                border: OutlineInputBorder(),
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
              ),
            const SizedBox(height: 16),
            FilledButton.icon(
              icon: _busy
                  ? const SizedBox(
                      width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.save_outlined),
              label: Text(_editing ? 'Save changes' : 'Save'),
              onPressed: _busy || _chore == null ? null : _save,
            ),
          ],
        ),
      ),
    );
  }
}
