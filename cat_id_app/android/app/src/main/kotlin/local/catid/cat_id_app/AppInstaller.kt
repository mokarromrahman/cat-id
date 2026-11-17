package local.catid.cat_id_app

import android.app.Activity
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.security.MessageDigest

/**
 * Installs an app update the app downloaded itself (lib/app_update.dart), through Android's
 * PackageInstaller session API, so the app learns how it ended (installed, cancelled, or
 * failed and why). Android always shows its own "Update this app?" screen.
 *
 * Methods on the "cat_id/app_installer" channel:
 * - downloadDir: a folder in the app's cache for the APK
 * - canInstall: is "Install unknown apps" allowed for this app
 * - openInstallSettings: opens that setting for this app
 * - install(path, sha256): checks the file's SHA-256, then installs it. Answers
 *   {"status": installed | cancelled | checksum | conflict | storage | incompatible |
 *   invalid | blocked | failed, "message": Android's detail or null}.
 *
 * Android reports back by starting MainActivity with [ACTION_STATUS] (see onNewIntent):
 * first "needs the person's OK" (we show Android's confirm screen), then the result.
 */
class AppInstaller(private val activity: Activity) : MethodChannel.MethodCallHandler {
    companion object {
        const val CHANNEL = "cat_id/app_installer"
        const val ACTION_STATUS = "local.catid.cat_id_app.INSTALL_STATUS"
    }

    private val main = Handler(Looper.getMainLooper())

    /** The Dart call waiting for the install to end. */
    private var pending: MethodChannel.Result? = null

    override fun onMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "downloadDir" -> {
                val dir = File(activity.cacheDir, "updates").apply { mkdirs() }
                result.success(dir.absolutePath)
            }
            "canInstall" -> result.success(
                Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
                    activity.packageManager.canRequestPackageInstalls()
            )
            "openInstallSettings" -> {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    activity.startActivity(
                        Intent(
                            Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                            Uri.parse("package:${activity.packageName}")
                        )
                    )
                }
                result.success(null)
            }
            "install" -> {
                val path = call.argument<String>("path")
                val sha256 = call.argument<String>("sha256")
                if (path == null || sha256 == null) {
                    result.error("bad_args", "path and sha256 are needed", null)
                } else {
                    install(File(path), sha256, result)
                }
            }
            else -> result.notImplemented()
        }
    }

    private fun install(file: File, sha256: String, result: MethodChannel.Result) {
        // Android sometimes says nothing when its confirm screen is dismissed, so a new try
        // ends the old one instead of being refused.
        answer("cancelled", null)
        pending = result
        Thread {
            try {
                if (!sha256Of(file).equals(sha256, ignoreCase = true)) {
                    main.post { answer("checksum", null) }
                    return@Thread
                }
                val installer = activity.packageManager.packageInstaller
                val params = PackageInstaller.SessionParams(
                    PackageInstaller.SessionParams.MODE_FULL_INSTALL
                ).apply { setAppPackageName(activity.packageName) }
                val id = installer.createSession(params)
                installer.openSession(id).use { session ->
                    session.openWrite("cat-id.apk", 0, file.length()).use { out ->
                        file.inputStream().use { it.copyTo(out) }
                        session.fsync(out)
                    }
                    val intent = Intent(activity, MainActivity::class.java).setAction(ACTION_STATUS)
                    // Mutable: Android adds the status to it. Explicit (component set), as
                    // Android 14 requires for a mutable PendingIntent.
                    val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                        (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0)
                    val sender = PendingIntent.getActivity(activity, id, intent, flags)
                    session.commit(sender.intentSender)
                }
            } catch (e: Exception) {
                main.post { answer("failed", e.message) }
            }
        }.start()
    }

    /** Called by MainActivity with each status Android sends for the session. */
    fun onInstallStatus(intent: Intent) {
        if (intent.action != ACTION_STATUS) return
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm: Intent? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    intent.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(Intent.EXTRA_INTENT)
                }
                if (confirm == null) {
                    answer("failed", "Android didn't show its install screen")
                } else {
                    activity.startActivity(confirm)
                }
            }
            PackageInstaller.STATUS_SUCCESS -> answer("installed", null)
            PackageInstaller.STATUS_FAILURE_ABORTED -> answer("cancelled", null)
            PackageInstaller.STATUS_FAILURE_CONFLICT -> answer("conflict", message)
            PackageInstaller.STATUS_FAILURE_STORAGE -> answer("storage", message)
            PackageInstaller.STATUS_FAILURE_INCOMPATIBLE -> answer("incompatible", message)
            PackageInstaller.STATUS_FAILURE_INVALID -> answer("invalid", message)
            PackageInstaller.STATUS_FAILURE_BLOCKED -> answer("blocked", message)
            else -> answer("failed", message)
        }
    }

    /** Answers the waiting Dart call, if there is one. Main thread only. */
    private fun answer(status: String, message: String?) {
        val r = pending ?: return
        pending = null
        r.success(mapOf("status" to status, "message" to message))
    }

    private fun sha256Of(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(1 shl 16)
            while (true) {
                val n = input.read(buffer)
                if (n < 0) break
                digest.update(buffer, 0, n)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
