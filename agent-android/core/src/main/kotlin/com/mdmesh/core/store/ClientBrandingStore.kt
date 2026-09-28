package com.mdmesh.core.store

import android.content.Context
import android.content.SharedPreferences
import android.graphics.BitmapFactory
import com.mdmesh.core.di.RawHttpClient
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The client's own brand (AMBIC DIGITAL owns the MDM; e.g. Aradhana Jewellers is the client),
 * set once in the console and delivered on every check-in. Logos are downloaded only when their
 * URL changes and cached in app storage, so the kiosk shows them offline and at boot.
 *
 * UI reads it synchronously with [read] and re-renders on [PREFS] changes (the `version` key is
 * bumped whenever anything visible changed).
 */
@Singleton
class ClientBrandingStore @Inject constructor(
    @ApplicationContext private val context: Context,
    @RawHttpClient private val http: OkHttpClient,
) {
    data class Branding(val name: String?, val logo: File?, val mark: File?) {
        val isEmpty: Boolean get() = name == null && logo == null && mark == null
    }

    /** Applies the server's branding; a failed download keeps the previous image and is retried
     *  on the next check-in (the URL is only recorded once its image is safely on disk). */
    suspend fun apply(name: String?, logoUrl: String?, markUrl: String?) = withContext(Dispatchers.IO) {
        val p = prefs(context)
        val e = p.edit()
        var changed = false
        val cleanName = name?.trim()?.takeIf { it.isNotEmpty() }
        if (cleanName != p.getString(KEY_NAME, null)) {
            e.putString(KEY_NAME, cleanName)
            changed = true
        }
        if (sync(p, e, "logo", logoUrl)) changed = true
        if (sync(p, e, "mark", markUrl)) changed = true
        if (changed) e.putLong(KEY_VERSION, System.currentTimeMillis())
        e.apply()
    }

    private fun sync(p: SharedPreferences, e: SharedPreferences.Editor, key: String, url: String?): Boolean {
        val file = file(context, key)
        val savedUrl = p.getString("${key}Url", null)
        val wanted = url?.trim()?.takeIf { it.startsWith("https://") || it.startsWith("http://") }
        if (wanted == null) {
            if (savedUrl == null && !file.exists()) return false
            file.delete()
            e.remove("${key}Url")
            return true
        }
        if (wanted == savedUrl && file.exists()) return false
        return runCatching {
            val bytes = http.newCall(Request.Builder().url(wanted).build()).execute().use { r ->
                if (!r.isSuccessful) error("HTTP ${r.code}")
                val body = r.body ?: error("empty body")
                if (body.contentLength() > MAX_BYTES) error("image too large")
                body.bytes().also { if (it.size > MAX_BYTES) error("image too large") }
            }
            // Only accept something Android can actually decode as an image.
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) error("not an image")
            val tmp = File(file.parentFile, "$key.tmp")
            tmp.writeBytes(bytes)
            if (!tmp.renameTo(file)) { file.delete(); tmp.renameTo(file) }
            e.putString("${key}Url", wanted)
            true
        }.getOrDefault(false)
    }

    companion object {
        const val PREFS = "client_branding"
        const val KEY_VERSION = "version"
        private const val KEY_NAME = "name"
        private const val MAX_BYTES = 4L * 1024 * 1024

        fun prefs(context: Context): SharedPreferences =
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        private fun file(context: Context, key: String): File =
            File(context.filesDir, "client_branding").apply { mkdirs() }.let { File(it, "$key.png") }

        /** Current branding for rendering (files only when actually present). */
        fun read(context: Context): Branding {
            val name = prefs(context).getString(KEY_NAME, null)
            val logo = file(context, "logo").takeIf { it.exists() && it.length() > 0 }
            val mark = file(context, "mark").takeIf { it.exists() && it.length() > 0 }
            return Branding(name, logo, mark)
        }
    }
}
