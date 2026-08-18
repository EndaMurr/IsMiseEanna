package com.ismiseeanna.garminui.ui

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

@Composable
fun Sparkline(values: List<Double?>, color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) {
        val indexed = values.mapIndexedNotNull { i, v -> v?.let { i to it } }
        if (indexed.size < 2) return@Canvas
        val minV = indexed.minOf { it.second }
        val maxV = indexed.maxOf { it.second }
        val range = (maxV - minV).let { if (it == 0.0) 1.0 else it }
        val lastIndex = (values.size - 1).coerceAtLeast(1)
        val path = Path()
        indexed.forEachIndexed { pointIdx, (i, v) ->
            val x = (i.toFloat() / lastIndex) * size.width
            val y = size.height - ((v - minV) / range).toFloat() * size.height
            if (pointIdx == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, color, style = Stroke(width = 2.dp.toPx()))
    }
}
