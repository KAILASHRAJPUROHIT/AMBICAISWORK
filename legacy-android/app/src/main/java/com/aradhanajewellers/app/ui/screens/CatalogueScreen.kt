package com.aradhanajewellers.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aradhanajewellers.app.AppViewModel
import com.aradhanajewellers.app.SortMode
import com.aradhanajewellers.app.data.Product
import com.aradhanajewellers.app.ui.components.ProductImage
import com.aradhanajewellers.app.ui.theme.DeepNavy
import com.aradhanajewellers.app.ui.theme.Gold
import com.aradhanajewellers.app.ui.theme.GoldLight

@Composable
fun CatalogueScreen(vm: AppViewModel, initialCategory: String?, onOpenProduct: (String) -> Unit) {
    if (initialCategory != null && vm.selectedCategory != initialCategory) vm.setCategory(initialCategory)
    val wishlist by vm.wishlist.collectAsStateWithLifecycle()
    var sortExpanded by remember { mutableStateOf(false) }
    val products = vm.categoryProducts()

    Column(Modifier.fillMaxSize()) {
        LazyRow(
            contentPadding = PaddingValues(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.padding(vertical = 8.dp),
        ) {
            item {
                FilterChip(
                    selected = vm.selectedCategory == null,
                    onClick = { vm.setCategory(null) },
                    label = { Text("All") },
                )
            }
            items(vm.categories().toList(), key = { it.first }) { (key, label) ->
                FilterChip(
                    selected = vm.selectedCategory == key,
                    onClick = { vm.setCategory(if (vm.selectedCategory == key) null else key) },
                    label = { Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                )
            }
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                "${products.size} designs",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.weight(1f),
            )
            Box {
                TextButton(onClick = { sortExpanded = true }) {
                    Text(
                        "Sort: ${vm.sortMode.label}",
                        style = MaterialTheme.typography.labelMedium,
                        color = GoldLight,
                    )
                    Icon(Icons.Default.ArrowDropDown, contentDescription = null, tint = GoldLight)
                }
                DropdownMenu(
                    expanded = sortExpanded,
                    onDismissRequest = { sortExpanded = false },
                ) {
                    SortMode.entries.forEach { mode ->
                        DropdownMenuItem(
                            text = {
                                Text(
                                    mode.label,
                                    color = if (mode == vm.sortMode) GoldLight else MaterialTheme.colorScheme.onSurface,
                                )
                            },
                            onClick = {
                                vm.setSortMode(mode)
                                sortExpanded = false
                            },
                        )
                    }
                }
            }
        }

        LazyVerticalGrid(
            columns = GridCells.Fixed(2),
            contentPadding = PaddingValues(12.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            modifier = Modifier.fillMaxSize(),
        ) {
            items(products, key = { it.id }) { p ->
                ProductGridCard(p, vm, wishlist, onOpenProduct)
            }
        }
    }
}

@Composable
private fun ProductGridCard(
    product: Product,
    vm: AppViewModel,
    wishlist: Set<String>,
    onOpenProduct: (String) -> Unit,
) {
    val rates by vm.rates.collectAsStateWithLifecycle()
    Card(
        modifier = Modifier.clickable { onOpenProduct(product.id) },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column {
            ProductImage(product.image, Modifier.fillMaxWidth().aspectRatio(1f))
            Column(Modifier.padding(10.dp)) {
                Text(
                    product.name,
                    style = MaterialTheme.typography.titleSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    "${product.netWeight} g · ${product.purity}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        vm.inr(product.priceInr(rates)),
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        color = GoldLight,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f),
                    )
                    Box(
                        modifier = Modifier
                            .padding(end = 8.dp)
                            .size(28.dp)
                            .background(Gold, CircleShape)
                            .clickable { vm.addToCart(product.id) },
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(Icons.Default.Add, contentDescription = "Add to cart", tint = DeepNavy, modifier = Modifier.size(17.dp))
                    }
                    Icon(
                        if (product.id in wishlist) Icons.Default.Favorite else Icons.Default.FavoriteBorder,
                        contentDescription = null,
                        tint = Gold,
                        modifier = Modifier
                            .height(18.dp)
                            .clickable { vm.toggleWish(product.id) },
                    )
                }
            }
        }
    }
}
