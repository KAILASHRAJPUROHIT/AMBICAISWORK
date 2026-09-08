package com.aradhanajewellers.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.aradhanajewellers.app.R

val Playfair = FontFamily(
    Font(R.font.playfair_display_600, FontWeight.SemiBold),
    Font(R.font.playfair_display_700, FontWeight.Bold),
)

val Inter = FontFamily(
    Font(R.font.inter_400, FontWeight.Normal),
    Font(R.font.inter_500, FontWeight.Medium),
    Font(R.font.inter_600, FontWeight.SemiBold),
)

private val AppTypography = Typography(
    headlineLarge = TextStyle(fontFamily = Playfair, fontWeight = FontWeight.Bold, fontSize = 32.sp, lineHeight = 38.sp, color = TextPrimary),
    headlineMedium = TextStyle(fontFamily = Playfair, fontWeight = FontWeight.Bold, fontSize = 26.sp, lineHeight = 32.sp, color = TextPrimary),
    headlineSmall = TextStyle(fontFamily = Playfair, fontWeight = FontWeight.Bold, fontSize = 22.sp, lineHeight = 28.sp, color = TextPrimary),
    titleLarge = TextStyle(fontFamily = Playfair, fontWeight = FontWeight.SemiBold, fontSize = 20.sp, lineHeight = 26.sp, color = TextPrimary),
    titleMedium = TextStyle(fontFamily = Inter, fontWeight = FontWeight.SemiBold, fontSize = 16.sp, lineHeight = 22.sp, color = TextPrimary),
    titleSmall = TextStyle(fontFamily = Inter, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 20.sp, color = TextPrimary),
    bodyLarge = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 24.sp, color = TextPrimary),
    bodyMedium = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 14.sp, lineHeight = 21.sp, color = TextPrimary),
    bodySmall = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Normal, fontSize = 12.sp, lineHeight = 18.sp, color = TextSecondary),
    labelLarge = TextStyle(fontFamily = Inter, fontWeight = FontWeight.SemiBold, fontSize = 15.sp, lineHeight = 20.sp, color = TextPrimary),
    labelMedium = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Medium, fontSize = 12.sp, lineHeight = 16.sp, letterSpacing = 0.4.sp, color = TextSecondary),
    labelSmall = TextStyle(fontFamily = Inter, fontWeight = FontWeight.Medium, fontSize = 11.sp, lineHeight = 15.sp, letterSpacing = 0.6.sp, color = TextSecondary),
)

private val Scheme = darkColorScheme(
    primary = Gold,
    onPrimary = DeepNavy,
    secondary = GoldLight,
    onSecondary = DeepNavy,
    tertiary = SuccessGreen,
    background = DeepNavy,
    onBackground = TextPrimary,
    surface = NavySurface,
    onSurface = TextPrimary,
    surfaceVariant = NavyCard,
    onSurfaceVariant = TextSecondary,
    outline = GoldDeep,
)

@Composable
fun AradhanaTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = Scheme,
        typography = AppTypography,
        content = content,
    )
}
