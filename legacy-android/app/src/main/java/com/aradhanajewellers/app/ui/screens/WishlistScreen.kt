package com.aradhanajewellers.app.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aradhanajewellers.app.AppViewModel
import com.aradhanajewellers.app.ui.components.ProductImage
import com.aradhanajewellers.app.ui.theme.GoldLight

@Composable
fun WishlistScreen(vm: AppViewModel, onOpenProduct: (String) -> Unit) {
    val wishlist by vm.wishlist.collectAsStateWithLifecycle()
    val rates by vm.rates.collectAsStateWithLifecycle()
    val items = vm.products().filter { it.id in wishlist }

    if (items.isEmpty()) {
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("♥", style = MaterialTheme.typography.displayMedium, color = GoldLight)
            Spacer(Modifier.padding(6.dp))
            Text("Your wishlist is empty", color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Tap the heart on any piece to save it here.", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        return
    }

    LazyColumn(
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        items(items, key = { it.id }) { p ->
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { onOpenProduct(p.id) },
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    ProductImage(p.image, Modifier.size(84.dp))
                    Column(Modifier.padding(12.dp).weight(1f)) {
                        Text(p.name, style = MaterialTheme.typography.titleSmall)
                        Text(
                            "${p.netWeight} g · ${p.purity}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(vm.inr(p.priceInr(rates)), color = GoldLight, fontWeight = FontWeight.Bold)
                    }
                    IconButton({ vm.toggleWish(p.id) }) {
                        Icon(Icons.Default.Delete, "Remove", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}
