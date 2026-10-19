import 'package:flutter/material.dart';

import '../api.dart';
import '../server_store.dart';

// Same colours as the label page (ui/label.css).
const _littenColor = Color(0xFFD62828);
const _shinxColor = Color(0xFFF4C20D);

/// Report a cough: choose Litten or Shinx, add a note if you like, and the server posts
/// it to Discord (POST /cough). The pictures are the same img_src/ files the label pages
/// use, loaded from the server's /asset/ route, so there is only one copy of them.
class CoughScreen extends StatefulWidget {
  const CoughScreen({super.key, required this.store, required this.server});

  final ServerStore store;
  final Server server;

  @override
  State<CoughScreen> createState() => _CoughScreenState();
}

class _CoughScreenState extends State<CoughScreen> {
  final _info = TextEditingController();
  String? _cat;
  bool _busy = false;
  String? _error;
  String? _sentFor;

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
      await CatApi(widget.server, key).cough(cat, _info.text);
      if (!mounted) return;
      setState(() {
        _sentFor = cat;
        _cat = null; // ready for the next report
        _info.clear();
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
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Who coughed?', style: theme.textTheme.titleMedium),
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
          TextField(
            controller: _info,
            enabled: !_busy,
            minLines: 3,
            maxLines: 6,
            textCapitalization: TextCapitalization.sentences,
            decoration: const InputDecoration(
              labelText: 'Additional info (optional)',
              hintText: 'e.g. after eating, lasted about 10 seconds',
              border: OutlineInputBorder(),
            ),
          ),
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
