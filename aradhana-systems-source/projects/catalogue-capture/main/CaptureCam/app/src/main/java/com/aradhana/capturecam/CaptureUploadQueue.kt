package com.aradhana.capturecam

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.widget.Toast
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.locks.ReentrantLock
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlin.concurrent.withLock

/**
 * Disk-backed hand-off between capture and upload.
 *
 * The camera workflow blocks only until originals are fsynced into one
 * app-private job directory. WorkManager then uploads jobs independently of
 * MainActivity, survives process/network restarts, and retries transport
 * failures. Server-side validation failures keep their originals in
 * `pending_capture_uploads` with state=needs_review; nothing is discarded.
 */
object CaptureUploadQueue {
    private const val ROOT = "pending_capture_uploads"
    internal const val MANIFEST = "manifest.json"
    internal const val TYPE_MULTI = "multi"
    internal const val TYPE_PAIR = "pair"
    private const val WORK_PREFIX = "capture-upload-"
    private const val WORK_TAG = "capture-upload"
    private const val HISTORY_FILE = "capture_pipeline_history.json"
    private const val HISTORY_LIMIT = 10
    private val historyLock = ReentrantLock()

    data class Staged(val id: String, val tagCode: String)

    /** Operator-visible, durable summary of the most recent captures.
     * `savedOnLaptop` changes only after the catalogue server accepts the
     * originals. This deliberately does not infer a save from local staging. */
    data class PipelineRecord(
        val id: String,
        val capturedAt: Long,
        val tagCode: String,
        val stitched: Boolean,
        val savedOnLaptop: Boolean,
        val state: String
    )

    suspend fun stageMulti(
        context: Context,
        serverUrl: String,
        tagCode: String,
        staffName: String,
        main: ByteArray,
        angle1: ByteArray,
        angle2: ByteArray
    ): Staged = stage(
        context, TYPE_MULTI, serverUrl, tagCode, staffName,
        mapOf("main.jpg" to main, "angle1.jpg" to angle1, "angle2.jpg" to angle2)
    )

    suspend fun stagePair(
        context: Context,
        serverUrl: String,
        tagCode: String,
        staffName: String,
        jewel: ByteArray,
        tag: ByteArray
    ): Staged = stage(
        context, TYPE_PAIR, serverUrl, tagCode, staffName,
        mapOf("jewel.jpg" to jewel, "tag.jpg" to tag)
    )

    private suspend fun stage(
        context: Context,
        type: String,
        serverUrl: String,
        tagCode: String,
        staffName: String,
        files: Map<String, ByteArray>
    ): Staged = withContext(Dispatchers.IO) {
        val root = File(context.filesDir, ROOT).apply { mkdirs() }
        val id = "${System.currentTimeMillis()}-${UUID.randomUUID()}"
        val temp = File(root, ".$id.tmp")
        val target = File(root, id)
        check(temp.mkdir()) { "Cannot create upload staging directory" }
        try {
            files.forEach { (name, bytes) -> durableWrite(File(temp, name), bytes) }
            writeManifest(
                temp,
                JSONObject().apply {
                    put("schema", 1)
                    put("id", id)
                    put("type", type)
                    put("server_url", serverUrl)
                    put("tag_code", tagCode)
                    put("staff_name", staffName)
                    put("created_at", System.currentTimeMillis())
                    put("state", "queued")
                    put("attempts", 0)
                }
            )
            check(temp.renameTo(target)) { "Cannot publish upload staging directory" }
        } catch (e: Exception) {
            temp.deleteRecursively()
            throw e
        }
        // The capture job is already durable. A diagnostics-card write must
        // never turn a valid capture into a failed one.
        runCatching { addPipelineRecord(context.applicationContext, id, tagCode, type) }
            .onFailure { Log.w(TAG, "Could not record capture pipeline card id=$id", it) }
        enqueue(context.applicationContext, target)
        Log.i(TAG, "Staged background upload id=$id tag=$tagCode type=$type bytes=${files.values.sumOf { it.size.toLong() }}")
        Staged(id, tagCode)
    }

    fun listPipelineHistory(context: Context): List<PipelineRecord> = historyLock.withLock {
        readHistory(context).sortedByDescending { it.capturedAt }
    }

    internal fun updatePipelineRecord(
        context: Context,
        id: String,
        stitched: Boolean? = null,
        savedOnLaptop: Boolean? = null,
        state: String? = null
    ) = historyLock.withLock {
        val records = readHistory(context).toMutableList()
        val index = records.indexOfFirst { it.id == id }
        if (index < 0) return@withLock
        val old = records[index]
        records[index] = old.copy(
            stitched = stitched ?: old.stitched,
            savedOnLaptop = savedOnLaptop ?: old.savedOnLaptop,
            state = state ?: old.state
        )
        writeHistory(context, records)
    }

    private fun addPipelineRecord(context: Context, id: String, tagCode: String, type: String) = historyLock.withLock {
        val records = readHistory(context).toMutableList()
        records.removeAll { it.id == id }
        records += PipelineRecord(
            id = id,
            capturedAt = System.currentTimeMillis(),
            tagCode = tagCode,
            stitched = false,
            savedOnLaptop = false,
            state = if (type == TYPE_MULTI) "queued for stitch" else "queued"
        )
        writeHistory(context, records.sortedByDescending { it.capturedAt }.take(HISTORY_LIMIT))
    }

    private fun readHistory(context: Context): List<PipelineRecord> {
        return try {
            val file = File(context.filesDir, HISTORY_FILE)
            if (!file.isFile) emptyList() else {
                val rows = JSONObject(file.readText()).optJSONArray("records")
                if (rows == null) emptyList() else buildList {
                    for (index in 0 until rows.length()) {
                        val row = rows.optJSONObject(index) ?: continue
                        add(PipelineRecord(
                            id = row.optString("id"),
                            capturedAt = row.optLong("captured_at"),
                            tagCode = row.optString("tag_code"),
                            stitched = row.optBoolean("stitched", false),
                            savedOnLaptop = row.optBoolean("saved_on_laptop", false),
                            state = row.optString("state", "queued")
                        ))
                    }
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Ignoring unreadable capture pipeline history", e)
            emptyList()
        }
    }

    private fun writeHistory(context: Context, records: List<PipelineRecord>) {
        val data = JSONObject().put("records", org.json.JSONArray().apply {
            records.forEach { row -> put(JSONObject().apply {
                put("id", row.id)
                put("captured_at", row.capturedAt)
                put("tag_code", row.tagCode)
                put("stitched", row.stitched)
                put("saved_on_laptop", row.savedOnLaptop)
                put("state", row.state)
            }) }
        })
        val file = File(context.filesDir, HISTORY_FILE)
        val temp = File(context.filesDir, "$HISTORY_FILE.tmp")
        durableWrite(temp, data.toString().toByteArray(Charsets.UTF_8))
        if (file.exists() && !file.delete()) error("Cannot replace capture pipeline history")
        check(temp.renameTo(file)) { "Cannot commit capture pipeline history" }
    }

    /** Re-enqueue durable jobs after an app/process restart. WorkManager KEEP
     * makes this idempotent if the original request still exists. */
    fun resumePending(context: Context) {
        val root = File(context.filesDir, ROOT)
        root.listFiles()?.filter { it.isDirectory && !it.name.startsWith(".") }?.forEach { dir ->
            val state = readManifest(dir)?.optString("state")
            if (state != "needs_review") enqueue(context.applicationContext, dir)
        }
    }

    /** One entry a staff member can act on from the review screen. */
    data class ReviewItem(
        val dir: File,
        val tagCode: String,
        val error: String?,
        /** Server names the exact failed pose for multi-angle validation. */
        val slot: String?,
        val reason: String?,
        val blurScore: Double?,
        val type: String,
        val updatedAt: Long
    )

    /** Everything currently parked in needs_review -- nothing here was
     * discarded, it's just waiting for a human decision (2026-08-26 fix:
     * previously this state was only ever surfaced as a transient Toast,
     * with no way for staff to actually go act on it). */
    fun listNeedsReview(context: Context): List<ReviewItem> {
        val root = File(context.filesDir, ROOT)
        return root.listFiles()
            ?.filter { it.isDirectory && !it.name.startsWith(".") }
            ?.mapNotNull { dir ->
                val json = readManifest(dir) ?: return@mapNotNull null
                if (json.optString("state") != "needs_review") return@mapNotNull null
                ReviewItem(
                    dir = dir,
                    tagCode = json.optString("tag_code"),
                    error = json.optString("last_error").ifBlank { null },
                    slot = json.optString("review_slot").ifBlank { null },
                    reason = json.optString("review_reason").ifBlank { null },
                    blurScore = if (json.has("review_blur_score")) {
                        json.optDouble("review_blur_score")
                    } else null,
                    type = json.optString("type"),
                    updatedAt = json.optLong("updated_at", json.optLong("created_at"))
                )
            }
            ?.sortedBy { it.updatedAt }
            ?: emptyList()
    }

    /** Re-queues a needs_review job, optionally forcing past the specific
     * server-side rejection that parked it there. Staff make this call
     * explicitly per item -- it is never automatic. */
    fun retryWithOverride(
        context: Context,
        dir: File,
        overrideDuplicate: Boolean = false,
        overrideBlur: Boolean = false,
        overrideVisibility: Boolean = false
    ) {
        val json = readManifest(dir) ?: return
        json.put("state", "queued")
        json.put("updated_at", System.currentTimeMillis())
        json.remove("last_error")
        json.remove("review_slot")
        json.remove("review_reason")
        json.remove("review_blur_score")
        if (overrideDuplicate) json.put("override_duplicate", true)
        if (overrideBlur) json.put("override_blur", true)
        if (overrideVisibility) json.put("override_visibility", true)
        writeManifest(dir, json)
        updatePipelineRecord(context.applicationContext, json.optString("id"), state = "queued")
        enqueue(context.applicationContext, dir)
    }

    /** Permanently discards a needs_review item -- e.g. a genuine duplicate
     * staff confirm should not be saved. Deletes the staged originals. */
    fun discard(context: Context, dir: File) {
        readManifest(dir)?.optString("id")?.takeIf { it.isNotBlank() }?.let { id ->
            updatePipelineRecord(context.applicationContext, id, state = "recapture")
            Log.i(TAG, "Discarded staged job id=$id")
        }
        dir.deleteRecursively()
    }

    internal fun readManifest(dir: File): JSONObject? = try {
        JSONObject(File(dir, MANIFEST).readText())
    } catch (e: Exception) {
        Log.e(TAG, "Unreadable upload manifest: ${dir.absolutePath}", e)
        null
    }

    internal fun updateState(
        dir: File,
        state: String,
        error: String? = null,
        attempts: Int? = null,
        review: JSONObject? = null
    ) {
        val json = readManifest(dir) ?: return
        json.put("state", state)
        json.put("updated_at", System.currentTimeMillis())
        if (error == null) json.remove("last_error") else json.put("last_error", error)
        if (review == null) {
            json.remove("review_slot")
            json.remove("review_reason")
            json.remove("review_blur_score")
        } else {
            review.optString("slot").takeIf { it.isNotBlank() }?.let { json.put("review_slot", it) }
            review.optString("reason").takeIf { it.isNotBlank() }?.let { json.put("review_reason", it) }
            if (review.has("blur_score")) json.put("review_blur_score", review.optDouble("blur_score"))
        }
        if (attempts != null) json.put("attempts", attempts)
        writeManifest(dir, json)
    }

    private fun enqueue(context: Context, dir: File) {
        val request = OneTimeWorkRequestBuilder<CaptureUploadWorker>()
            .setInputData(workDataOf("job_dir" to dir.absolutePath))
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setBackoffCriteria(androidx.work.BackoffPolicy.EXPONENTIAL, 10, TimeUnit.SECONDS)
            .addTag(WORK_TAG)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            WORK_PREFIX + dir.name,
            ExistingWorkPolicy.KEEP,
            request
        )
    }

    private fun durableWrite(file: File, bytes: ByteArray) {
        FileOutputStream(file).use { output ->
            output.write(bytes)
            output.flush()
            output.fd.sync()
        }
    }

    private fun writeManifest(dir: File, json: JSONObject) {
        val temp = File(dir, "$MANIFEST.tmp")
        durableWrite(temp, json.toString().toByteArray(Charsets.UTF_8))
        val target = File(dir, MANIFEST)
        if (target.exists() && !target.delete()) error("Cannot replace upload manifest")
        check(temp.renameTo(target)) { "Cannot commit upload manifest" }
    }

    internal fun toast(context: Context, text: String, long: Boolean = false) {
        Handler(Looper.getMainLooper()).post {
            Toast.makeText(context.applicationContext, text, if (long) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()
        }
    }

    private const val TAG = "CaptureUpload"
}

class CaptureUploadWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {

    override suspend fun doWork(): Result = uploadMutex.withLock {
        UploadClient.refreshLanRoute(applicationContext)
        val path = inputData.getString("job_dir") ?: return@withLock Result.failure()
        val dir = File(path)
        if (!dir.isDirectory) return@withLock Result.success()
        val manifest = CaptureUploadQueue.readManifest(dir) ?: return@withLock Result.failure()
        val tag = manifest.optString("tag_code")
        val jobId = manifest.optString("id")
        val jobType = manifest.optString("type")
        val attempts = runAttemptCount + 1
        val overrideDuplicate = manifest.optBoolean("override_duplicate", false)
        val overrideBlur = manifest.optBoolean("override_blur", false)
        val overrideVisibility = manifest.optBoolean("override_visibility", false)
        val deliveryUrl = UploadClient.resolveDeliveryBaseUrl(
            applicationContext, manifest.getString("server_url")
        )
        CaptureUploadQueue.updateState(dir, "uploading", attempts = attempts)
        CaptureUploadQueue.updatePipelineRecord(applicationContext, jobId, state = "uploading")
        try {
            val result = when (jobType) {
                CaptureUploadQueue.TYPE_MULTI -> UploadClient.saveMultiFiles(
                    deliveryUrl, tag, manifest.optString("staff_name"),
                    File(dir, "main.jpg"), File(dir, "angle1.jpg"), File(dir, "angle2.jpg"),
                    overrideDuplicate, overrideBlur, overrideVisibility
                )
                CaptureUploadQueue.TYPE_PAIR -> UploadClient.savePairFiles(
                    deliveryUrl, tag, manifest.optString("staff_name"),
                    File(dir, "jewel.jpg"), File(dir, "tag.jpg"),
                    overrideDuplicate, overrideBlur, overrideVisibility
                )
                else -> {
                    CaptureUploadQueue.updateState(dir, "needs_review", "unknown_job_type", attempts)
                    CaptureUploadQueue.updatePipelineRecord(applicationContext, jobId, state = "needs review")
                    return@withLock Result.success(workDataOf("status" to "needs_review", "tag" to tag))
                }
            }
            if (result.ok) {
                Log.i(TAG, "Background upload saved tag=$tag attempt=$attempts")
                CaptureUploadQueue.updatePipelineRecord(
                    applicationContext,
                    jobId,
                    stitched = jobType == CaptureUploadQueue.TYPE_MULTI,
                    savedOnLaptop = true,
                    state = "saved"
                )
                dir.deleteRecursively()
                CaptureUploadQueue.toast(applicationContext, "Saved in background: $tag")
                Result.success(workDataOf("status" to "saved", "tag" to tag))
            } else if (result.error == null) {
                CaptureUploadQueue.updateState(dir, "queued", "empty_or_invalid_server_response", attempts)
                CaptureUploadQueue.updatePipelineRecord(applicationContext, jobId, state = "queued")
                Result.retry()
            } else {
                // Duplicate/blur/visibility and any catalogue rejection need a
                // human decision. Preserve originals and let later jobs run.
                // Keep the server diagnostics with the durable originals. The
                // review screen must show the failed pose, not a generic item
                // label that leaves staff guessing which photo was rejected.
                CaptureUploadQueue.updateState(
                    dir, "needs_review", result.error, attempts, result.raw
                )
                CaptureUploadQueue.updatePipelineRecord(applicationContext, jobId, state = "needs review")
                Log.e(TAG, "Background upload needs review tag=$tag error=${result.error}")
                CaptureUploadQueue.toast(
                    applicationContext,
                    "Upload needs review: $tag (${result.error}) -- long-press Settings to fix",
                    long = true
                )
                Result.success(workDataOf("status" to "needs_review", "tag" to tag, "error" to result.error))
            }
        } catch (e: CancellationException) {
            CaptureUploadQueue.updateState(dir, "queued", "cancelled", attempts)
            CaptureUploadQueue.updatePipelineRecord(applicationContext, jobId, state = "queued")
            throw e
        } catch (e: Exception) {
            CaptureUploadQueue.updateState(dir, "queued", e.message ?: e.javaClass.simpleName, attempts)
            CaptureUploadQueue.updatePipelineRecord(applicationContext, jobId, state = "retrying")
            Log.w(TAG, "Background upload retry tag=$tag attempt=$attempts: ${e.message}")
            Result.retry()
        }
    }

    companion object {
        private const val TAG = "CaptureUpload"
        private val uploadMutex = Mutex()
    }
}
