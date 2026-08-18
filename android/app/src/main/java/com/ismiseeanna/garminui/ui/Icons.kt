package com.ismiseeanna.garminui.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

// Simple hand-drawn glyphs mirroring the prototype's inline SVGs (bar chart /
// speech bubble / wifi signal), since the Modernist system calls for Lucide
// icons and no icon library is wired up in this scaffold.

@Composable
fun DashboardIcon(tint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.size(22.dp)) {
        val strokeWidth = 2.dp.toPx()
        val w = size.width
        val h = size.height
        drawLine(tint, Offset(w * 0.18f, h * 0.9f), Offset(w * 0.18f, h * 0.45f), strokeWidth, StrokeCap.Round)
        drawLine(tint, Offset(w * 0.5f, h * 0.9f), Offset(w * 0.5f, h * 0.18f), strokeWidth, StrokeCap.Round)
        drawLine(tint, Offset(w * 0.82f, h * 0.9f), Offset(w * 0.82f, h * 0.68f), strokeWidth, StrokeCap.Round)
    }
}

@Composable
fun ChatIcon(tint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.size(22.dp)) {
        val stroke = Stroke(width = 2.dp.toPx())
        val w = size.width
        val h = size.height
        val path = Path().apply {
            moveTo(w * 0.1f, h * 0.15f)
            lineTo(w * 0.95f, h * 0.15f)
            lineTo(w * 0.95f, h * 0.65f)
            lineTo(w * 0.35f, h * 0.65f)
            lineTo(w * 0.15f, h * 0.9f)
            lineTo(w * 0.15f, h * 0.65f)
            lineTo(w * 0.1f, h * 0.65f)
            close()
        }
        drawPath(path, tint, style = stroke)
    }
}

@Composable
fun PlanIcon(tint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.size(22.dp)) {
        val strokeWidth = 2.dp.toPx()
        val w = size.width
        val h = size.height
        drawLine(tint, Offset(w * 0.22f, h * 0.9f), Offset(w * 0.22f, h * 0.12f), strokeWidth, StrokeCap.Round)
        val pennant = Path().apply {
            moveTo(w * 0.22f, h * 0.15f)
            lineTo(w * 0.82f, h * 0.32f)
            lineTo(w * 0.22f, h * 0.5f)
            close()
        }
        drawPath(pennant, tint, style = Stroke(width = strokeWidth))
    }
}

@Composable
fun StatusIcon(tint: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.size(22.dp)) {
        val stroke = Stroke(width = 2.dp.toPx(), cap = StrokeCap.Round)
        val w = size.width
        val h = size.height
        val cx = w / 2f
        val dotY = h * 0.86f
        drawArc(
            tint,
            startAngle = 200f,
            sweepAngle = 140f,
            useCenter = false,
            topLeft = Offset(cx - w * 0.48f, dotY - h * 0.78f),
            size = Size(w * 0.96f, h * 0.78f),
            style = stroke,
        )
        drawArc(
            tint,
            startAngle = 200f,
            sweepAngle = 140f,
            useCenter = false,
            topLeft = Offset(cx - w * 0.32f, dotY - h * 0.52f),
            size = Size(w * 0.64f, h * 0.52f),
            style = stroke,
        )
        drawArc(
            tint,
            startAngle = 200f,
            sweepAngle = 140f,
            useCenter = false,
            topLeft = Offset(cx - w * 0.16f, dotY - h * 0.26f),
            size = Size(w * 0.32f, h * 0.26f),
            style = stroke,
        )
        drawCircle(tint, radius = 1.5.dp.toPx(), center = Offset(cx, dotY))
    }
}
