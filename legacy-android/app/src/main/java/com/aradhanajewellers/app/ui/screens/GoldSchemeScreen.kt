package com.aradhanajewellers.app.ui.screens

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
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Savings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.aradhanajewellers.app.AppViewModel
import com.aradhanajewellers.app.data.GoldScheme
import com.aradhanajewellers.app.data.Rates
import com.aradhanajewellers.app.ui.components.GoldDivider
import com.aradhanajewellers.app.ui.theme.Gold
import com.aradhanajewellers.app.ui.theme.GoldLight

@Composable
fun GoldSchemeScreen(vm: AppViewModel) {
    val schemes by vm.schemes.collectAsStateWithLifecycle()
    val rates by vm.rates.collectAsStateWithLifecycle()
    var showCreate by remember { mutableStateOf(false) }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(bottom = 24.dp),
    ) {
        SectionTitle("Gold Savings Scheme")
        Text(
            "Save a fixed amount every month. At maturity, redeem the collected value as gold at the store — booked at the rate on each payment date (approx. shown at today's rate).",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(12.dp))
        GoldDivider(Modifier.padding(horizontal = 16.dp))
        Spacer(Modifier.height(12.dp))

        if (schemes.isEmpty()) {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
            ) {
                Column(Modifier.padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Savings, null, tint = GoldLight)
                    Spacer(Modifier.height(8.dp))
                    Text("No active plan yet", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        "Start one below — from ₹500 a month.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
        }

        schemes.forEach { scheme ->
            SchemeCard(scheme, vm, rates)
            Spacer(Modifier.height(10.dp))
        }

        Button(
            onClick = { showCreate = true },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Gold),
        ) { Text(if (schemes.isEmpty()) "Start a New Plan" else "+ Another Plan") }

        Spacer(Modifier.height(16.dp))
        Text(
            "Installments are recorded in this app and settled at the store. Terms: pay by the 10th of each month · minimum 6 months · redemption at any Aradhana Jewellers counter.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
    }

    if (showCreate) {
        CreatePlanDialog(
            onStart = { monthly, months ->
                vm.createScheme(monthly, months)
                showCreate = false
            },
            onDismiss = { showCreate = false },
        )
    }
}

@Composable
private fun SchemeCard(scheme: GoldScheme, vm: AppViewModel, rates: Rates) {
    val progress = if (scheme.monthsTotal == 0) 0f else scheme.monthsPaid.toFloat() / scheme.monthsTotal
    val approxGrams = if (rates.gold22 > 0) scheme.amountPaid / rates.gold22 else 0.0

    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("${scheme.id} · ${vm.inr(scheme.monthlyAmount)}/month", fontWeight = FontWeight.Bold)
                    Text(
                        "${scheme.monthsTotal} months",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(
                    if (scheme.isComplete) "Matured" else "${scheme.monthsPaid}/${scheme.monthsTotal} paid",
                    style = MaterialTheme.typography.labelMedium,
                    color = if (scheme.isComplete) GoldLight else MaterialTheme.colorScheme.onSurfaceVariant,
                    fontWeight = FontWeight.Bold,
                )
            }

            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier.fillMaxWidth(),
                color = Gold,
                trackColor = MaterialTheme.colorScheme.surface,
            )

            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Paid so far: ${vm.inr(scheme.amountPaid)}")
                    Text(
                        "≈ %.2f g gold at today's rate".format(approxGrams),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (!scheme.isComplete) {
                    FilledTonalButton(onClick = { vm.paySchemeMonth(scheme.id) }) {
                        Text("Mark Month Paid")
                    }
                } else {
                    IconButton(onClick = { vm.removeScheme(scheme.id) }) {
                        Icon(Icons.Default.Delete, "Remove plan", tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }

            if (scheme.isComplete) {
                Text(
                    "Plan matured — visit the store with this phone to redeem your gold.",
                    style = MaterialTheme.typography.labelSmall,
                    color = GoldLight,
                )
            }
        }
    }
}

@Composable
private fun CreatePlanDialog(
    onStart: (monthly: Double, months: Int) -> Unit,
    onDismiss: () -> Unit,
) {
    var amount by remember { mutableStateOf("") }
    var months by remember { mutableStateOf(11) }

    val amountValue = amount.toDoubleOrNull()
    val valid = amountValue != null && amountValue >= 500 && amountValue <= 100000

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New Savings Plan") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    amount, { amount = it },
                    label = { Text("Monthly amount (₹)") },
                    isError = amount.isNotBlank() && !valid,
                    supportingText = {
                        if (amount.isNotBlank() && !valid) Text("Enter between ₹500 and ₹1,00,000")
                    },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    singleLine = true,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(1000, 2500, 5000).forEach { preset ->
                        FilterChip(
                            selected = amountValue == preset.toDouble(),
                            onClick = { amount = preset.toString() },
                            label = { Text("₹$preset") },
                        )
                    }
                }
                Text("Duration", style = MaterialTheme.typography.labelMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(6, 11, 12).forEach { m ->
                        FilterChip(
                            selected = months == m,
                            onClick = { months = m },
                            label = { Text("$m months") },
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = valid, onClick = { onStart(amountValue ?: return@TextButton, months) }) {
                Text("Start Plan")
            }
        },
        dismissButton = { TextButton(onDismiss) { Text("Cancel") } },
    )
}
