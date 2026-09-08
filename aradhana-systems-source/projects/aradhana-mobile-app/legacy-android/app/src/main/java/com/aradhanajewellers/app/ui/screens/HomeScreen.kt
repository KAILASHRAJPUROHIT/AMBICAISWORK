package com.aradhanajewellers.app.ui.screens

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.ChildCare
import androidx.compose.material.icons.filled.Circle
import androidx.compose.material.icons.filled.DonutLarge
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Female
import androidx.compose.material.icons.filled.Hearing
import androidx.compose.material.icons.filled.Male
import androidx.compose.material.icons.filled.Savings
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aradhanajewellers.app.AppViewModel
import com.aradhanajewellers.app.R
import com.aradhanajewellers.app.data.Product
import com.aradhanajewellers.app.ui.components.GoldDivider
import com.aradhanajewellers.app.ui.components.ProductImage
import com.aradhanajewellers.app.ui.theme.DeepNavy
import com.aradhanajewellers.app.ui.theme.Gold
import com.aradhanajewellers.app.ui.theme.GoldLight
import com.aradhanajewellers.app.ui.theme.Ivory
import com.aradhanajewellers.app.ui.theme.RoyalBlue
import kotlinx.coroutines.delay

private data class PromoBanner(
    val title: String,
    val subtitle: String,
    val start: Color,
    val end: Color,
)

private fun categoryIcon(key: String): ImageVector = when (key) {
    "gents_ring" -> Icons.Default.Male
    "ladies_ring" -> Icons.Default.Female
    "earring" -> Icons.Default.Hearing
    "jhumka" -> Icons.Default.AutoAwesome
    "bangle" -> Icons.Default.DonutLarge
    "bali" -> Icons.Default.Circle
    "wati" -> Icons.Default.ChildCare
    else -> Icons.Default.Star
}

private fun formatUpdated(millis: Long): String {
    val cal = java.util.Calendar.getInstance().apply { timeInMillis = millis }
    val now = java.util.Calendar.getInstance()
    val sameDay = cal.get(java.util.Calendar.YEAR) == now.get(java.util.Calendar.YEAR) &&
        cal.get(java.util.Calendar.DAY_OF_YEAR) == now.get(java.util.Calendar.DAY_OF_YEAR)
    val fmt = if (sameDay) {
        java.text.SimpleDateFormat("'Updated today,' hh:mm a", java.util.Locale.ENGLISH)
    } else {
        java.text.SimpleDateFormat("'Updated' dd MMM, hh:mm a", java.util.Locale.ENGLISH)
    }
    return fmt.format(java.util.Date(millis))
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    vm: AppViewModel,
    onOpenProduct: (String) -> Unit,
    onOpenCategory: (String) -> Unit,
    onOpenSearch: () -> Unit,
    onOpenScheme: () -> Unit,
) {
    val rates by vm.rates.collectAsStateWithLifecycle()
    val updatedAt by vm.ratesUpdatedAt.collectAsStateWithLifecycle()
    var showRateDialog by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(bottom = 24.dp),
    ) {
        // Brand hero
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.verticalGradient(listOf(MaterialTheme.colorScheme.surface, MaterialTheme.colorScheme.background))),
        ) {
            Image(
                painter = painterResource(R.drawable.splash_logo),
                contentDescription = null,
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(vertical = 10.dp)
                    .size(width = 180.dp, height = 180.dp),
            )
        }
        GoldDivider()

        // Search entry point
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            shape = RoundedCornerShape(28.dp),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp)
                .clickable(onClick = onOpenSearch),
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Icon(Icons.Default.Search, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    "Search rings, earrings, bangles…",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        BannerCarousel()

        // Live rates
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            RateCard("Gold 22K", "₹ %,.0f".format(rates.gold22), "/g", Modifier.weight(1f))
            RateCard("Gold 18K", "₹ %,.0f".format(rates.gold18), "/g", Modifier.weight(1f))
            RateCard("Silver", "₹ %,.0f".format(rates.silver), "/g", Modifier.weight(1f))
            IconButton(onClick = { showRateDialog = true }) {
                Icon(Icons.Default.Edit, contentDescription = "Update rates", tint = Gold)
            }
        }
        Text(
            formatUpdated(updatedAt),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .padding(top = 2.dp),
            textAlign = androidx.compose.ui.text.style.TextAlign.End,
        )

        SectionTitle("Shop by Category")
        LazyRow(
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            items(vm.categories(), key = { it.first }) { (key, label) ->
                CategoryTile(label, categoryIcon(key)) { onOpenCategory(key) }
            }
        }

        SectionTitle("Featured")
        LazyRow(
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(vm.featured(), key = { it.id }) { p ->
                FeaturedCard(p, vm) { onOpenProduct(p.id) }
            }
        }

        Spacer(Modifier.height(8.dp))
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
                .clickable(onClick = onOpenScheme),
        ) {
            Row(
                modifier = Modifier.padding(14.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Box(
                    modifier = Modifier
                        .size(44.dp)
                        .background(Gold.copy(alpha = 0.15f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Default.Savings, contentDescription = null, tint = GoldLight)
                }
                Column(Modifier.weight(1f)) {
                    Text("Gold Savings Scheme", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onSurface)
                    Text(
                        "Save monthly · Redeem at the store",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Icon(Icons.Default.ChevronRight, contentDescription = null, tint = Gold)
            }
        }
    }

    if (showRateDialog) {
        RateDialog(
            current = rates,
            onSave = { g22, g18, ag, gst -> vm.saveRates(g22, g18, ag, gst); showRateDialog = false },
            onDismiss = { showRateDialog = false },
        )
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun BannerCarousel() {
    val banners = listOf(
        PromoBanner("BIS Hallmark 916", "Purity you can trust, on every piece", RoyalBlue, DeepNavy),
        PromoBanner("Gold Savings Scheme", "Save monthly — redeem at the store", DeepNavy, com.aradhanajewellers.app.ui.theme.NavyCard),
        PromoBanner("Old Gold Exchange", "Transparent wastage, fair value", com.aradhanajewellers.app.ui.theme.GoldDeep, DeepNavy),
    )
    val pagerState = rememberPagerState(pageCount = { banners.size })

    LaunchedEffect(pagerState.pageCount) {
        while (true) {
            delay(4000)
            val next = (pagerState.currentPage + 1) % pagerState.pageCount
            runCatching { pagerState.animateScrollToPage(next) }
        }
    }

    Column(Modifier.padding(bottom = 8.dp)) {
        HorizontalPager(
            state = pagerState,
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
            pageSpacing = 10.dp,
        ) { page ->
            val banner = banners[page]
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(120.dp)
                    .clip(RoundedCornerShape(16.dp))
                    .background(Brush.horizontalGradient(listOf(banner.start, banner.end))),
            ) {
                Column(Modifier.align(Alignment.CenterStart).padding(horizontal = 20.dp)) {
                    Text(
                        banner.title,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = Ivory,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(banner.subtitle, style = MaterialTheme.typography.bodySmall, color = GoldLight)
                }
                Text(
                    "✦",
                    color = Gold.copy(alpha = 0.35f),
                    style = MaterialTheme.typography.displayMedium,
                    modifier = Modifier.align(Alignment.CenterEnd).padding(end = 18.dp),
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp),
            horizontalArrangement = Arrangement.Center,
        ) {
            repeat(banners.size) { i ->
                val selected = pagerState.currentPage == i
                Box(
                    modifier = Modifier
                        .padding(horizontal = 3.dp)
                        .size(width = if (selected) 18.dp else 6.dp, height = 6.dp)
                        .clip(CircleShape)
                        .background(if (selected) Gold else MaterialTheme.colorScheme.outline),
                )
            }
        }
    }
}

@Composable
private fun CategoryTile(label: String, icon: ImageVector, onClick: () -> Unit) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier.width(76.dp).clickable(onClick = onClick),
    ) {
        Box(
            modifier = Modifier
                .size(56.dp)
                .background(Gold.copy(alpha = 0.15f), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = label, tint = GoldLight, modifier = Modifier.size(26.dp))
        }
        Spacer(Modifier.height(6.dp))
        Text(
            label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onBackground,
            maxLines = 1,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
    }
}

@Composable
private fun RateCard(title: String, value: String, unit: String, modifier: Modifier = Modifier) {
    Card(modifier = modifier, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(12.dp)) {
            Text(title, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(4.dp))
            Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = GoldLight)
            Text(unit, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun SectionTitle(text: String) {
    Column {
        Text(
            text,
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
        )
    }
}

@Composable
fun FeaturedCard(product: Product, vm: AppViewModel, onClick: () -> Unit) {
    val wishlist by vm.wishlist.collectAsStateWithLifecycle()
    Card(
        modifier = Modifier
            .width(230.dp)
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        ProductImage(product.image, Modifier.fillMaxWidth().height(170.dp))
        Column(Modifier.padding(12.dp)) {
            Text(product.name, style = MaterialTheme.typography.titleSmall, maxLines = 1)
            Text(
                product.purity,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    vm.inr(product.priceInr(vm.rates.value)),
                    style = MaterialTheme.typography.titleMedium,
                    color = GoldLight,
                )
                Spacer(Modifier.weight(1f))
                Box(
                    modifier = Modifier
                        .padding(end = 8.dp)
                        .size(30.dp)
                        .background(Gold, CircleShape)
                        .clickable { vm.addToCart(product.id) },
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(Icons.Default.Add, contentDescription = "Add to cart", tint = DeepNavy, modifier = Modifier.size(18.dp))
                }
                Icon(
                    if (product.id in wishlist) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                    contentDescription = null,
                    tint = Gold,
                    modifier = Modifier
                        .size(22.dp)
                        .clickable { vm.toggleWish(product.id) },
                )
            }
        }
    }
}

@Composable
private fun RateDialog(
    current: com.aradhanajewellers.app.data.Rates,
    onSave: (Double, Double, Double, Double) -> Unit,
    onDismiss: () -> Unit,
) {
    var g22 by remember { mutableStateOf(current.gold22.toString()) }
    var g18 by remember { mutableStateOf(current.gold18.toString()) }
    var silver by remember { mutableStateOf(current.silver.toString()) }
    var gst by remember { mutableStateOf(current.gstPercent.toString()) }

    fun validRate(s: String) = s.toDoubleOrNull()?.let { it > 0 } == true
    fun validGst(s: String) = s.toDoubleOrNull()?.let { it in 0.0..100.0 } == true
    val allValid = validRate(g22) && validRate(g18) && validRate(silver) && validGst(gst)

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Today's Rates") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    g22, { g22 = it },
                    label = { Text("Gold 22K /g") },
                    isError = !validRate(g22),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                )
                OutlinedTextField(
                    g18, { g18 = it },
                    label = { Text("Gold 18K /g") },
                    isError = !validRate(g18),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                )
                OutlinedTextField(
                    silver, { silver = it },
                    label = { Text("Silver /g") },
                    isError = !validRate(silver),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                )
                OutlinedTextField(
                    gst, { gst = it },
                    label = { Text("GST % (0–100)") },
                    isError = !validGst(gst),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = allValid,
                onClick = {
                    onSave(
                        g22.toDoubleOrNull() ?: return@TextButton,
                        g18.toDoubleOrNull() ?: return@TextButton,
                        silver.toDoubleOrNull() ?: return@TextButton,
                        gst.toDoubleOrNull() ?: return@TextButton,
                    )
                },
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } },
    )
}
