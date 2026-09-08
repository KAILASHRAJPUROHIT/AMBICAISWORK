package com.aradhanajewellers.app.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.Image
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aradhanajewellers.app.Business
import com.aradhanajewellers.app.R
import com.aradhanajewellers.app.ui.components.GoldDivider
import com.aradhanajewellers.app.ui.theme.Gold

@Composable
fun StoreScreen() {
    val context = LocalContext.current
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Image(
            painterResource(R.drawable.splash_logo),
            contentDescription = null,
            modifier = Modifier.size(150.dp).clip(CircleShape),
        )
        Text(Business.NAME, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(Business.TAGLINE, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(14.dp))
        GoldDivider(Modifier.fillMaxWidth())

        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
            modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
        ) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.LocationOn, null, tint = Gold)
                    Spacer(Modifier.padding(4.dp))
                    Text(Business.ADDRESS)
                }
                HorizontalDivider(color = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
                Column {
                    Business.HOURS.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }

        Spacer(Modifier.height(16.dp))
        Button(
            onClick = { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/${Business.WHATSAPP}"))) },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = Gold),
        ) {
            Icon(Icons.Default.Chat, null)
            Text("  WhatsApp Us")
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = { context.startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:${Business.PHONE}"))) },
            modifier = Modifier.fillMaxWidth(),
        ) { Icon(Icons.Default.Call, null, tint = Gold); Text("  Call the Shop") }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = {
                val map = "geo:0,0?q=${Uri.encode(Business.MAP_QUERY)}"
                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(map)))
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Icon(Icons.Default.LocationOn, null, tint = Gold); Text("  Get Directions") }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = {
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_TEXT, "${Business.NAME} — ${Business.TAGLINE}")
                }
                context.startActivity(Intent.createChooser(send, "Share"))
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Icon(Icons.Default.Share, null, tint = Gold); Text("  Share with Family") }

        Spacer(Modifier.height(20.dp))
        Text(
            "BIS Hallmark Jewellery · Transparent Wastage · Exchange Welcome",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
