import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import 'server_store.dart';

/// An error with a message that is fine to show to the user.
class ApiException implements Exception {
  ApiException(this.message);
  final String message;

  @override
  String toString() => message;
}

/// What /identify and /litterbox send back.
class IdentifyResult {
  IdentifyResult.fromJson(Map<String, dynamic> j)
      : cat = j['cat'] as String,
        bestGuess = j['best_guess'] as String,
        confidence = (j['confidence'] as num).toDouble(),
        savedAs = j['saved_as'] as String;

  /// Litten / Shinx / neither / "uncertain" (best guess was below the server's MIN_CONF).
  final String cat;
  final String bestGuess;
  final double confidence;
  final String savedAs;
}

/// Talks to one cat-id server. The /label page is shown in a web view instead (see
/// screens/label_screen.dart), so it is not here.
class CatApi {
  CatApi(this.server, this.apiKey);

  final Server server;
  final String apiKey;

  Uri _uri(String path) => server.baseUri.replace(path: path);

  /// GET /health
  Future<Map<String, dynamic>> health() async {
    final r = await _guard(
        () => http.get(_uri('/health')).timeout(const Duration(seconds: 10)));
    return _json(r);
  }

  /// POST /identify, or POST /litterbox (same, plus a post to Discord).
  /// Either way the server also saves the photo in its inbox for later labeling.
  Future<IdentifyResult> identify(String photoPath,
      {required bool sendToDiscord}) async {
    final r = await _guard(() async {
      final req = http.MultipartRequest(
          'POST', _uri(sendToDiscord ? '/litterbox' : '/identify'))
        ..fields['key'] = apiKey
        ..files.add(await http.MultipartFile.fromPath('file', photoPath));
      final streamed = await req.send().timeout(const Duration(seconds: 90));
      return http.Response.fromStream(streamed);
    });
    return IdentifyResult.fromJson(_json(r));
  }

  /// POST /cough: the server posts a cough report to its Discord channel.
  /// [info] is optional; the server fills in "No additional info." when it is left out.
  Future<void> cough(String cat, String info) async {
    final r = await _guard(() async {
      final req = http.MultipartRequest('POST', _uri('/cough'))
        ..fields['cat'] = cat
        ..fields['key'] = apiKey;
      if (info.trim().isNotEmpty) req.fields['info'] = info.trim();
      final streamed = await req.send().timeout(const Duration(seconds: 30));
      return http.Response.fromStream(streamed);
    });
    if (r.statusCode == 200) {
      dynamic body;
      try {
        body = jsonDecode(utf8.decode(r.bodyBytes));
      } catch (_) {
        body = null;
      }
      if (body is Map) return;
      // The server answers 200 with nothing when COUGH_DISCORD_WEBHOOK isn't set.
      throw ApiException(
          'The server took it, but has no cough Discord webhook set, so nothing was posted.');
    }
    _json(r); // not 200: throws the matching error
  }

  /// POST /api/retrain. Trains again on the server's data/ folder; takes a few minutes.
  Future<void> retrain() async {
    final r = await _guard(() =>
        http.post(_uri('/api/retrain')).timeout(const Duration(minutes: 20)));
    _json(r);
  }

  Future<http.Response> _guard(Future<http.Response> Function() call) async {
    try {
      return await call();
    } on TimeoutException {
      throw ApiException('${server.address} took too long to answer.');
    } on SocketException {
      throw _unreachable();
    } on http.ClientException {
      throw _unreachable();
    }
  }

  ApiException _unreachable() => ApiException(
      "Can't reach ${server.address}. Is the server running, and is this phone on the home Wi-Fi?");

  Map<String, dynamic> _json(http.Response r) {
    dynamic body;
    try {
      body = jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      body = null;
    }
    if (r.statusCode != 200) {
      final detail = body is Map ? (body['detail'] ?? body['error']) : null;
      throw ApiException(_explain(r.statusCode, detail?.toString()));
    }
    if (body is! Map<String, dynamic>) {
      throw ApiException('The server sent something unexpected.');
    }
    return body;
  }

  String _explain(int code, String? detail) {
    switch (code) {
      case 401:
        return 'Wrong API key for this server. Fix it under Servers.';
      case 503:
        return "The model isn't trained yet. Train it on the server first.";
      case 400:
        return "The server couldn't read that as an image.";
      case 409:
        return 'Retraining is already running.';
      default:
        final d = detail == null || detail.isEmpty ? '' : ': $detail';
        final shown = d.length > 300 ? '${d.substring(0, 300)}…' : d;
        return 'Server error ($code)$shown';
    }
  }
}
