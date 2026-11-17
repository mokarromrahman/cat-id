package local.catid.cat_id_app

import android.content.Intent
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    /** In-app updates (see AppInstaller.kt and lib/app_update.dart). */
    private var installer: AppInstaller? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val inst = AppInstaller(this)
        installer = inst
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, AppInstaller.CHANNEL)
            .setMethodCallHandler(inst)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Android restarted the activity to deliver an install status (rare).
        if (intent?.action == AppInstaller.ACTION_STATUS) installer?.onInstallStatus(intent)
    }

    // Android reports the install's progress by starting this (singleTop) activity again.
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        installer?.onInstallStatus(intent)
    }
}
