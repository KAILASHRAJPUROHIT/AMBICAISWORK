package com.mdmesh.core.command.handlers

import android.annotation.SuppressLint
import android.app.WallpaperManager
import android.content.Context
import android.graphics.BitmapFactory
import com.mdmesh.core.command.CommandHandler
import com.mdmesh.core.command.CommandResults
import com.mdmesh.proto.CommandEnvelope
import com.mdmesh.proto.CommandResult
import com.mdmesh.proto.DeviceAction
import com.mdmesh.proto.ProtocolJson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import okhttp3.OkHttpClient
import okhttp3.Request

/**
 * `device.wallpaper` — set the home and/or lock screen wallpaper. Uses [WallpaperManager]
 * directly, not a Device Owner API: setting your own device's wallpaper only needs the normal
 * (install-time, no runtime prompt) `SET_WALLPAPER` permission, so this works on Lite (Device
 * Admin) devices too, not just Device Owner.
 */
class DeviceWallpaperHandler(
    private val context: Context,
    private val httpClient: OkHttpClient,
) : CommandHandler {

    override val type: String = DeviceAction.WALLPAPER

    @Serializable
    private data class Payload(val url: String, val target: String = "both")

    override suspend fun handle(command: CommandEnvelope): CommandResult {
        val payload = command.payload
            ?: return CommandResults.failed(command, "device.wallpaper requires a payload")
        val parsed = runCatching {
            ProtocolJson.json.decodeFromJsonElement(Payload.serializer(), payload)
        }.getOrElse { return CommandResults.failed(command, "bad payload: ${it.message}") }

        return withContext(Dispatchers.IO) {
            runCatching {
                val bitmap = httpClient.newCall(Request.Builder().url(parsed.url).build()).execute().use { response ->
                    if (!response.isSuccessful) error("HTTP ${response.code} for ${parsed.url}")
                    val body = response.body ?: error("empty response body for ${parsed.url}")
                    body.byteStream().use { BitmapFactory.decodeStream(it) }
                        ?: error("not a decodable image")
                }
                val wm = WallpaperManager.getInstance(context)
                val which = when (parsed.target.lowercase()) {
                    "home" -> WallpaperManager.FLAG_SYSTEM
                    "lock" -> WallpaperManager.FLAG_LOCK
                    else -> WallpaperManager.FLAG_SYSTEM or WallpaperManager.FLAG_LOCK
                }
                @SuppressLint("MissingPermission")
                wm.setBitmap(bitmap, null, true, which)
                CommandResults.done(command)
            }.getOrElse { CommandResults.failed(command, it.message ?: "wallpaper failed") }
        }
    }
}
