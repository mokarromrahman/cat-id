import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../api.dart';
import '../camera_recovery.dart';
import '../server_store.dart';

/// Pick or take a photo, then ask the server who it is.
///  - "Identify" calls /identify (JSON only).
///  - "Identify + send to Discord" calls /litterbox (same, and posts to Discord).
class IdentifyScreen extends StatefulWidget {
  const IdentifyScreen(
      {super.key, required this.store, required this.server, this.recoveredPhoto});

  final ServerStore store;
  final Server server;

  /// A camera photo recovered after Android closed the app (see camera_recovery.dart).
  final LostDataResponse? recoveredPhoto;

  @override
  State<IdentifyScreen> createState() => _IdentifyScreenState();
}

class _IdentifyScreenState extends State<IdentifyScreen> {
  XFile? _photo;
  bool _busy = false;
  IdentifyResult? _result;
  bool _resultWentToDiscord = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _useRecovered(widget.recoveredPhoto);
  }

  @override
  void didUpdateWidget(IdentifyScreen old) {
    super.didUpdateWidget(old);
    if (widget.recoveredPhoto != old.recoveredPhoto) {
      setState(() => _useRecovered(widget.recoveredPhoto));
    }
  }

  void _useRecovered(LostDataResponse? lost) {
    if (lost == null) return;
    if (lost.file != null) {
      _photo = lost.file;
      _result = null;
      _error = null;
    } else if (lost.exception != null) {
      _error = 'Could not get the photo from the camera: ${lost.exception!.message}';
    }
  }

  Future<void> _pick(ImageSource source) async {
    try {
      if (source == ImageSource.camera) await CameraRecovery.markOpened();
      // Shrinking here makes the upload quick; the model only looks at a small version anyway.
      final f = await ImagePicker()
          .pickImage(source: source, maxWidth: 1600, imageQuality: 90);
      if (source == ImageSource.camera) await CameraRecovery.markReturned();
      if (f == null) return; // cancelled
      setState(() {
        _photo = f;
        _result = null;
        _error = null;
      });
    } catch (e) {
      setState(() => _error =
          'Could not open the ${source == ImageSource.camera ? 'camera' : 'gallery'}: $e');
    }
  }

  Future<void> _run({required bool discord}) async {
    final photo = _photo;
    if (photo == null || _busy) return;
    setState(() {
      _busy = true;
      _result = null;
      _error = null;
    });
    try {
      final key = await widget.store.keyFor(widget.server.id);
      final r = await CatApi(widget.server, key)
          .identify(photo.path, sendToDiscord: discord);
      if (!mounted) return;
      setState(() {
        _result = r;
        _resultWentToDiscord = discord;
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

  @override
  Widget build(BuildContext context) {
    final photo = _photo;
    final theme = Theme.of(context);

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          height: 260,
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(12),
          ),
          clipBehavior: Clip.antiAlias,
          alignment: Alignment.center,
          child: photo == null
              ? const Text('No photo yet')
              : Image.file(File(photo.path), fit: BoxFit.contain),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                icon: const Icon(Icons.photo_library_outlined),
                label: const Text('Gallery'),
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
        ),
        const SizedBox(height: 16),
        FilledButton.icon(
          icon: const Icon(Icons.search),
          label: const Text('Identify'),
          onPressed: photo == null || _busy ? null : () => _run(discord: false),
        ),
        const SizedBox(height: 8),
        FilledButton.tonalIcon(
          icon: const Icon(Icons.send),
          label: const Text('Identify + send to Discord'),
          onPressed: photo == null || _busy ? null : () => _run(discord: true),
        ),
        const SizedBox(height: 8),
        Text(
          "Either way, the server keeps the photo in its inbox so you can label it later.",
          style: theme.textTheme.bodySmall,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 16),
        if (_busy) const Center(child: CircularProgressIndicator()),
        if (_error != null) _ErrorCard(message: _error!),
        if (_result != null) _ResultCard(result: _result!, discord: _resultWentToDiscord),
      ],
    );
  }
}

class _ResultCard extends StatelessWidget {
  const _ResultCard({required this.result, required this.discord});

  final IdentifyResult result;
  final bool discord;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pct = (result.confidence * 100).round();
    final String title;
    final String subtitle;
    if (result.cat == 'uncertain') {
      title = 'Not sure';
      subtitle = 'Best guess: ${result.bestGuess} ($pct%)';
    } else if (result.cat == 'neither') {
      title = 'No cat in the photo';
      subtitle = '$pct% sure';
    } else {
      title = result.cat;
      subtitle = '$pct% sure';
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: theme.textTheme.headlineMedium),
            const SizedBox(height: 4),
            Text(subtitle, style: theme.textTheme.titleMedium),
            const SizedBox(height: 12),
            LinearProgressIndicator(value: result.confidence),
            const SizedBox(height: 12),
            Text(discord ? 'Also posted to Discord.' : 'Not posted to Discord.'),
            Text('Saved as ${result.savedAs}', style: theme.textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: scheme.onErrorContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Text(message, style: TextStyle(color: scheme.onErrorContainer)),
            ),
          ],
        ),
      ),
    );
  }
}
