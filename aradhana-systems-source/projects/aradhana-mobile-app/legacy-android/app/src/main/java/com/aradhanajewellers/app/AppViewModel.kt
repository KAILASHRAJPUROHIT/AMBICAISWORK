package com.aradhanajewellers.app

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.aradhanajewellers.app.data.GoldScheme
import com.aradhanajewellers.app.data.Product
import com.aradhanajewellers.app.data.Rates
import com.aradhanajewellers.app.data.Store
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

enum class SortMode(val label: String) {
    FEATURED("Featured"),
    PRICE_ASC("Price: Low to High"),
    PRICE_DESC("Price: High to Low"),
    WEIGHT_ASC("Weight: Light to Heavy"),
}

class AppViewModel(private val store: Store) : ViewModel() {

    val rates: StateFlow<Rates> = MutableStateFlow(store.rates)
    val ratesUpdatedAt: StateFlow<Long> = MutableStateFlow(store.ratesUpdatedAt)
    val wishlist: StateFlow<Set<String>> = MutableStateFlow(store.wishlist)
    val cart: StateFlow<Map<String, Int>> = MutableStateFlow(store.cart)
    val schemes: StateFlow<List<GoldScheme>> = MutableStateFlow(store.schemes)

    private var queryState by mutableStateOf("")
    val query: String get() = queryState
    var selectedCategory by mutableStateOf<String?>(null)
        private set
    private var sortState by mutableStateOf(SortMode.FEATURED)
    val sortMode: SortMode get() = sortState

    fun products(): List<Product> = store.products
    fun categories(): List<Pair<String, String>> = store.categories
    fun inr(value: Double): String = store.inr(value)

    fun byId(id: String): Product? = store.byId(id)
    fun featured(): List<Product> = store.products.filter { it.featured }
    fun cartCount(): Int = store.cart.values.sum()

    fun searchResults(): List<Product> {
        val q = query.trim().lowercase()
        if (q.isEmpty()) return emptyList()
        return store.products.filter {
            it.name.lowercase().contains(q) ||
                it.categoryName.lowercase().contains(q) ||
                it.purity.lowercase().contains(q)
        }
    }

    fun categoryProducts(): List<Product> {
        val list = store.products.filter { selectedCategory == null || it.category == selectedCategory }
        return when (sortMode) {
            SortMode.FEATURED -> list.sortedByDescending { it.featured }
            SortMode.PRICE_ASC -> list.sortedBy { it.priceInr(store.rates) }
            SortMode.PRICE_DESC -> list.sortedByDescending { it.priceInr(store.rates) }
            SortMode.WEIGHT_ASC -> list.sortedBy { it.netWeight }
        }
    }

    fun setQuery(q: String) { queryState = q }
    fun setCategory(key: String?) { selectedCategory = key }
    fun setSortMode(mode: SortMode) { sortState = mode }

    fun toggleWish(id: String) {
        store.toggleWish(id)
        (wishlist as MutableStateFlow).value = store.wishlist
    }

    fun addToCart(id: String) {
        store.addToCart(id)
        (cart as MutableStateFlow).value = store.cart
    }

    fun setCartQty(id: String, qty: Int) {
        store.setCartQty(id, qty)
        (cart as MutableStateFlow).value = store.cart
    }

    fun clearCart() {
        store.clearCart()
        (cart as MutableStateFlow).value = store.cart
    }

    fun createScheme(monthlyAmount: Double, monthsTotal: Int) {
        store.createScheme(monthlyAmount, monthsTotal)
        (schemes as MutableStateFlow).value = store.schemes
    }

    fun paySchemeMonth(id: String) {
        store.paySchemeMonth(id)
        (schemes as MutableStateFlow).value = store.schemes
    }

    fun removeScheme(id: String) {
        store.removeScheme(id)
        (schemes as MutableStateFlow).value = store.schemes
    }

    fun saveRates(g22: Double, g18: Double, silver: Double, gst: Double) {
        viewModelScope.launch {
            store.updateRates(g22, g18, silver, gst)
            (rates as MutableStateFlow).value = store.rates
            (ratesUpdatedAt as MutableStateFlow).value = store.ratesUpdatedAt
        }
    }

    class Factory(private val store: Store) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = AppViewModel(store) as T
    }
}
