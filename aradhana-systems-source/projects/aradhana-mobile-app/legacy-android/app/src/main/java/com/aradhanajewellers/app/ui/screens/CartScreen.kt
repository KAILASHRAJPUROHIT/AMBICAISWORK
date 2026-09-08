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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aradhanajewellers.app.AppViewModel
import com.aradhanajewellers.app.Business
import com.aradhanajewellers.app.data.Product
import com.aradhanajewellers.app.ui.components.GoldDivider
import com.aradhanajewellers.app.ui.components.ProductImage
import com.aradhanajewellers.app.ui.theme.Gold
import com.aradhanajewellers.app.ui.theme.GoldLight

@Composable
fun CartScreen(vm: AppViewModel) {
    val cart by vm.cart.collectAsStateWithLifecycle()
    val rates by vm.rates.collectAsStateWithLifecycle()
    val context = LocalContext.current

    val lines = cart.entries.mapNotNull { (id, qty) -> vm.byId(id)?.let { it to qty } }

    if (lines.isEmpty()) {
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Icon(Icons.Default.ShoppingCart, null, tint = GoldLight, modifier = Modifier.size(56.dp))
            Spacer(Modifier.padding(6.dp))
            Text("Your cart is empty", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                "Tap + on any piece to add it here.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        return
    }

    var metalTotal = 0.0
    var makingTotal = 0.0
    lines.forEach { (p, qty) ->
        metalTotal += p.netWeight * p.metalRate(rates) * qty
        makingTotal += p.netWeight * p.makingPerGram * qty
    }
    val gstTotal = (metalTotal + makingTotal) * rates.gstPercent / 100.0
    val grandTotal = metalTotal + makingTotal + gstTotal

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${lines.sumOf { it.second }} item(s)",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = { vm.clearCart() }) { Text("Clear all") }
        }
        Spacer(Modifier.height(4.dp))

        lines.forEach { (product, qty) ->
            CartLineCard(product, qty, vm)
            Spacer(Modifier.height(10.dp))
        }

        Spacer(Modifier.height(6.dp))
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                PriceRow("Gold value", vm.inr(metalTotal))
                PriceRow("Making charges", vm.inr(makingTotal))
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.4f))
                PriceRow("GST (${rates.gstPercent}%)", vm.inr(gstTotal))
                PriceRow("Total", vm.inr(grandTotal), bold = true)
            }
        }

        Spacer(Modifier.height(16.dp))
        Button(
            onClick = {
                val body = lines.joinToString("\n") { (p, qty) ->
                    "${qty} x ${p.name} (${p.code}) - ${vm.inr(p.priceInr(rates) * qty)}"
                }
                val msg = "Hi ${Business.NAME}, I'd like to book these pieces:\n$body\nApprox total at today's rate: ${vm.inr(grandTotal)}. Please confirm availability & final price."
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/${Business.WHATSAPP}?text=${Uri.encode(msg)}")))
            },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = Gold),
        ) {
            Icon(Icons.Default.Chat, null)
            Text("  Send Order on WhatsApp")
        }
        Spacer(Modifier.height(8.dp))
        Text(
            "Cart prices move with the daily gold rate — final price is confirmed by the store.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun CartLineCard(product: Product, qty: Int, vm: AppViewModel) {
    val rates by vm.rates.collectAsStateWithLifecycle()
    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ProductImage(product.image, Modifier.size(76.dp))
            Column(Modifier.padding(horizontal = 10.dp).weight(1f)) {
                Text(product.name, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(
                    "${product.code} · ${product.netWeight} g · ${product.purity}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilledIconButton(
                        onClick = { vm.setCartQty(product.id, qty - 1) },
                        modifier = Modifier.size(28.dp),
                        colors = IconButtonDefaults.filledIconButtonColors(containerColor = MaterialTheme.colorScheme.surface),
                    ) { Icon(Icons.Default.Remove, "Decrease", tint = Gold, modifier = Modifier.size(16.dp)) }
                    Text("$qty", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                    FilledIconButton(
                        onClick = { vm.setCartQty(product.id, qty + 1) },
                        modifier = Modifier.size(28.dp),
                        colors = IconButtonDefaults.filledIconButtonColors(containerColor = Gold.copy(alpha = 0.2f)),
                    ) { Icon(Icons.Default.Add, "Increase", tint = GoldLight, modifier = Modifier.size(16.dp)) }
                    Spacer(Modifier.weight(1f))
                    Text(vm.inr(product.priceInr(rates) * qty), color = GoldLight, fontWeight = FontWeight.Bold)
                }
            }
            IconButton(onClick = { vm.setCartQty(product.id, 0) }) {
                Icon(Icons.Default.Delete, "Remove", tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
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
