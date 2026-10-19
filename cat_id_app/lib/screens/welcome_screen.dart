import 'package:flutter/material.dart';

import '../server_store.dart';
import 'servers_screen.dart';

/// Shown until you have saved at least one server.
class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key, required this.store});

  final ServerStore store;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.pets, size: 72),
                const SizedBox(height: 16),
                Text('Cat ID', style: Theme.of(context).textTheme.headlineMedium),
                const SizedBox(height: 8),
                const Text(
                  "Add the address of your cat-id server to get started, e.g. 192.168.1.116. "
                  "You can save up to ${ServerStore.maxServers}.",
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                FilledButton.icon(
                  icon: const Icon(Icons.add),
                  label: const Text('Add a server'),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(
                      builder: (_) => ServersScreen(store: store, startWithAdd: true),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
