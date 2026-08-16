package com.ismiseeanna.garminui.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Ported from the Modernist design system's styles.css: a near-mono red on
// white, zero corner radius, and strong 2px dividers.
val GarminBackground = Color(0xFFF3F2F2)
val GarminText = Color(0xFF201E1D)
val GarminAccent = Color(0xFFEC3013)
val GarminAccent700 = Color(0xFFB0230D) // deep step of the accent ramp, for text on light ground
val GarminNeutral700 = Color(0xFF6B6866)
val GarminDivider = GarminText

// The design system pairs Archivo for both headings and body (readme.md
// "Type"). Wiring up the Google Fonts Downloadable Fonts provider needs a
// certificate-hash resource array that can't be verified without a device
// to run against, so this ships on the platform sans-serif for now — drop
// in a bundled Archivo .ttf under res/font/ (or the Google Fonts provider,
// once you can test it) to match the mockup exactly.
private val garminFont = FontFamily.SansSerif

val GarminTypography = Typography(
    bodyLarge = TextStyle(fontFamily = garminFont, fontWeight = FontWeight.Normal, fontSize = 14.sp),
    bodyMedium = TextStyle(fontFamily = garminFont, fontWeight = FontWeight.Normal, fontSize = 14.sp),
    titleLarge = TextStyle(
        fontFamily = garminFont,
        fontWeight = FontWeight.Bold,
        fontSize = 20.sp,
        letterSpacing = (-0.2).sp,
    ),
    headlineSmall = TextStyle(fontFamily = garminFont, fontWeight = FontWeight.Bold, fontSize = 34.sp),
    labelSmall = TextStyle(
        fontFamily = garminFont,
        fontWeight = FontWeight.Normal,
        fontSize = 11.sp,
        letterSpacing = 0.9.sp,
    ),
)

private val GarminColorScheme = lightColorScheme(
    primary = GarminAccent,
    onPrimary = Color.White,
    background = GarminBackground,
    onBackground = GarminText,
    surface = GarminBackground,
    onSurface = GarminText,
    outline = GarminDivider,
)

@Composable
fun GarminUiTheme(content: @Composable () -> Unit) {
    // The Modernist system is a single light, ink-on-ground scheme by design
    // (readme.md: "a light ground ... with a single accent") — there is no
    // dark variant, so this doesn't branch on system dark mode.
    MaterialTheme(
        colorScheme = GarminColorScheme,
        typography = GarminTypography,
        content = content,
    )
}
