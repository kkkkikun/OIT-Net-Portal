package com.oitnetportal.ui

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

private val PortalLightColors = lightColorScheme(
    primary = Color(0xFF2457C5), onPrimary = Color.White,
    primaryContainer = Color(0xFFE7EEFF), onPrimaryContainer = Color(0xFF173B83),
    secondary = Color(0xFF087F72), onSecondary = Color.White,
    secondaryContainer = Color(0xFFDDF5EF), onSecondaryContainer = Color(0xFF075B53),
    background = Color(0xFFF5F7FB), onBackground = Color(0xFF17243A),
    surface = Color.White, onSurface = Color(0xFF17243A),
    surfaceVariant = Color(0xFFEEF2F8), onSurfaceVariant = Color(0xFF65738A),
    outline = Color(0xFFDCE3ED), error = Color(0xFFB42332),
    errorContainer = Color(0xFFFFE9EA), onErrorContainer = Color(0xFF7E1723),
)
private val PortalShapes = Shapes(
    extraSmall = RoundedCornerShape(8.dp), small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(18.dp), large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(28.dp),
)
@Composable
fun OitPortalTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = PortalLightColors, shapes = PortalShapes, content = content)
}
