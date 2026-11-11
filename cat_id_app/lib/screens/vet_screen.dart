import 'package:flutter/material.dart';

import '../api.dart';
import '../server_store.dart';

// Same colours as the label page (ui/label.css) and the Cough tab.
const _littenColor = Color(0xFFD62828);
const _shinxColor = Color(0xFFF4C20D);

/// Pre-filled on new visits; you can change it. A blank clinic is stored as "unknown".
const kDefaultClinic = 'Millwoods East Veterinary Clinic';

/// The reasons the server accepts (vet_visit.reason), in the order they're shown.
const kReasons = ['checkup', 'shots', 'emergency', 'food pickup', 'medication pickup', 'other'];

enum _CatChoice { litten, shinx, both, none }

extension on _CatChoice {
  String get label => switch (this) {
        _CatChoice.litten => 'Litten',
        _CatChoice.shinx => 'Shinx',
        _CatChoice.both => 'Both',
        _CatChoice.none => 'No cat',
      };

  /// The cats this choice saves visits for (null = a visit not for one cat).
  List<String?> get cats => switch (this) {
        _CatChoice.litten => ['Litten'],
        _CatChoice.shinx => ['Shinx'],
        _CatChoice.both => ['Litten', 'Shinx'],
        _CatChoice.none => [null],
      };
}

_CatChoice _choiceFor(String? cat) => switch (cat) {
      'Litten' => _CatChoice.litten,
      'Shinx' => _CatChoice.shinx,
      _ => _CatChoice.none,
    };

Color? _catColor(String? cat) => switch (cat) {
      'Litten' => _littenColor,
      'Shinx' => _shinxColor,
      _ => null,
    };

String _two(int n) => n.toString().padLeft(2, '0');
String _isoDate(DateTime d) => '${d.year}-${_two(d.month)}-${_two(d.day)}';
const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
String _niceDate(DateTime d) => '${_weekdays[d.weekday - 1]}, ${_months[d.month - 1]} ${d.day}, ${d.year}';

String? _hhmm(TimeOfDay? t) => t == null ? null : '${_two(t.hour)}:${_two(t.minute)}';
TimeOfDay? _parseTime(String? s) {
  final m = RegExp(r'^(\d{1,2}):(\d{2})').firstMatch(s ?? '');
  return m == null ? null : TimeOfDay(hour: int.parse(m.group(1)!), minute: int.parse(m.group(2)!));
}

String _numText(double? v) {
  if (v == null) return '';
  return v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toString();
}

/// The Vet tab: a form to add a visit, and the list of visits underneath (edit, delete,
/// restore). Talks to the server's /vet_visit routes; nothing is kept on the phone, so if
/// the server can't be reached it shows the error and nothing is saved.
class VetScreen extends StatefulWidget {
  const VetScreen({super.key, required this.store, required this.server});

  final ServerStore store;
  final Server server;

  @override
  State<VetScreen> createState() => _VetScreenState();
}

class _VetScreenState extends State<VetScreen> {
  List<VetVisit>? _visits;
  String? _error;
  bool _loading = false;
  bool _showDeleted = false;

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
      final visits = await (await _api()).vetVisits(includeDeleted: _showDeleted);
      if (!mounted) return;
      setState(() => _visits = visits);
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

  Future<void> _edit(VetVisit v) async {
    final saved = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => Scaffold(
        appBar: AppBar(title: const Text('Edit visit')),
        body: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Builder(
              builder: (context) => VetVisitForm(
                api: _api,
                initial: v,
                onSaved: (_) => Navigator.of(context).pop(true),
              ),
            ),
          ],
        ),
      ),
    ));
    if (saved == true) {
      if (mounted) _toast('Visit updated.');
      _load();
    }
  }

  Future<void> _delete(VetVisit v) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this visit?'),
        content: Text(
            '${v.cat ?? 'No cat'} · ${_niceDate(v.visitDate)}\n\nYou can bring it back with "Show deleted" and Restore.'),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    await _change(() async => (await _api()).deleteVetVisit(v.id), 'Visit deleted.');
  }

  Future<void> _restore(VetVisit v) =>
      _change(() async => (await _api()).restoreVetVisit(v.id), 'Visit restored.');

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
    final visits = _visits;
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('New visit', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          VetVisitForm(
            api: _api,
            onSaved: (saved) {
              _toast(saved.length == 2 ? 'Saved 2 visits (Litten and Shinx).' : 'Visit saved.');
              _load();
            },
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              Expanded(child: Text('Visits', style: theme.textTheme.titleMedium)),
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
          if (_loading && visits == null) const Center(child: CircularProgressIndicator()),
          if (_error != null)
            Card(
              color: theme.colorScheme.errorContainer,
              child: ListTile(
                leading: Icon(Icons.error_outline, color: theme.colorScheme.onErrorContainer),
                title: Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
                trailing: IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
              ),
            ),
          if (visits != null && visits.isEmpty && _error == null)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 24),
              child: Text('No visits yet. Add the first one above.', textAlign: TextAlign.center),
            ),
          if (visits != null)
            for (final v in visits)
              _VisitCard(
                visit: v,
                onEdit: () => _edit(v),
                onDelete: () => _delete(v),
                onRestore: () => _restore(v),
              ),
        ],
      ),
    );
  }
}

class _VisitCard extends StatelessWidget {
  const _VisitCard({
    required this.visit,
    required this.onEdit,
    required this.onDelete,
    required this.onRestore,
  });

  final VetVisit visit;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onRestore;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final v = visit;
    final color = _catColor(v.cat) ?? theme.colorScheme.outline;
    final time = _parseTime(v.appointmentTime);
    final lines = <String>[
      [v.clinic, if (v.doctor != null) v.doctor!].join(' · '),
      v.reason.join(', '),
      [
        if (v.weightKg != null) '${_numText(v.weightKg)} kg',
        if (v.cost != null) '\$${v.cost!.toStringAsFixed(2)}',
        if (v.followUpDate != null) 'follow-up ${_niceDate(v.followUpDate!)}',
      ].join(' · '),
      if (v.notes != null) v.notes!,
      'Added by ${v.reporter ?? 'unknown'}'
          '${v.modifiedBy != null && v.modifiedBy != v.reporter ? ' · last changed by ${v.modifiedBy}' : ''}',
    ].where((l) => l.isNotEmpty);

    return Opacity(
      opacity: v.deleted ? 0.55 : 1,
      child: Card(
        margin: const EdgeInsets.only(bottom: 12),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: color, width: 2),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${v.cat ?? 'No cat'} · ${_niceDate(v.visitDate)}'
                      '${time != null ? ' · ${time.format(context)}' : ''}',
                      style: theme.textTheme.titleSmall,
                    ),
                  ),
                  if (v.deleted)
                    Chip(label: const Text('Deleted'), visualDensity: VisualDensity.compact),
                ],
              ),
              const SizedBox(height: 4),
              for (final l in lines)
                Padding(padding: const EdgeInsets.only(bottom: 2), child: Text(l)),
              Align(
                alignment: Alignment.centerRight,
                child: v.deleted
                    ? TextButton.icon(
                        icon: const Icon(Icons.restore), label: const Text('Restore'), onPressed: onRestore)
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          TextButton.icon(
                              icon: const Icon(Icons.edit_outlined), label: const Text('Edit'), onPressed: onEdit),
                          TextButton.icon(
                              icon: const Icon(Icons.delete_outline), label: const Text('Delete'), onPressed: onDelete),
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

/// The fields entered for each cat (for "Both", one set per cat).
class _PerCat {
  _PerCat([VetVisit? v])
      : reasons = {...?v?.reason},
        weight = TextEditingController(text: _numText(v?.weightKg)),
        cost = TextEditingController(text: v?.cost?.toStringAsFixed(2) ?? ''),
        notes = TextEditingController(text: v?.notes ?? ''),
        followUp = v?.followUpDate;

  final Set<String> reasons;
  final TextEditingController weight;
  final TextEditingController cost;
  final TextEditingController notes;
  DateTime? followUp;

  void dispose() {
    weight.dispose();
    cost.dispose();
    notes.dispose();
  }
}

/// Add a visit (or two, for "Both"), or edit one when [initial] is given.
class VetVisitForm extends StatefulWidget {
  const VetVisitForm({super.key, required this.api, required this.onSaved, this.initial});

  final Future<CatApi> Function() api;
  final void Function(List<VetVisit> saved) onSaved;
  final VetVisit? initial;

  @override
  State<VetVisitForm> createState() => _VetVisitFormState();
}

class _VetVisitFormState extends State<VetVisitForm> {
  late _CatChoice _choice;
  late DateTime _date;
  TimeOfDay? _time;
  late final TextEditingController _clinic;
  late final TextEditingController _doctor;

  /// One entry per cat in [_choice].cats (two for "Both").
  late List<_PerCat> _perCat;
  bool _busy = false;
  String? _error;

  bool get _editing => widget.initial != null;

  @override
  void initState() {
    super.initState();
    final v = widget.initial;
    _choice = v == null ? _CatChoice.litten : _choiceFor(v.cat);
    _date = v?.visitDate ?? DateTime.now();
    _time = _parseTime(v?.appointmentTime);
    _clinic = TextEditingController(text: v == null ? kDefaultClinic : (v.clinic == 'unknown' ? '' : v.clinic));
    _doctor = TextEditingController(text: v?.doctor ?? '');
    _perCat = [_PerCat(v)];
  }

  @override
  void dispose() {
    _clinic.dispose();
    _doctor.dispose();
    for (final p in _perCat) {
      p.dispose();
    }
    super.dispose();
  }

  void _setChoice(_CatChoice c) {
    setState(() {
      _choice = c;
      // Keep what's typed in the first set; add or drop the second for "Both".
      while (_perCat.length < c.cats.length) {
        _perCat.add(_PerCat());
      }
      while (_perCat.length > c.cats.length) {
        _perCat.removeLast().dispose();
      }
    });
  }

  void _reset() {
    setState(() {
      _date = DateTime.now();
      _time = null;
      _clinic.text = kDefaultClinic;
      _doctor.clear();
      for (final p in _perCat) {
        p.dispose();
      }
      _perCat = [for (final _ in _choice.cats) _PerCat()];
      _error = null;
    });
  }

  Future<DateTime?> _pickDate(DateTime? initial) => showDatePicker(
        context: context,
        initialDate: initial ?? DateTime.now(),
        firstDate: DateTime(2023),
        lastDate: DateTime(DateTime.now().year + 3, 12, 31),
      );

  /// A number field's text, or null when empty. Throws a message when it isn't a number.
  String? _number(TextEditingController c, String what, String? cat) {
    final s = c.text.trim().replaceAll(',', '.').replaceAll('\$', '');
    if (s.isEmpty) return null;
    final n = double.tryParse(s);
    if (n == null || n < 0) throw '${cat ?? 'Visit'}: $what must be a number like 4.35';
    return s;
  }

  Map<String, dynamic> _visitJson(String? cat, _PerCat p) => {
        'cat': cat,
        'visit_date': _isoDate(_date),
        'appointment_time': _hhmm(_time),
        'clinic': _clinic.text.trim(),
        'doctor': _doctor.text.trim(),
        'reason': [for (final r in kReasons) if (p.reasons.contains(r)) r],
        'weight_kg': _number(p.weight, 'weight', cat),
        'cost': _number(p.cost, 'cost', cat),
        'follow_up_date': p.followUp == null ? null : _isoDate(p.followUp!),
        'notes': p.notes.text.trim(),
      };

  Future<void> _save() async {
    final cats = _choice.cats;
    final List<Map<String, dynamic>> visits;
    try {
      for (var i = 0; i < cats.length; i++) {
        if (_perCat[i].reasons.isEmpty) {
          throw 'Pick at least one reason${cats.length > 1 ? ' for ${cats[i]}' : ''}.';
        }
      }
      visits = [for (var i = 0; i < cats.length; i++) _visitJson(cats[i], _perCat[i])];
    } on String catch (message) {
      setState(() => _error = message);
      return;
    }

    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = await widget.api();
      final saved = _editing
          ? [await api.editVetVisit(widget.initial!.id, visits.single)]
          : await api.addVetVisits(visits);
      if (!mounted) return;
      if (!_editing) _reset();
      widget.onSaved(saved);
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
    final choices = _editing
        ? const [_CatChoice.litten, _CatChoice.shinx, _CatChoice.none]
        : _CatChoice.values;
    final cats = _choice.cats;

    return AbsorbPointer(
      absorbing: _busy,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SegmentedButton<_CatChoice>(
            segments: [
              for (final c in choices) ButtonSegment(value: c, label: Text(c.label)),
            ],
            selected: {_choice},
            showSelectedIcon: false,
            onSelectionChanged: (s) => _setChoice(s.single),
          ),
          if (_choice == _CatChoice.none)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('For pickups or anything not for one cat.', style: theme.textTheme.bodySmall),
            ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.event),
                  label: Text(_niceDate(_date)),
                  onPressed: () async {
                    final d = await _pickDate(_date);
                    if (d != null) setState(() => _date = d);
                  },
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.schedule),
                  label: Text(_time == null ? 'No time' : _time!.format(context)),
                  onPressed: () async {
                    final t = await showTimePicker(
                        context: context, initialTime: _time ?? const TimeOfDay(hour: 9, minute: 0));
                    if (t != null) setState(() => _time = t);
                  },
                ),
              ),
              if (_time != null)
                IconButton(
                  tooltip: 'Clear the time',
                  icon: const Icon(Icons.clear),
                  onPressed: () => setState(() => _time = null),
                ),
            ],
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _clinic,
            decoration: const InputDecoration(
              labelText: 'Clinic',
              helperText: 'Left blank, it is saved as "unknown".',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _doctor,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(labelText: 'Doctor (optional)', border: OutlineInputBorder()),
          ),
          for (var i = 0; i < cats.length; i++) _catSection(theme, cats[i], _perCat[i], cats.length > 1),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
            ),
          const SizedBox(height: 16),
          FilledButton.icon(
            icon: _busy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.save),
            label: Text(_editing ? 'Save changes' : (cats.length == 2 ? 'Save 2 visits' : 'Save visit')),
            onPressed: _busy ? null : _save,
          ),
        ],
      ),
    );
  }

  Widget _catSection(ThemeData theme, String? cat, _PerCat p, bool titled) {
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (titled)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(cat ?? 'No cat',
                  style: theme.textTheme.titleSmall?.copyWith(color: _catColor(cat))),
            ),
          Text('Reasons', style: theme.textTheme.labelLarge),
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final r in kReasons)
                FilterChip(
                  label: Text(r),
                  selected: p.reasons.contains(r),
                  onSelected: (on) => setState(() => on ? p.reasons.add(r) : p.reasons.remove(r)),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: p.weight,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Weight', suffixText: 'kg', border: OutlineInputBorder()),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: p.cost,
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                      labelText: 'Cost', prefixText: '\$ ', border: OutlineInputBorder()),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  icon: const Icon(Icons.event_repeat),
                  label: Text(p.followUp == null ? 'No follow-up date' : 'Follow-up ${_niceDate(p.followUp!)}'),
                  onPressed: () async {
                    final d = await _pickDate(p.followUp);
                    if (d != null) setState(() => p.followUp = d);
                  },
                ),
              ),
              if (p.followUp != null)
                IconButton(
                  tooltip: 'Clear the follow-up date',
                  icon: const Icon(Icons.clear),
                  onPressed: () => setState(() => p.followUp = null),
                ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            controller: p.notes,
            minLines: 2,
            maxLines: 5,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
              labelText: 'Notes (optional)',
              hintText: 'e.g. what "other" means, test results, medication',
              border: OutlineInputBorder(),
            ),
          ),
        ],
      ),
    );
  }
}
