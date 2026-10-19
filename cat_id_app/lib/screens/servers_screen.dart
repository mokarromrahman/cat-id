import 'package:flutter/material.dart';

import '../server_store.dart';

/// Add, edit, remove and choose between up to 5 servers.
class ServersScreen extends StatefulWidget {
  const ServersScreen({super.key, required this.store, this.startWithAdd = false});

  final ServerStore store;

  /// Open the "add" form straight away (used the first time the app runs).
  final bool startWithAdd;

  @override
  State<ServersScreen> createState() => _ServersScreenState();
}

class _ServersScreenState extends State<ServersScreen> {
  ServerStore get _store => widget.store;

  @override
  void initState() {
    super.initState();
    if (widget.startWithAdd) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _showEditor();
      });
    }
  }

  Future<void> _showEditor({Server? existing}) async {
    if (existing == null && _store.isFull) {
      _snack('You can save up to ${ServerStore.maxServers} servers. Remove one first.');
      return;
    }
    // Show the saved key so editing a server keeps it unless you change it.
    final existingKey = existing == null ? '' : await _store.keyFor(existing.id);
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => _ServerDialog(store: _store, existing: existing, existingKey: existingKey),
    );
  }

  Future<void> _confirmRemove(Server s) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Remove ${s.label}?'),
        content: const Text('Its saved API key is deleted from this phone too.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Remove')),
        ],
      ),
    );
    if (yes == true) await _store.remove(s.id);
  }

  void _snack(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _store,
      builder: (context, _) {
        final servers = _store.servers;
        final selectedId = _store.selected?.id;
        return Scaffold(
          appBar: AppBar(title: Text('Servers (${servers.length}/${ServerStore.maxServers})')),
          floatingActionButton: FloatingActionButton.extended(
            icon: const Icon(Icons.add),
            label: const Text('Add'),
            onPressed: _showEditor,
          ),
          body: servers.isEmpty
              ? const Center(child: Text('No servers saved.'))
              : ListView.separated(
                  padding: const EdgeInsets.only(bottom: 88),
                  itemCount: servers.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final s = servers[i];
                    final isSelected = s.id == selectedId;
                    return ListTile(
                      leading: Icon(isSelected ? Icons.check_circle : Icons.circle_outlined),
                      title: Text(s.label),
                      subtitle: s.name.isEmpty ? null : Text(s.address),
                      onTap: () {
                        _store.select(s.id);
                        Navigator.of(context).maybePop();
                      },
                      trailing: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          IconButton(
                            tooltip: 'Edit',
                            icon: const Icon(Icons.edit_outlined),
                            onPressed: () => _showEditor(existing: s),
                          ),
                          IconButton(
                            tooltip: 'Remove',
                            icon: const Icon(Icons.delete_outline),
                            onPressed: () => _confirmRemove(s),
                          ),
                        ],
                      ),
                    );
                  },
                ),
        );
      },
    );
  }
}

class _ServerDialog extends StatefulWidget {
  const _ServerDialog({required this.store, required this.existing, required this.existingKey});

  final ServerStore store;
  final Server? existing;
  final String existingKey;

  @override
  State<_ServerDialog> createState() => _ServerDialogState();
}

class _ServerDialogState extends State<_ServerDialog> {
  late final TextEditingController _name;
  late final TextEditingController _address;
  late final TextEditingController _key;
  bool _showKey = false;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: widget.existing?.name ?? '');
    _address = TextEditingController(text: widget.existing?.address ?? '');
    _key = TextEditingController(text: widget.existingKey);
  }

  @override
  void dispose() {
    _name.dispose();
    _address.dispose();
    _key.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    final existing = widget.existing;
    final err = existing == null
        ? await widget.store.add(name: _name.text, address: _address.text, apiKey: _key.text)
        : await widget.store.update(existing.id,
            name: _name.text, address: _address.text, apiKey: _key.text);
    if (!mounted) return;
    if (err == null) {
      Navigator.of(context).pop();
    } else {
      setState(() {
        _saving = false;
        _error = err;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.existing == null ? 'Add a server' : 'Edit server'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: _name,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                labelText: 'Name (optional)',
                hintText: 'Home server',
              ),
            ),
            TextField(
              controller: _address,
              autofocus: widget.existing == null,
              autocorrect: false,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'IP address',
                hintText: '192.168.1.116 (port 8000 if left out)',
              ),
            ),
            TextField(
              controller: _key,
              obscureText: !_showKey,
              autocorrect: false,
              enableSuggestions: false,
              decoration: InputDecoration(
                labelText: 'API key',
                helperText: 'Stored encrypted on this phone. Leave empty if the server has none.',
                helperMaxLines: 2,
                suffixIcon: IconButton(
                  tooltip: _showKey ? 'Hide' : 'Show',
                  icon: Icon(_showKey ? Icons.visibility_off : Icons.visibility),
                  onPressed: () => setState(() => _showKey = !_showKey),
                ),
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _saving ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: const Text('Save'),
        ),
      ],
    );
  }
}
