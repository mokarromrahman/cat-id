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
  if (c.overdue || !now.isBefore(due)) return 'Overdue by ${spanText(now.difference(due))} $every';
  return 'Due in ${spanText(due.difference(now))} $every';
}

/// Overdue first (never done, then the longest overdue), then the ones with a reminder by
/// how soon they're due, then the rest in the server's order.
List<Chore> sortChores(List<Chore> chores) {
  int group(Chore c) => c.overdue ? 0 : (c.dueAt != null ? 1 : 2);
  final indexed = chores.indexed.toList();
  indexed.sort((a, b) {
    final (ia, ca) = a;
    final (ib, cb) = b;
    final g = group(ca).compareTo(group(cb));
    if (g != 0) return g;
    if (group(ca) < 2) {
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

/// Date picker, then time picker, for something that already happened. Null if cancelled;
/// a time later than now is refused with a message.
Future<DateTime?> pickPastDateTime(BuildContext context, DateTime? initial,
    {required void Function(String) onError}) async {
  final now = DateTime.now();
  final start = initial ?? now;
  final date = await showDatePicker(
    context: context,
    initialDate: start.isAfter(now) ? now : start,
    firstDate: DateTime(2000),
    lastDate: now,
    helpText: 'When was it done?',
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
                      : overdue == 0
                          ? 'Nothing overdue.'
                          : '$overdue overdue',
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
  });

  final Chore chore;
  final String lastDone;
  final String due;
  final VoidCallback onDone;
  final VoidCallback onHistory;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final warn = chore.overdue ? scheme.error : null;
    return Opacity(
      opacity: chore.active ? 1 : 0.55,
      child: Card(
        margin: const EdgeInsets.only(bottom: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: warn ?? scheme.outlineVariant, width: chore.overdue ? 2 : 1),
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
                    ),
                ],
              ),
              const SizedBox(height: 2),
              Text(lastDone),
              Text(due, style: TextStyle(color: warn)),
              OverflowBar(
                alignment: MainAxisAlignment.end,
                spacing: 4,
                children: [
                  TextButton(onPressed: onHistory, child: const Text('History')),
                  TextButton(onPressed: onEdit, child: const Text('Edit')),
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
        child: ChoreEventForm(
            api: api, chore: chore, chores: chores, people: people, initial: initial),
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
  late final Set<String> _doneBy = widget.initial != null
      ? {...widget.initial!.doneBy}
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

  Future<void> _save() async {
    final chore = _chore;
    if (chore == null) return;
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
        saved = await api.addChoreEvent(chore, when: _when, doneBy: doneBy, notes: _notes.text);
      } else {
        saved = await api.editChoreEvent(i.id, {
          if (chore != i.chore) 'chore': chore,
          if (_when != i.when) 'event_time': (_when ?? DateTime.now()).toUtc().toIso8601String(),
          'done_by': doneBy,
          'notes': _notes.text.trim(),
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
