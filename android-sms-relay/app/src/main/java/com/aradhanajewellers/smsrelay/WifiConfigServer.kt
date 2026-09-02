package com.aradhanajewellers.smsrelay

import android.content.Context
import java.io.BufferedInputStream
import java.net.Inet4Address
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Minimal local-only settings server. It intentionally has no endpoint that
 * returns SMS data, relay history, or the stored SMTP password.
 */
class WifiConfigServer(private val context: Context) {
    private val store = RelayConfigStore(context)
    private val workers: ExecutorService = Executors.newCachedThreadPool()
    @Volatile private var socket: ServerSocket? = null

    fun start() {
        if (socket != null) return
        socket = ServerSocket(PORT)
        workers.execute {
            while (!Thread.currentThread().isInterrupted) {
                try {
                    val client = socket?.accept() ?: break
                    workers.execute { handle(client) }
                } catch (_: Exception) {
                    break
                }
            }
        }
    }

    fun stop() {
        socket?.close()
        socket = null
        workers.shutdownNow()
    }

    private fun handle(client: Socket) {
        client.use {
            if (!isPrivateLan(client.inetAddress)) {
                write(client, 403, "Local network only", "Access is limited to the phone's private Wi-Fi/LAN.")
                return
            }
            val input = BufferedInputStream(client.getInputStream())
            val headerText = readHeaders(input) ?: return
            val lines = headerText.split("\r\n")
            val request = lines.firstOrNull()?.split(" ") ?: return
            if (request.size < 2) return
            val method = request[0]
            val target = request[1]
            val contentLength = lines.firstOrNull { it.startsWith("Content-Length:", true) }
                ?.substringAfter(":")?.trim()?.toIntOrNull()?.coerceIn(0, 16_384) ?: 0
            val body = if (contentLength > 0) input.readNBytes(contentLength).toString(StandardCharsets.UTF_8) else ""
            val (path, query) = splitTarget(target)
            val code = query["code"] ?: ""
            if (code != store.pairingCode()) {
                write(client, 401, "Pairing required", pairingPage())
                return
            }
            if (method == "POST" && path == "/save") {
                val fields = parseForm(body)
                val old = store.load()
                val next = RelayConfig(
                    enabled = fields["enabled"] == "on",
                    forwardAllMessages = false,
                    smtpHost = fields["smtpHost"]?.trim().orEmpty(),
                    smtpPort = fields["smtpPort"]?.toIntOrNull() ?: 0,
                    smtpUsername = fields["smtpUsername"]?.trim().orEmpty(),
                    smtpPassword = fields["smtpPassword"].orEmpty().ifBlank { old.smtpPassword },
                    recipient = fields["recipient"]?.trim().orEmpty(),
                    senderWhitelist = fields["senderWhitelist"].orEmpty().lines().map { it.trim() }.filter { it.isNotEmpty() },
                )
                if (!store.isValid(next)) {
                    write(client, 400, "Invalid settings", settingsPage("Complete all SMTP fields. Password may be left blank only after it was saved once."))
                    return
                }
                store.save(next)
                write(client, 200, "Saved", settingsPage("Settings saved on the relay phone."))
                return
            }
            write(client, 200, "Relay Wi-Fi Settings", settingsPage())
        }
    }

    private fun pairingPage() = """<h1>Aradhana SMS Relay</h1><p>Enter the 8-character pairing code shown on the relay phone.</p><form><input name="code" autocomplete="off" autofocus><button>Connect</button></form>"""

    private fun settingsPage(message: String = ""): String {
        val c = store.load()
        fun checked(value: Boolean) = if (value) "checked" else ""
        fun esc(value: String) = value.replace("&", "&amp;").replace("\"", "&quot;").replace("<", "&lt;")
        val code = store.pairingCode()
        return """
            <h1>Aradhana SMS Relay</h1><p>${esc(message)}</p>
            <p>This page changes relay settings only. It never displays SMS messages, email contents, or saved passwords.</p>
            <form method="post" action="/save?code=$code">
            <label><input type="checkbox" name="enabled" ${checked(c.enabled)}> Enable forwarding</label><br>
            <p>Only bank credit/debit transaction messages are forwarded. OTPs and personal messages are excluded.</p>
            <label>SMTP host <input name="smtpHost" value="${esc(c.smtpHost)}"></label><br>
            <label>SMTP port <input name="smtpPort" inputmode="numeric" value="${c.smtpPort}"></label><br>
            <label>SMTP username <input name="smtpUsername" value="${esc(c.smtpUsername)}"></label><br>
            <label>New SMTP app password <input name="smtpPassword" type="password" placeholder="Leave blank to keep saved password"></label><br>
            <label>Recipient <input name="recipient" value="${esc(c.recipient)}"></label><br>
            <label>Approved sender IDs<br><textarea name="senderWhitelist" rows="6">${esc(c.senderWhitelist.joinToString("\n"))}</textarea></label><br>
            <button type="submit">Save relay settings</button></form>
        """.trimIndent()
    }

    private fun readHeaders(input: BufferedInputStream): String? {
        val bytes = ArrayList<Byte>()
        while (bytes.size < 16_384) {
            val value = input.read()
            if (value == -1) return null
            bytes.add(value.toByte())
            if (bytes.size >= 4 && bytes.takeLast(4).map { it.toInt() and 0xff } == listOf(13, 10, 13, 10)) break
        }
        return bytes.toByteArray().toString(StandardCharsets.UTF_8)
    }

    private fun splitTarget(target: String): Pair<String, Map<String, String>> {
        val path = target.substringBefore('?')
        val query = target.substringAfter('?', "").split('&').filter { it.isNotBlank() }.associate {
            val key = URLDecoder.decode(it.substringBefore('='), "UTF-8")
            key to URLDecoder.decode(it.substringAfter('=', ""), "UTF-8")
        }
        return path to query
    }

    private fun parseForm(value: String): Map<String, String> = value.split('&').filter { it.isNotBlank() }.associate {
        URLDecoder.decode(it.substringBefore('='), "UTF-8") to URLDecoder.decode(it.substringAfter('=', ""), "UTF-8")
    }

    private fun write(client: Socket, status: Int, title: String, body: String) {
        val html = "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>$title</title><style>body{font:16px sans-serif;max-width:640px;margin:32px auto;padding:0 16px}label{display:block;margin:12px 0}input,textarea{width:100%;box-sizing:border-box;padding:9px;margin-top:4px}button{padding:10px 16px}</style>$body"
        val payload = html.toByteArray(StandardCharsets.UTF_8)
        client.getOutputStream().use { out ->
            out.write("HTTP/1.1 $status $title\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ${payload.size}\r\nConnection: close\r\n\r\n".toByteArray())
            out.write(payload)
        }
    }

    private fun isPrivateLan(address: InetAddress): Boolean = address.isLoopbackAddress || address.isSiteLocalAddress

    companion object {
        const val PORT = 8765
        fun localUrl(): String? {
            val address = NetworkInterface.getNetworkInterfaces().toList().flatMap { it.inetAddresses.toList() }
                .firstOrNull { it is Inet4Address && !it.isLoopbackAddress && it.isSiteLocalAddress }
            return address?.hostAddress?.let { "http://$it:$PORT" }
        }
    }
}
