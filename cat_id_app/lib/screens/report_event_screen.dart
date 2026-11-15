import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../camera_recovery.dart';
import '../server_store.dart';

// Same colours as the label page (ui/label.css).
const _littenColor = Color(0xFFD62828);
const _shinxColor = Color(0xFFF4C20D);

/// What the sheet reports: a cough (POST /cough) or a litterbox visit (POST /litterbox
/// with `cat`).
enum ReportKind {
  cough('Who coughed?', 'e.g. after eating, lasted about 10 seconds'),
  litterbox('Who used the litterbox?', 'e.g. pee and poop, soft stool');

  const ReportKind(this.question, this.hint);
  final String question;
  final String hint;
}

/// Report an event by hand (the Events tab's Add event menu): choose Litten or Shinx, set
/// when it happened (default now; any past date and time), add a note and a photo if you
/// like, and the server records the event and posts it to
/// Discord. The photo also goes to the server's label queue and shows on the event in the
/// Events tab. The cat pictures are the same img_src/ files the label pages use, loaded
/// from the server's /asset/ route, so there is only one copy of them.
class ReportEventScreen extends StatefulWidget {
  const ReportEventScreen(
      {super.key, required this.store, required this.server, required this.kind});

  final ServerStore store;
  final Server server;
  final ReportKind kind;

  @override
  State<ReportEventScreen> createState() => _ReportEventScreenState();
}

class _ReportEventScreenState extends State<ReportEventScreen> {
  final _info = TextEditingController();
  String? _cat;
  bool _busy = false;
  String? _error;
  String? _sentFor;
  XFile? _photo;

  /// When it happened; null = now (the moment Send is tapped).
  DateTime? _when;

  @override
  void dispose() {
    _info.dispose();
    super.dispose();
  }

  String _assetUrl(String file) =>
      widget.server.baseUri.replace(path: '/asset/$file').toString();

  void _choose(String cat) {
    if (_busy) return;
    setState(() {
      _cat = cat;
      _error = null;
      _sentFor = null;
    });
  }

  Future<void> _pick(ImageSource source) async {
    try {
      // If Android closes the app while the camera is open, the photo comes back on the
      // Identify tab (camera_recovery.dart) rather than being lost.
      if (source == ImageSource.camera) await CameraRecovery.markOpened();
      final f = await ImagePicker()
          .pickImage(source: source, maxWidth: 1600, imageQuality: 90);
      if (source == ImageSource.camera) await CameraRecovery.markReturned();
      if (f == null || !mounted) return; // cancelled
      setState(() {
        _photo = f;
        _error = null;
        _sentFor = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error =
          'Could not open the ${source == ImageSource.camera ? 'camera' : 'gallery'}: $e');
    }
  }

  /// Date picker, then time picker. Today's date limits the time to now or earlier.
  Future<void> _pickWhen() async {
    final now = DateTime.now();
    final start = _when ?? now;
    final date = await showDatePicker(
      context: context,
      initialDate: start,
      firstDate: DateTime(2000),
      lastDate: now,
      helpText: 'When did it happen?',
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(start),
      helpText: 'At what time?',
    );
    if (time == null || !mounted) return;
    final picked = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    final later = DateTime.now();
    setState(() {
      _sentFor = null;
      if (picked.isAfter(later)) {
        _error = "That time hasn't happened yet. Pick now or earlier.";
      } else {
        _error = null;
        _when = picked;
      }
    });
  }

  /// "Now", or e.g. "Today, 2:41 PM" / "Yesterday, 11:05 PM" / "Nov 12, 2026, 8:00 AM".
  String _whenText(BuildContext context) {
    final when = _when;
    if (when == null) return 'Now';
    final loc = MaterialLocalizations.of(context);
    final time = loc.formatTimeOfDay(TimeOfDay.fromDateTime(when));
    final now = DateTime.now();
    final days = DateTime(now.year, now.month, now.day)
        .difference(DateTime(when.year, when.month, when.day))
        .inDays;
    final day = switch (days) {
      0 => 'Today',
      1 => 'Yesterday',
      _ => loc.formatMediumDate(when),
    };
    return '$day, $time';
  }

  Future<void> _send() async {
    final cat = _cat;
    if (cat == null || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
      _sentFor = null;
    });
    try {
      final key = await widget.store.keyFor(widget.server.id);
      final api = CatApi(widget.server, key);
      final photo = _photo?.path;
      switch (widget.kind) {
        case ReportKind.cough:
          await api.cough(cat, _info.text, photoPath: photo, when: _when);
        case ReportKind.litterbox:
          await api.litterbox(cat, _info.text, photoPath: photo, when: _when);
      }
      if (!mounted) return;
      setState(() {
        _sentFor = cat;
        _cat = null; // ready for the next report
        _info.clear();
        _photo = null;
        _when = null;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = e.message);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Something went wrong: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Optional photo: Gallery / Camera buttons, then a preview with a remove button.
  Widget _photoSection(ThemeData theme) {
    final photo = _photo;
    final buttons = Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            icon: const Icon(Icons.photo_library_outlined),
            label: Text(photo == null ? 'Add photo' : 'Change photo'),
            onPressed: _busy ? null : () => _pick(ImageSource.gallery),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton.icon(
            icon: const Icon(Icons.photo_camera_outlined),
            label: const Text('Camera'),
            onPressed: _busy ? null : () => _pick(ImageSource.camera),
          ),
        ),
      ],
    );
    if (photo == null) return buttons;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Stack(
          children: [
            Container(
              height: 200,
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(12),
              ),
              clipBehavior: Clip.antiAlias,
              alignment: Alignment.center,
              child: Image.file(File(photo.path), fit: BoxFit.contain),
            ),
            Positioned(
              top: 4,
              right: 4,
              child: IconButton.filledTonal(
                tooltip: 'Remove photo',
                icon: const Icon(Icons.close),
                onPressed: _busy ? null : () => setState(() => _photo = null),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        buttons,
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(widget.kind.question, style: theme.textTheme.titleMedium),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _CatTile(
                name: 'Litten',
                color: _littenColor,
                imageUrl: _assetUrl('litten_pokemon.png'),
                selected: _cat == 'Litten',
                dimmed: _cat != null && _cat != 'Litten',
                onTap: () => _choose('Litten'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _CatTile(
                name: 'Shinx',
                color: _shinxColor,
                imageUrl: _assetUrl('shinx_pokemon.png'),
                selected: _cat == 'Shinx',
                dimmed: _cat != null && _cat != 'Shinx',
                onTap: () => _choose('Shinx'),
              ),
            ),
          ],
        ),
        if (_cat != null) ...[
          const SizedBox(height: 16),
          Card.outlined(
            margin: EdgeInsets.zero,
            child: ListTile(
              leading: const Icon(Icons.schedule),
              title: const Text('When'),
              subtitle: Text(_whenText(context)),
              enabled: !_busy,
              onTap: _pickWhen,
              trailing: _when == null
                  ? const Icon(Icons.edit_calendar_outlined)
                  : TextButton(
                      onPressed: _busy ? null : () => setState(() => _when = null),
                      child: const Text('Now'),
                    ),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _info,
            enabled: !_busy,
            minLines: 3,
            maxLines: 6,
            textCapitalization: TextCapitalization.sentences,
            decoration: InputDecoration(
              labelText: 'Additional info (optional)',
              hintText: widget.kind.hint,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          _photoSection(theme),
        ],
        const SizedBox(height: 16),
        FilledButton.icon(
          icon: const Icon(Icons.send),
          label: const Text('Send to Discord'),
          onPressed: _cat == null || _busy ? null : _send,
        ),
        const SizedBox(height: 16),
        if (_busy) const Center(child: CircularProgressIndicator()),
        if (_error != null)
          Card(
            color: scheme.errorContainer,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Icon(Icons.error_outline, color: scheme.onErrorContainer),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(_error!, style: TextStyle(color: scheme.onErrorContainer)),
                  ),
                ],
              ),
            ),
          ),
        if (_sentFor != null)
          Card(
            child: ListTile(
              leading: const Icon(Icons.check_circle, color: Colors.greenAccent),
              title: Text("Sent to Discord for $_sentFor"),
            ),
          ),
      ],
    );
  }
}

/// A big square button: the cat's picture on its label-page colour, with the name at the bottom.
class _CatTile extends StatelessWidget {
  const _CatTile({
    required this.name,
    required this.color,
    required this.imageUrl,
    required this.selected,
    required this.dimmed,
    required this.onTap,
  });

  final String name;
  final Color color;
  final String imageUrl;
  final bool selected;
  final bool dimmed;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(16);
    return Opacity(
      opacity: dimmed ? 0.45 : 1.0,
      child: AspectRatio(
        aspectRatio: 1,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          decoration: BoxDecoration(
            borderRadius: radius,
            border: Border.all(color: Colors.white, width: selected ? 4 : 0),
          ),
          child: Material(
            color: color,
            borderRadius: radius,
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onTap,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(8, 8, 8, 28),
                    child: Image.network(
                      imageUrl,
                      fit: BoxFit.contain,
                      // No picture (server unreachable or art missing): the colour and name still work.
                      errorBuilder: (_, __, ___) =>
                          const Center(child: Icon(Icons.pets, size: 48, color: Colors.white70)),
                    ),
                  ),
                  Align(
                    alignment: Alignment.bottomCenter,
                    child: Padding(
                      padding: const EdgeInsets.all(8),
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: Colors.black.withAlpha(184),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                          child: Text(
                            name,
                            style: const TextStyle(color: Colors.white, fontSize: 16),
                          ),
                        ),
                      ),
                    ),
                  ),
                  if (selected)
                    const Positioned(
                      top: 8,
                      right: 8,
                      child: Icon(Icons.check_circle, color: Colors.white, size: 28),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
