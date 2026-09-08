package com.aradhanajewellers.app.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.EventAvailable
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aradhanajewellers.app.AppViewModel
import com.aradhanajewellers.app.Business
import com.aradhanajewellers.app.ui.components.GoldDivider
import com.aradhanajewellers.app.ui.components.ProductImage
import com.aradhanajewellers.app.ui.theme.Gold
import com.aradhanajewellers.app.ui.theme.GoldLight
import kotlinx.coroutines.delay

@Composable
fun ProductDetailScreen(vm: AppViewModel, productId: String) {
    val product = vm.byId(productId) ?: return
    val rates by vm.rates.collectAsStateWithLifecycle()
    val wishlist by vm.wishlist.collectAsStateWithLifecycle()
    val context = LocalContext.current

    val metal = product.netWeight * product.metalRate(rates)
    val making = product.netWeight * product.makingPerGram
    val gst = (metal + making) * rates.gstPercent / 100.0
    val total = metal + making + gst

    var justAdded by remember { mutableStateOf(false) }
    LaunchedEffect(justAdded) {
        if (justAdded) {
            delay(1500)
            justAdded = false
        }
    }
    var showVisitDialog by remember { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(bottom = 24.dp),
    ) {
        Row {
            ProductImage(
                product.image,
                Modifier
                    .weight(1f)
                    .height(340.dp),
                zoom = true,
            )
            IconButton(onClick = { vm.toggleWish(product.id) }) {
                Icon(
                    if (product.id in wishlist) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    contentDescription = "Wishlist",
                    tint = Gold,
                )
            }
        }

        Column(Modifier.padding(horizontal = 16.dp)) {
            Text(product.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(
                "Code: ${product.code} · ${product.purity} · ${product.categoryName}",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                vm.inr(total),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = GoldLight,
            )

            Spacer(Modifier.height(14.dp))
            GoldDivider()

            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 14.dp),
            ) {
                Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    PriceRow("Gold value (${product.netWeight} g × ₹%,.0f".format(product.metalRate(rates)) + ")", vm.inr(metal))
                    PriceRow("Making charges (₹%,.0f/g".format(product.makingPerGram) + ")", vm.inr(making))
                    if (product.stoneInfo.isNotBlank()) PriceRow("Stones", product.stoneInfo)
                    HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.4f))
                    PriceRow("GST (${rates.gstPercent}%)", vm.inr(gst))
                    PriceRow("Total", vm.inr(total), bold = true)
                }
            }

            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    vm.addToCart(product.id)
                    justAdded = true
                },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Gold),
            ) {
                Icon(if (justAdded) Icons.Default.Check else Icons.Default.ShoppingCart, null)
                Text(if (justAdded) "  Added to Cart" else "  Add to Cart")
            }

            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = {
                        val msg = "Hi ${Business.NAME}, I'm interested in ${product.name} (${product.purity}, ${product.netWeight} g). Is it available?"
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/${Business.WHATSAPP}?text=${Uri.encode(msg)}")))
                    },
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                ) {
                    Icon(Icons.Default.Chat, null, tint = GoldLight)
                    Text("  WhatsApp")
                }
                OutlinedButton(
                    onClick = { context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${Business.PHONE}"))) },
                    modifier = Modifier.weight(1f),
                ) {
                    Icon(Icons.Default.Call, null, tint = Gold)
                    Text("  Call")
                }
            }

            Spacer(Modifier.height(10.dp))
            OutlinedButton(
                onClick = { showVisitDialog = true },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Default.EventAvailable, null, tint = Gold)
                Text("  Book a Visit to See This Piece")
            }

            Spacer(Modifier.height(10.dp))
            Text(
                "Prices move with the daily gold rate — confirm availability & final price on WhatsApp.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }

    if (showVisitDialog) {
        VisitDialog(
            productName = product.name,
            onConfirm = { date, time, note ->
                val msg = buildString {
                    append("Hi ${Business.NAME}, I'd like to visit the showroom on $date at $time to see ${product.name} (${product.code}).")
                    if (note.isNotBlank()) append(" Note: $note")
                }
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/${Business.WHATSAPP}?text=${Uri.encode(msg)}")))
                showVisitDialog = false
            },
            onDismiss = { showVisitDialog = false },
        )
    }
}

@Composable
private fun VisitDialog(
    productName: String,
    onConfirm: (date: String, time: String, note: String) -> Unit,
    onDismiss: () -> Unit,
) {
    var date by remember { mutableStateOf("") }
    var time by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    val valid = date.isNotBlank() && time.isNotBlank()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Book a Visit") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    "For: $productName",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedTextField(
                    date, { date = it },
                    label = { Text("Date (e.g. Sat 24 Aug)") },
                    singleLine = true,
                )
                OutlinedTextField(
                    time, { time = it },
                    label = { Text("Time (e.g. 11:30 AM)") },
                    singleLine = true,
                )
                OutlinedTextField(
                    note, { note = it },
                    label = { Text("Anything else? (optional)") },
                    singleLine = true,
                )
                Text(
                    "We'll confirm your slot on WhatsApp. Store hours: ${Business.HOURS.first()}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(enabled = valid, onClick = { onConfirm(date.trim(), time.trim(), note.trim()) }) { Text("Send") }
        },
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun PriceRow(label: String, value: String, bold: Boolean = false) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        Text(
            value,
            style = if (bold) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium,
            fontWeight = if (bold) FontWeight.Bold else FontWeight.Normal,
            color = if (bold) GoldLight else MaterialTheme.colorScheme.onSurface,
        )
    }
}
