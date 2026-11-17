import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

/// In-app updates. The server has the newest APK per channel (GET /app_update, filled by
/// deploy.yml); the phone never talks to GitHub, so this works with a private repo.
/// - Health tab: an Update button, only when the server has a newer full release
///   ([healthUpdateOffer]) and this isn't a dev build.
/// - Settings page: the installed version, "Show prereleases" ([UpdatePrefs]) and its offer
///   ([prereleaseOffer]), and "Install latest release" on a dev build.
/// Both run [startAppUpdate]: what's new, then the download, then Android's own install
/// screen (through [ApkInstaller], our Kotlin code in MainActivity / AppInstaller.kt).

/// The release tag this APK was built from (apk.yml passes --dart-define=CAT_ID_VERSION).
const String _builtVersion = String.fromEnvironment('CAT_ID_VERSION');

/// The installed app's version, e.g. "v1.4.4"; empty for a dev build (flutter run or a
/// local build). Tests set it.
String installedAppVersion = _builtVersion;

/// Built without a release version (on the Mac): never offered updates on Health.
bool get isDevBuild => AppVersion.tryParse(installedAppVersion) == null;

/// A release version: v1.4.4 or v1.5.0-test (the "v" is optional). Ordered like semantic
/// versions: numbers first, and a prerelease comes before its full release
/// (1.5.0-test < 1.5.0 < 1.5.1).
class AppVersion implements Comparable<AppVersion> {
  AppVersion._(this.major, this.minor, this.patch, this.pre);

  static final _pattern = RegExp(r'^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$');

  static AppVersion? tryParse(String text) {
    final m = _pattern.firstMatch(text.trim());
    if (m == null) return null;
    return AppVersion._(int.parse(m.group(1)!), int.parse(m.group(2)!),
        int.parse(m.group(3)!), m.group(4)?.split('.') ?? const []);
  }

  final int major, minor, patch;

  /// The part after the dash, split on dots; empty for a full release.
  final List<String> pre;

  bool get isPrerelease => pre.isNotEmpty;

  @override
  int compareTo(AppVersion o) {
    for (final (a, b) in [(major, o.major), (minor, o.minor), (patch, o.patch)]) {
      if (a != b) return a.compareTo(b);
    }
    if (pre.isEmpty || o.pre.isEmpty) {
      return pre.isEmpty == o.pre.isEmpty ? 0 : (pre.isEmpty ? 1 : -1);
    }
    for (var i = 0; i < pre.length && i < o.pre.length; i++) {
      final a = int.tryParse(pre[i]), b = int.tryParse(o.pre[i]);
      final c = a != null && b != null
          ? a.compareTo(b)
          : a != null
              ? -1 // numbers before words
              : b != null
                  ? 1
                  : pre[i].compareTo(o.pre[i]);
      if (c != 0) return c;
    }
    return pre.length.compareTo(o.pre.length);
  }

  bool operator >(AppVersion o) => compareTo(o) > 0;
}

/// The Health tab's offer: the server's full release, if it's newer than [installed]
/// (default: this app). Never for a dev build, never a prerelease.
AppUpdateInfo? healthUpdateOffer(AppUpdates updates, {String? installed}) {
  final mine = AppVersion.tryParse(installed ?? installedAppVersion);
  final release = updates.release;
  final theirs = release == null ? null : AppVersion.tryParse(release.version);
  if (mine == null || theirs == null || theirs.isPrerelease || !(theirs > mine)) return null;
  return release;
}

/// The Settings page's prerelease offer (only when "Show prereleases" is on): the server's
/// prerelease, if it's newer than [installed] (any, for a dev build) and newer than the
/// server's full release (an older prerelease is pointless once its release is out).
AppUpdateInfo? prereleaseOffer(AppUpdates updates, {String? installed}) {
  final pre = updates.prerelease;
  final theirs = pre == null ? null : AppVersion.tryParse(pre.version);
  if (theirs == null) return null;
  final mine = AppVersion.tryParse(installed ?? installedAppVersion);
  if (mine != null && !(theirs > mine)) return null;
  final release = updates.release == null ? null : AppVersion.tryParse(updates.release!.version);
  if (release != null && !(theirs > release)) return null;
  return pre;
}

/// "64.2 MB".
String sizeText(int bytes) => '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';

/// The per-phone "Show prereleases" setting (Settings page). Off by default.
class UpdatePrefs {
  static const _key = 'show_prereleases';

  static Future<bool> showPrereleases() async {
    try {
      return (await SharedPreferences.getInstance()).getBool(_key) ?? false;
    } catch (_) {
      return false;
    }
  }

  static Future<void> setShowPrereleases(bool on) async =>
      (await SharedPreferences.getInstance()).setBool(_key, on);
}

/// How an install ended. `installed` is rarely seen: Android closes the app to replace it.
enum InstallStatus { installed, cancelled, failed }

class InstallOutcome {
  const InstallOutcome(this.status, [this.message]);
  final InstallStatus status;

  /// Why it failed, worded for the person.
  final String? message;
}

/// Hands a downloaded APK to Android's installer. [instance] is the real one (Kotlin, see
/// android/.../AppInstaller.kt); tests replace it.
abstract class ApkInstaller {
  static ApkInstaller instance = const AndroidApkInstaller();

  /// A folder the app can download the APK into (the app's cache).
  Future<String> downloadDir();

  /// Is cat-id allowed to install apps ("Install unknown apps" > Allow from this source)?
  Future<bool> canInstall();

  /// Opens that Android setting for cat-id.
  Future<void> openInstallSettings();

  /// Checks the file's SHA-256, then asks Android to install it (Android shows its own
  /// "Update this app?" screen). Completes when the install ends, or with "cancelled" when
  /// the person backs out.
  Future<InstallOutcome> install(String path, String sha256);
}

class AndroidApkInstaller implements ApkInstaller {
  const AndroidApkInstaller();

  static const _channel = MethodChannel('cat_id/app_installer');

  @override
  Future<String> downloadDir() async => (await _channel.invokeMethod<String>('downloadDir'))!;

  @override
  Future<bool> canInstall() async => await _channel.invokeMethod<bool>('canInstall') ?? false;

  @override
  Future<void> openInstallSettings() => _channel.invokeMethod<void>('openInstallSettings');

  @override
  Future<InstallOutcome> install(String path, String sha256) async {
    try {
      final r = await _channel
          .invokeMapMethod<String, dynamic>('install', {'path': path, 'sha256': sha256});
      return outcomeFrom(r?['status'] as String?, r?['message'] as String?);
    } on PlatformException catch (e) {
      return InstallOutcome(InstallStatus.failed, 'The update failed: ${e.message ?? e.code}');
    }
  }
}

/// Words the Kotlin side's status for the person.
@visibleForTesting
InstallOutcome outcomeFrom(String? status, String? detail) {
  final extra = detail == null || detail.isEmpty ? '' : ' ($detail)';
  return switch (status) {
    'installed' => const InstallOutcome(InstallStatus.installed),
    'cancelled' => const InstallOutcome(InstallStatus.cancelled),
    'checksum' => const InstallOutcome(InstallStatus.failed,
        "The download was damaged (its checksum doesn't match), so it wasn't installed. Try again."),
    'conflict' => InstallOutcome(InstallStatus.failed,
        'Android refused the update: it is signed with a different key, or older than the '
        'installed app$extra.'),
    'storage' => const InstallOutcome(
        InstallStatus.failed, 'Not enough free storage on this phone to install the update.'),
    'incompatible' => const InstallOutcome(
        InstallStatus.failed, "This version doesn't work on this phone's Android version."),
    'invalid' => InstallOutcome(
        InstallStatus.failed, "Android couldn't read the downloaded APK$extra. Try again."),
    'blocked' =>
      InstallOutcome(InstallStatus.failed, 'Android blocked the install$extra.'),
    _ => InstallOutcome(InstallStatus.failed, 'The update failed$extra.'),
  };
}

/// The whole update: what's new (with Update / Not now), the one-time "allow installs"
/// step, the download with a progress bar, then Android's install screen. [title] defaults
/// to "Update to vX.Y.Z". Problems end as a snackbar.
Future<void> startAppUpdate(BuildContext context, CatApi api, AppUpdateInfo update,
    {String? title}) async {
  final go = await showDialog<bool>(
    context: context,
    builder: (context) => _WhatsNewDialog(update: update, title: title),
  );
  if (go != true || !context.mounted) return;
  if (!await _ensureInstallAllowed(context) || !context.mounted) return;
  final message = await showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _UpdateProgressDialog(api: api, update: update),
  );
  if (message != null && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }
}

/// Android asks once per phone whether cat-id may install apps. Explain it, open the
/// setting, and check again when the person comes back.
Future<bool> _ensureInstallAllowed(BuildContext context) async {
  final installer = ApkInstaller.instance;
  if (await installer.canInstall()) return true;
  if (!context.mounted) return false;
  final open = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Allow Kitten Dex to install updates'),
      content: const Text(
          'Android asks once on each phone. On the next screen, turn on "Allow from this '
          'source", then come back here and the update continues.'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
        FilledButton(
            onPressed: () => Navigator.pop(ctx, true), child: const Text('Open settings')),
      ],
    ),
  );
  if (open != true) return false;
  final back = Completer<void>();
  final listener = AppLifecycleListener(onResume: () {
    if (!back.isCompleted) back.complete();
  });
  try {
    await installer.openInstallSettings();
    await back.future;
  } finally {
    listener.dispose();
  }
  if (await installer.canInstall()) return true;
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Updates need "Allow from this source" turned on for Kitten Dex.')));
  }
  return false;
}

class _WhatsNewDialog extends StatelessWidget {
  const _WhatsNewDialog({required this.update, this.title});

  final AppUpdateInfo update;
  final String? title;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final pre = AppVersion.tryParse(update.version)?.isPrerelease ?? false;
    return AlertDialog(
      title: Text(title ?? 'Update to ${update.version}'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${sizeText(update.size)} download', style: theme.textTheme.bodySmall),
            if (pre) ...[
              const SizedBox(height: 8),
              Text('This is a prerelease: a test version that may have problems.',
                  style: TextStyle(color: theme.colorScheme.tertiary)),
            ],
            const SizedBox(height: 12),
            Text("What's new", style: theme.textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(update.notes.isEmpty ? 'No release notes.' : update.notes),
            const SizedBox(height: 16),
            Text(
              'Kitten Dex closes when the update is installed. Open it again afterwards. '
              'Your servers, keys and settings are kept.',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Not now')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Update')),
      ],
    );
  }
}

/// Downloads the APK, then hands it to Android. Pops with a message for a snackbar, or
/// null (cancelled by the person, or nothing to say).
class _UpdateProgressDialog extends StatefulWidget {
  const _UpdateProgressDialog({required this.api, required this.update});

  final CatApi api;
  final AppUpdateInfo update;

  @override
  State<_UpdateProgressDialog> createState() => _UpdateProgressDialogState();
}

class _UpdateProgressDialogState extends State<_UpdateProgressDialog> {
  int _received = 0;
  bool _installing = false;
  bool _closed = false;

  @override
  void initState() {
    super.initState();
    _run();
  }

  void _close([String? message]) {
    if (_closed || !mounted) return;
    _closed = true;
    Navigator.of(context).pop(message);
  }

  Future<void> _run() async {
    final installer = ApkInstaller.instance;
    File? file;
    try {
      file = File('${await installer.downloadDir()}/cat-id-update.apk');
      await widget.api.downloadApk(widget.update, file,
          onProgress: (n) {
            if (mounted) setState(() => _received = n);
          },
          cancelled: () => _closed);
      if (_closed) return;
      setState(() => _installing = true);
      final outcome = await installer.install(file.path, widget.update.sha256);
      // Installed: Android closes the app, so this is rarely reached.
      _close(switch (outcome.status) {
        InstallStatus.installed => null,
        InstallStatus.cancelled => 'Update cancelled.',
        InstallStatus.failed => outcome.message,
      });
    } on DownloadCancelled {
      // The person closed the dialog.
    } on ApiException catch (e) {
      _close(e.message);
    } catch (e) {
      _close('The update failed: $e');
    } finally {
      // Free the space unless Android is (or was) installing from it.
      if (!_installing) {
        try {
          if (file != null && file.existsSync()) file.deleteSync();
        } catch (_) {}
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = widget.update.size;
    return PopScope(
      canPop: false,
      child: AlertDialog(
        title: Text(_installing ? 'Installing ${widget.update.version}' : 'Downloading ${widget.update.version}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: _installing
              ? const [
                  LinearProgressIndicator(),
                  SizedBox(height: 12),
                  Text("Confirm the update on Android's screen. Kitten Dex closes when it's "
                      'installed; open it again afterwards.'),
                ]
              : [
                  LinearProgressIndicator(value: size > 0 ? _received / size : null),
                  const SizedBox(height: 12),
                  Text('${sizeText(_received)} of ${sizeText(size)}'),
                ],
        ),
        actions: [
          TextButton(
            onPressed: () => _close(),
            child: Text(_installing ? 'Close' : 'Cancel'),
          ),
        ],
      ),
    );
  }
}
