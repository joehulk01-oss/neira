package com.neira.remote

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.KeyEvent
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.ConsoleMessage
import android.webkit.JavascriptInterface
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.util.Log
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast

/**
 * Neira Remote — fase 1 (WebView wrapper).
 *
 * Memuat halaman remote-control milik Neira Gateway (web/index.html):
 * pairing via QR/token, kirim perintah, lihat log & status Neira di PC.
 * Kredensial device disimpan oleh halaman web di localStorage WebView.
 *
 * Alamat gateway disimpan di SharedPreferences; ganti lewat menu "Ganti alamat gateway".
 */
class MainActivity : Activity() {

    companion object {
        private const val PREFS = "neira"
        private const val KEY_URL = "gateway_url"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_DEVICE_KEY = "device_key"
        private const val REQ_PERMS = 101
        private const val REQ_FILES = 102
    }

    /**
     * Vault kredensial pairing di SharedPreferences (native) — TIDAK terikat
     * origin seperti localStorage WebView. Efeknya: pairing cukup SEKALI dan
     * tetap sah selamanya (ikut walau IP/port gateway berubah), sampai user
     * menekan LOGOUT atau menghapus data. Halaman web memanggil lewat
     * window.NeiraNative.* (fallback browser = localStorage).
     */
    private inner class NativeBridge {
        @JavascriptInterface
        fun getDeviceId(): String = prefs.getString(KEY_DEVICE_ID, "") ?: ""

        @JavascriptInterface
        fun getDeviceKey(): String = prefs.getString(KEY_DEVICE_KEY, "") ?: ""

        @JavascriptInterface
        fun saveDevice(id: String?, key: String?) {
            prefs.edit()
                .putString(KEY_DEVICE_ID, id ?: "")
                .putString(KEY_DEVICE_KEY, key ?: "")
                .apply()
        }

        @JavascriptInterface
        fun clearDevice() {
            prefs.edit()
                .remove(KEY_DEVICE_ID)
                .remove(KEY_DEVICE_KEY)
                .apply()
        }
    }

    private lateinit var web: WebView
    private lateinit var progress: ProgressBar
    private lateinit var fabSettings: TextView
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingPermission: PermissionRequest? = null

    private val prefs by lazy { getSharedPreferences(PREFS, MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Debug WebView dari PC (chrome://inspect / CDP via adb forward) — diagnosa mic.
        WebView.setWebContentsDebuggingEnabled(true)

        val root = FrameLayout(this)
        web = WebView(this)
        progress = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal)
        progress.isIndeterminate = true
        progress.visibility = View.GONE

        root.addView(
            web,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        )
        root.addView(
            progress,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                8
            )
        )

        // Tombol Setelan native — SELALU tampil di atas WebView, bahkan saat
        // halaman gagal dimuat (IP salah / PC mati). Menu opsi tidak tampil di
        // theme NoActionBar, jadi tombol melayang ini adalah jalur utama setelan:
        // edit alamat/IP gateway + masukkan kode pairing ulang (repair).
        fabSettings = TextView(this)
        fabSettings.text = "⚙️"
        fabSettings.textSize = 20f
        fabSettings.gravity = Gravity.CENTER
        fabSettings.setPadding(24, 14, 24, 14)
        val fabBg = GradientDrawable()
        fabBg.shape = GradientDrawable.OVAL
        fabBg.setColor(0xCC0A0E14.toInt())
        fabSettings.background = fabBg
        fabSettings.contentDescription = "Setelan koneksi"
        val fabLp = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.TOP or Gravity.END
        )
        fabLp.topMargin = 28
        fabLp.rightMargin = 28
        root.addView(fabSettings, fabLp)
        fabSettings.setOnClickListener { showSettingsDialog() }

        setContentView(root)

        setupWebView()

        var saved = prefs.getString(KEY_URL, "") ?: ""
        // Migrasi halus build lama: port 8765 → 8000 DAN paksa skema https://.
        // Gateway lokal (uvicorn :8000) HANYA melayani TLS — http://<IP>:8000
        // menyebabkan ERR_CONNECTION_REFUSED / "halaman tidak tersedia" di APK,
        // walau browser PC tetap bisa membukanya (browser otomatis upgrade/retry).
        // Benarkan HANYA untuk host privat/localhost (domain VPS jangan disentuh).
        if (isPrivateHost(saved) || saved.contains(":8000") || saved.contains(":8765")) {
            if (saved.contains(":8765")) saved = saved.replace(":8765", ":8000")
            if (saved.startsWith("http://")) {
                saved = "https://" + saved.removePrefix("http://")
            }
            prefs.edit().putString(KEY_URL, saved).apply()
        }
        if (saved.isBlank()) {
            askGatewayUrl(firstRun = true)
        } else {
            web.loadUrl(saved)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun setupWebView() {
        val s = web.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true                 // localStorage: kredensial device pairing
        s.mediaPlaybackRequiresUserGesture = false // suara Neira bisa langsung terdengar
        s.cacheMode = WebSettings.LOAD_DEFAULT
        // Gateway lokal dilayani https (TLS) — jangan biarkan WebView memblokirnya
        // sebagai mixed content saat halaman memakai http:// di dalam.
        s.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE

        // Jembatan JS → native untuk vault kredensial (pairing permanen lintas origin).
        web.addJavascriptInterface(NativeBridge(), "NeiraNative")

        web.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                progress.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                progress.visibility = View.GONE
            }

            // Gateway lokal (port 8000) memakai sertifikat self-signed —
            // izinkan agar halaman tetap dimuat sebagai https (secure origin → mic OK).
            // Cert IP LAN juga sudah dipercaya via res/xml/network_security_config.xml.
            override fun onReceivedSslError(
                view: WebView?,
                handler: SslErrorHandler?,
                error: android.net.http.SslError?
            ) {
                // Cadangan bila cert belum di-sync: terima self-signed gateway lokal
                // di :8000 (port lama :8765 tetap dikenali agar APK lama tidak mati).
                if (error != null &&
                    (error.url.contains(":8000") || error.url.contains(":8765"))
                ) {
                    handler?.proceed()
                } else {
                    handler?.cancel()
                }
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    Toast.makeText(
                        this@MainActivity,
                        "Gagal memuat gateway — tap ⚙️ untuk ganti alamat/IP gateway",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }

        web.webChromeClient = object : WebChromeClient() {

            // Izin mic/kamera untuk getUserMedia di halaman web (push-to-talk, scan QR).
            override fun onPermissionRequest(request: PermissionRequest?) {
                if (request == null) return
                val needed = mutableListOf<String>()
                if (request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE) &&
                    checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                    != PackageManager.PERMISSION_GRANTED
                ) {
                    needed.add(Manifest.permission.RECORD_AUDIO)
                }
                if (request.resources.contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE) &&
                    checkSelfPermission(Manifest.permission.CAMERA)
                    != PackageManager.PERMISSION_GRANTED
                ) {
                    needed.add(Manifest.permission.CAMERA)
                }

                if (needed.isEmpty()) {
                    request.grant(request.resources)
                } else {
                    pendingPermission = request
                    requestPermissions(needed.toTypedArray(), REQ_PERMS)
                }
            }

            // Unggah file dari halaman web (fitur upload dashboard).
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: WebChromeClient.FileChooserParams?
            ): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = filePathCallback
                val intent = fileChooserParams?.createIntent() ?: return false
                return try {
                    @Suppress("DEPRECATION")
                    startActivityForResult(intent, REQ_FILES)
                    true
                } catch (e: Exception) {
                    fileCallback = null
                    false
                }
            }

            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progress.progress = newProgress
                progress.visibility =
                    if (newProgress in 0..99) View.VISIBLE else View.GONE
            }

            // Console halaman web → logcat (tag NeiraWeb) untuk diagnosa.
            override fun onConsoleMessage(consoleMessage: ConsoleMessage?): Boolean {
                if (consoleMessage != null) {
                    Log.d(
                        "NeiraWeb",
                        "${consoleMessage.messageLevel()} ${consoleMessage.message()} " +
                            "(${consoleMessage.sourceId()}:${consoleMessage.lineNumber()})"
                    )
                }
                return true
            }
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_PERMS) {
            val req = pendingPermission
            pendingPermission = null
            if (req != null && grantResults.isNotEmpty() &&
                grantResults.all { it == PackageManager.PERMISSION_GRANTED }
            ) {
                req.grant(req.resources)
            } else {
                req?.deny()
            }
        }
    }

    @Suppress("DEPRECATION")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQ_FILES) {
            val cb = fileCallback ?: return
            fileCallback = null
            val result: Array<Uri>? =
                if (resultCode == RESULT_OK) {
                    WebChromeClient.FileChooserParams.parseResult(resultCode, data)
                } else {
                    null
                }
            cb.onReceiveValue(result)
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && web.canGoBack()) {
            web.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onCreateOptionsMenu(menu: Menu?): Boolean {
        menu?.add(0, 1, 0, "Setelan koneksi")
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == 1) {
            showSettingsDialog()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    /** Panel setelan: edit alamat/IP gateway + kode pairing ulang (repair).
     *  Bisa dibuka kapan saja lewat tombol ⚙️ melayang — termasuk saat halaman
     *  gagal dimuat atau Neira PC baru dinyalakan lagi dan minta kode baru. */
    private fun showSettingsDialog() {
        val form = LinearLayout(this)
        form.orientation = LinearLayout.VERTICAL
        form.setPadding(48, 16, 48, 0)

        fun label(txt: String): TextView {
            val t = TextView(this)
            t.text = txt
            t.setPadding(4, 20, 4, 4)
            return t
        }

        form.addView(label("Alamat gateway (IP PC / domain VPS)"))
        val urlInput = EditText(this)
        urlInput.inputType =
            InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        urlInput.hint = "https://IP-PC:8000"
        urlInput.setText(prefs.getString(KEY_URL, "") ?: "")
        form.addView(urlInput)

        form.addView(label("Kode pairing 6 digit (dari PC) — kosongkan bila tidak pair ulang"))
        val codeInput = EditText(this)
        codeInput.inputType = InputType.TYPE_CLASS_NUMBER
        codeInput.hint = "000000"
        codeInput.filters = arrayOf(android.text.InputFilter.LengthFilter(6))
        form.addView(codeInput)

        AlertDialog.Builder(this)
            .setTitle("⚙️ Setelan Koneksi")
            .setView(form)
            .setPositiveButton("Sambung") { _, _ ->
                val url = normalize(urlInput.text.toString())
                if (url.isBlank()) {
                    Toast.makeText(this, "Alamat gateway kosong.", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                prefs.edit().putString(KEY_URL, url).apply()
                val code = codeInput.text.toString().trim()
                // Isi kode → muat ulang dengan ?code=XXXXXX → halaman web langsung
                // pair_request (repair) tanpa perlu scan QR lagi.
                web.loadUrl(if (code.length == 6) "$url/?code=$code" else url)
            }
            .setNeutralButton("Hapus Data Pair") { _, _ ->
                // Hapus kredensial di native vault + localStorage halaman web.
                prefs.edit().remove(KEY_DEVICE_ID).remove(KEY_DEVICE_KEY).apply()
                web.evaluateJavascript(
                    "try{NeiraNative.clearDevice&&NeiraNative.clearDevice();}catch(e){}" +
                        "localStorage.removeItem('neira_device_id');" +
                        "localStorage.removeItem('neira_device_key');",
                    null
                )
                Toast.makeText(
                    this,
                    "Data pairing dihapus — buka Setelan lagi lalu masukkan kode baru.",
                    Toast.LENGTH_LONG
                ).show()
            }
            .setNegativeButton("Batal", null)
            .show()
    }

    private fun askGatewayUrl(firstRun: Boolean) {
        val input = EditText(this)
        input.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        // Mic (getUserMedia) hanya di secure origin: https:// atau http://localhost —
        // http://IP lokal diblokir WebView (navigator.mediaDevices undefined).
        input.hint = "https://IP-PC:8000"
        input.setText(prefs.getString(KEY_URL, "") ?: "")
        input.setPadding(48, 24, 48, 8)

        val dialog = AlertDialog.Builder(this)
            .setTitle("Alamat Neira Gateway")
            .setMessage(
                "Isi alamat gateway.\n" +
                    "• Mic HP butuh secure origin — pakai https://IP-PC:8000 " +
                    "(gateway lokal jalan dengan sertifikat self-signed).\n" +
                    "• Atau https://domain untuk pemakaian via VPS."
            )
            .setView(input)
            .setCancelable(!firstRun)
            .setPositiveButton("Sambung") { _, _ ->
                val url = normalize(input.text.toString())
                if (url.isBlank()) {
                    if (firstRun) askGatewayUrl(true)
                    return@setPositiveButton
                }
                prefs.edit().putString(KEY_URL, url).apply()
                web.loadUrl(url)
            }
            .create()

        if (firstRun) {
            // Awal wajib isi alamat — tombol kembali tidak menutup aplikasi diam-diam.
            dialog.setOnKeyListener { _, keyCode, _ ->
                keyCode == KeyEvent.KEYCODE_BACK
            }
        }
        dialog.show()
    }

    /** Host privat/localhost — aman dimigrasi otomatis (mis. port lama 8765 → 8000). */
    private fun isPrivateHost(url: String): Boolean {
        val host = android.net.Uri.parse(url).host ?: return false
        return host == "localhost" || host == "127.0.0.1" ||
            host.startsWith("192.168.") || host.startsWith("10.") ||
            Regex("^172\\.(1[6-9]|2\\d|3[01])\\.").containsMatchIn(host)
    }

    private fun normalize(raw: String): String {
        var u = raw.trim().trimEnd('/')
        if (u.isEmpty()) return ""
        // Gateway lokal SELALU TLS (lihat neira-gateway/run_local.bat). Uvicorn di
        // :8000 menolak http polos → "halaman tidak tersedia" di WebView APK,
        // padahal browser PC tetap bisa. Jadi http:// DIPAKSA https:// untuk
        // port 8000/8765 atau host privat/localhost.
        if (u.startsWith("http://") &&
            (u.contains(":8000") || u.contains(":8765") || isPrivateHost(u))
        ) {
            u = "https://" + u.removePrefix("http://")
        } else if (!u.startsWith("http://") && !u.startsWith("https://")) {
            // Default https:// bila pengguna hanya mengetik IP:port atau domain.
            u = "https://$u"
        }
        return u
    }
}
