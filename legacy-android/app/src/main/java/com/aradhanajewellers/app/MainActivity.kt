package com.aradhanajewellers.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.GridView
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.aradhanajewellers.app.data.Store
import com.aradhanajewellers.app.ui.screens.CatalogueScreen
import com.aradhanajewellers.app.ui.screens.CartScreen
import com.aradhanajewellers.app.ui.screens.GoldSchemeScreen
import com.aradhanajewellers.app.ui.screens.HomeScreen
import com.aradhanajewellers.app.ui.screens.ProductDetailScreen
import com.aradhanajewellers.app.ui.screens.SearchScreen
import com.aradhanajewellers.app.ui.screens.StoreScreen
import com.aradhanajewellers.app.ui.screens.WishlistScreen
import com.aradhanajewellers.app.ui.theme.DeepNavy
import com.aradhanajewellers.app.ui.theme.Gold
import com.aradhanajewellers.app.ui.theme.TextSecondary

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val store = Store.get(this)
        setContent {
            com.aradhanajewellers.app.ui.theme.AradhanaTheme {
                AppRoot(store)
            }
        }
    }
}

private data class BottomItem(val route: String, val label: String, val icon: @Composable () -> Unit)

@Composable
fun AppRoot(store: Store) {
    val vm: AppViewModel = viewModel(factory = AppViewModel.Factory(store))
    val nav = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val context = LocalContext.current

    val items = listOf(
        BottomItem("home", "Home") { Icon(Icons.Default.Home, null) },
        BottomItem("catalogue", "Catalogue") { Icon(Icons.Default.GridView, null) },
        BottomItem("cart", "Cart") { Icon(Icons.Default.ShoppingCart, null) },
        BottomItem("wishlist", "Wishlist") { Icon(Icons.Default.Favorite, null) },
        BottomItem("store", "Store") { Icon(Icons.Default.Storefront, null) },
    )

    Scaffold(
        containerColor = DeepNavy,
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surface) {
                items.forEach { item ->
                    NavigationBarItem(
                        selected = currentRoute == item.route,
                        onClick = {
                            nav.navigate(item.route) {
                                popUpTo("home") { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = {
                            if (item.route == "cart") {
                                BadgedBox(
                                    badge = {
                                        val count = vm.cartCount()
                                        if (count > 0) Badge { Text("$count") }
                                    },
                                ) { item.icon() }
                            } else {
                                item.icon()
                            }
                        },
                        label = { Text(item.label, style = MaterialTheme.typography.labelSmall) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Gold,
                            selectedTextColor = Gold,
                            unselectedIconColor = TextSecondary,
                            unselectedTextColor = TextSecondary,
                            indicatorColor = Gold.copy(alpha = 0.15f),
                        ),
                    )
                }
            }
        },
        floatingActionButton = {
            if (currentRoute != "store" && currentRoute != "cart") {
                FloatingActionButton(
                    onClick = {
                        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/${Business.WHATSAPP}")))
                    },
                    containerColor = Gold,
                    contentColor = DeepNavy,
                ) { Icon(Icons.Default.Chat, "WhatsApp us") }
            }
        },
    ) { padding ->
        NavHost(
            navController = nav,
            startDestination = "home",
            modifier = Modifier.padding(padding),
        ) {
            composable("home") {
                HomeScreen(
                    vm,
                    onOpenProduct = { nav.navigate("product/$it") },
                    onOpenCategory = { nav.navigate("catalogue?category=$it") },
                    onOpenSearch = { nav.navigate("search") },
                    onOpenScheme = { nav.navigate("scheme") },
                )
            }
            composable(
                route = "catalogue?category={category}",
                arguments = listOf(navArgument("category") { type = NavType.StringType; nullable = true; defaultValue = null }),
            ) { entry ->
                CatalogueScreen(vm, entry.arguments?.getString("category")) { id -> nav.navigate("product/$id") }
            }
            composable("product/{id}") { entry ->
                ProductDetailScreen(vm, entry.arguments?.getString("id").orEmpty())
            }
            composable("search") { SearchScreen(vm) { id -> nav.navigate("product/$id") } }
            composable("cart") { CartScreen(vm) }
            composable("wishlist") { WishlistScreen(vm) { id -> nav.navigate("product/$id") } }
            composable("store") { StoreScreen() }
            composable("scheme") { GoldSchemeScreen(vm) }
        }
    }
}
