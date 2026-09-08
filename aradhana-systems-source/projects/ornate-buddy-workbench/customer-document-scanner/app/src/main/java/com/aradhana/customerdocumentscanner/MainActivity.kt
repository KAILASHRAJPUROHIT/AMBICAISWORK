package com.aradhana.customerdocumentscanner

import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.view.View
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.aradhana.customerdocumentscanner.databinding.ActivityMainBinding
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.devanagari.DevanagariTextRecognizerOptions
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    private val scannerLauncher = registerForActivityResult(
        ActivityResultContracts.StartIntentSenderForResult()
    ) { result ->
        if (result.resultCode != RESULT_OK) return@registerForActivityResult
        val scan = GmsDocumentScanningResult.fromActivityResultIntent(result.data) ?: return@registerForActivityResult
        scan.pages?.firstOrNull()?.imageUri?.let(::recognizeDocument)
            ?: showStatus("No usable page returned. Please scan again.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.scanButton.setOnClickListener { startScan() }
    }

    private fun startScan() {
        val options = GmsDocumentScannerOptions.Builder()
            .setGalleryImportAllowed(true)
            .setPageLimit(1)
            .setResultFormats(GmsDocumentScannerOptions.RESULT_FORMAT_JPEG)
            .setScannerMode(GmsDocumentScannerOptions.SCANNER_MODE_FULL)
            .build()
        GmsDocumentScanning.getClient(options).getStartScanIntent(this)
            .addOnSuccessListener { scannerLauncher.launch(IntentSenderRequest.Builder(it).build()) }
            .addOnFailureListener { showStatus("Scanner unavailable: ${it.message ?: "unknown error"}") }
    }

    private fun recognizeDocument(uri: Uri) {
        setLoading(true)
        val bitmap = if (android.os.Build.VERSION.SDK_INT >= 28) {
            ImageDecoder.decodeBitmap(ImageDecoder.createSource(contentResolver, uri))
        } else {
            @Suppress("DEPRECATION") MediaStore.Images.Media.getBitmap(contentResolver, uri)
        }
        val image = InputImage.fromBitmap(bitmap, 0)
        val latin = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val devanagari = TextRecognition.getClient(DevanagariTextRecognizerOptions.Builder().build())
        Tasks.whenAllSuccess<com.google.mlkit.vision.text.Text>(
            listOf(latin.process(image), devanagari.process(image))
        ).addOnSuccessListener { results ->
            val parsed = CustomerDocumentParser.parse(results.joinToString("\n") { it.text })
            binding.nameField.setText(parsed.name)
            binding.dobField.setText(parsed.dob)
            binding.genderField.setText(parsed.gender)
            binding.addressField.setText(parsed.address)
            binding.pincodeField.setText(parsed.pincode)
            binding.aadhaarLast4Field.setText(parsed.aadhaarLast4)
            showStatus("OCR completed locally. Review and correct fields before challan use.")
        }.addOnFailureListener {
            showStatus("OCR could not read this image. Use a clearer capture.")
        }.addOnCompleteListener {
            latin.close()
            devanagari.close()
            bitmap.recycle()
            setLoading(false)
        }
    }

    private fun setLoading(loading: Boolean) {
        binding.progress.visibility = if (loading) View.VISIBLE else View.GONE
        binding.scanButton.isEnabled = !loading
        if (loading) binding.statusText.text = "Reading document on this device…"
    }

    private fun showStatus(message: String) { binding.statusText.text = message }
}

private data class CustomerDocument(
    val name: String = "",
    val dob: String = "",
    val gender: String = "",
    val address: String = "",
    val pincode: String = "",
    val aadhaarLast4: String = ""
)

/** Heuristic only. It deliberately never returns or persists a full Aadhaar number. */
private object CustomerDocumentParser {
    private val dobRegex = Regex("\\b(?:DOB|D\\.O\\.B\\.?|Date of Birth)\\s*[:.-]?\\s*(\\d{2}[/-]\\d{2}[/-]\\d{4})", RegexOption.IGNORE_CASE)
    private val looseDobRegex = Regex("\\b(\\d{2}[/-]\\d{2}[/-]\\d{4})\\b")
    private val pinRegex = Regex("\\b([1-9]\\d{5})\\b")
    private val aadhaarRegex = Regex("\\b([2-9]\\d{3}[ -]?\\d{4}[ -]?\\d{4})\\b")

    fun parse(ocr: String): CustomerDocument {
        val lines = ocr.lines().map { it.trim().replace(Regex("\\s+"), " ") }.filter { it.isNotBlank() }
        val normal = lines.joinToString("\n")
        val name = labeledValue(lines, listOf("name", "नाम"))
            ?: lines.firstOrNull { it.matches(Regex("[A-Za-z .]{3,}")) && !it.contains(Regex("government|india|aadhaar|address", RegexOption.IGNORE_CASE)) }
            ?: ""
        val gender = when {
            normal.contains(Regex("\\bfemale\\b|महिला", RegexOption.IGNORE_CASE)) -> "Female"
            normal.contains(Regex("\\bmale\\b|पुरुष", RegexOption.IGNORE_CASE)) -> "Male"
            normal.contains(Regex("\\btransgender\\b", RegexOption.IGNORE_CASE)) -> "Transgender"
            else -> ""
        }
        val dob = dobRegex.find(normal)?.groupValues?.get(1) ?: looseDobRegex.find(normal)?.groupValues?.get(1).orEmpty()
        val pincode = pinRegex.find(normal)?.groupValues?.get(1).orEmpty()
        val aadhaarLast4 = aadhaarRegex.findAll(normal).lastOrNull()?.groupValues?.get(1)
            ?.filter(Char::isDigit)?.takeLast(4).orEmpty()
        val address = address(lines, pincode)
        return CustomerDocument(name, dob, gender, address, pincode, aadhaarLast4)
    }

    private fun labeledValue(lines: List<String>, labels: List<String>): String? = lines.firstNotNullOfOrNull { line ->
        labels.firstOrNull { label -> line.lowercase(Locale.ROOT).startsWith(label.lowercase(Locale.ROOT)) }
            ?.let { line.substringAfter(":", "").trim().takeIf { it.length >= 2 } }
    }

    private fun address(lines: List<String>, pincode: String): String {
        val index = lines.indexOfFirst { it.contains(Regex("address|पता", RegexOption.IGNORE_CASE)) }
        if (index < 0) return ""
        return lines.drop(index).take(5)
            .joinToString(", ") { it.replace(Regex("(?i)address|पता\\s*:?"), "").trim() }
            .substringBefore(pincode).trim(' ', ',', ':')
    }
}
