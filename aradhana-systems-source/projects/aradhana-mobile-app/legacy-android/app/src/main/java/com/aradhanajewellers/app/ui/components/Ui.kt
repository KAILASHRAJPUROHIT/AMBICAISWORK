package com.aradhanajewellers.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.aradhanajewellers.app.ui.theme.DeepNavy
import com.aradhanajewellers.app.ui.theme.Gold
import com.aradhanajewellers.app.ui.theme.GoldDeep
import com.aradhanajewellers.app.ui.theme.GoldLight

val GoldBrush = Brush.horizontalGradient(listOf(GoldDeep, Gold, GoldLight))
val CardShape = RoundedCornerShape(18.dp)
val ButtonShape = RoundedCornerShape(14.dp)

@Composable
fun GoldButton(
    text: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    val click = onClick
    Box(modifier = modifier.background(GoldBrush, ButtonShape)) {
        Button(
            onClick = { if (enabled) click() },
            enabled = enabled,
            shape = ButtonShape,
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Color.Transparent,
                contentColor = DeepNavy,
                disabledContainerColor = Color.Transparent,
                disabledContentColor = DeepNavy.copy(alpha = 0.4f),
            ),
            elevation = ButtonDefaults.buttonElevation(defaultElevation = 0.dp, pressedElevation = 0.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (icon != null) Icon(icon, contentDescription = null)
            Text(" " + text, style = MaterialTheme.typography.labelLarge)
        }
    }
}

@Composable
fun GhostButton(
    text: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    fillWidth: Boolean = false,
    onClick: () -> Unit,
) {
    OutlinedButton(
        onClick = onClick,
        shape = ButtonShape,
        border = BorderStroke(1.dp, Gold.copy(alpha = 0.45f)),
        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 10.dp),
        modifier = if (fillWidth) modifier.fillMaxWidth() else modifier,
    ) {
        if (icon != null) Icon(icon, contentDescription = null, tint = GoldLight)
        Text(" " + text, style = MaterialTheme.typography.labelMedium, color = GoldLight)
    }
}

@Composable
fun SectionHeader(title: String, trailing: (@Composable () -> Unit)? = null) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 16.dp, end = 16.dp, top = 14.dp, bottom = 8.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(6.dp))
            Box(
                Modifier
                    .size(width = 42.dp, height = 2.dp)
                    .background(GoldBrush, RoundedCornerShape(2.dp)),
            )
        }
        if (trailing != null) trailing()
    }
}

/** White studio photos sit on an ivory "frame" so they look intentional, not pasted. */
@Composable
fun ProductFrame(imagePath: String, modifier: Modifier = Modifier) {
    Surface(
        color = Color.White,
        shape = CardShape,
        border = BorderStroke(1.dp, Gold.copy(alpha = 0.25f)),
        modifier = modifier,
    ) {
        AsyncImage(
            model = "file:///android_asset/$imagePath",
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .fillMaxSize()
                .clip(CardShape),
        )
    }
}

@Composable
fun EmptyState(icon: ImageVector, title: String, subtitle: String) {
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 48.dp, horizontal = 24.dp),
    ) {
        Surface(
            shape = CircleShape,
            color = Gold.copy(alpha = 0.12f),
            border = BorderStroke(1.dp, Gold.copy(alpha = 0.35f)),
        ) {
            Icon(
                icon,
                contentDescription = null,
                tint = GoldLight,
                modifier = Modifier
                    .padding(22.dp)
                    .size(30.dp),
            )
        }
        Spacer(Modifier.height(16.dp))
        Text(title, style = MaterialTheme.typography.titleLarge)
        Spacer(Modifier.height(4.dp))
        Text(subtitle, style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center)
    }
}
