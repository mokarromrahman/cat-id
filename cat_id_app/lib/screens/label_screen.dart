import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../server_store.dart';
import '../who_am_i.dart';

/// Shows the server's own /label page: the same page you get in a browser, with
/// labelling, crop, rotate, undo, history, delete and Retrain. Changes to that page
/// show up here without updating the app.
class LabelScreen extends StatefulWidget {
  const LabelScreen({super.key, required this.server});

  final Server server;

  @override
  State<LabelScreen> createState() => _LabelScreenState();
}

class _LabelScreenState extends State<LabelScreen> {
  late final WebViewController _controller;
  int _progress = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF111111))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (_) {
            if (mounted) setState(() => _error = null);
          },
          onProgress: (p) {
            if (mounted) setState(() => _progress = p);
          },
          onWebResourceError: (e) {
            // Ignore failures of small things on the page; only a failed page matters.
            if (e.isForMainFrame != false && mounted) {
              setState(() => _error =
                  "Can't reach ${widget.server.address}. Is the server running, and is this phone on the home Wi-Fi?");
            }
          },
        ),
      )
      // ?user= tells the page who is labeling (see who_am_i.dart); it records it on each label.
      ..loadRequest(widget.server.baseUri.replace(
          path: '/label',
          queryParameters: WhoAmI.current == null ? null : {'user': WhoAmI.current!}));
  }

  @override
  Widget build(BuildContext context) {
    final error = _error;
    return Column(
      children: [
        if (_progress < 100 && error == null) LinearProgressIndicator(value: _progress / 100),
        Expanded(
          child: error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(error, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          icon: const Icon(Icons.refresh),
                          label: const Text('Try again'),
                          onPressed: () {
                            setState(() => _error = null);
                            _controller.reload();
                          },
                        ),
                      ],
                    ),
                  ),
                )
              : WebViewWidget(controller: _controller),
        ),
      ],
    );
  }
}
