package com.ismiseeanna.garminui.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.weight
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ismiseeanna.garminui.data.DashboardResponse
import com.ismiseeanna.garminui.data.GarminApiFactory
import com.ismiseeanna.garminui.data.Settings
import com.ismiseeanna.garminui.ui.theme.GarminAccent
import com.ismiseeanna.garminui.ui.theme.GarminDivider
import com.ismiseeanna.garminui.ui.theme.GarminNeutral700
import com.ismiseeanna.garminui.ui.theme.GarminText
import kotlinx.coroutines.flow.first

@Composable
fun DashboardScreen(settings: Settings) {
    var dashboard by remember { mutableStateOf<DashboardResponse?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        val baseUrl = settings.baseUrl.first()
        val token = settings.apiToken.first()
        if (baseUrl.isBlank() || token.isBlank()) {
            error = "Set the server address and token on the Status tab first."
            return@LaunchedEffect
        }
        try {
            dashboard = GarminApiFactory.create(baseUrl).getDashboard("Bearer $token")
        } catch (e: Exception) {
            error = e.message ?: "Couldn't load the dashboard."
        }
    }

    when {
        error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(error!!, color = GarminNeutral700, modifier = Modifier.padding(32.dp))
        }
        dashboard == null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator(color = GarminAccent)
        }
        else -> DashboardGrid(dashboard!!)
    }
}

@Composable
private fun DashboardGrid(dashboard: DashboardResponse) {
    Column(Modifier.fillMaxSize()) {
        Text(
            "THIS WEEK",
            fontSize = 11.sp,
            letterSpacing = 1.sp,
            color = GarminNeutral700,
            modifier = Modifier.padding(start = 20.dp, top = 16.dp, bottom = 4.dp),
        )
        Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
            StatCell(
                label = "BODY BATTERY",
                value = dashboard.today.bodyBattery,
                trend = dashboard.trends.bodyBattery,
                sparklineColor = GarminAccent,
                modifier = Modifier.weight(1f),
            )
            Box(Modifier.width(2.dp).fillMaxHeight().background(GarminDivider))
            StatCell(
                label = "TRAINING READINESS",
                value = dashboard.today.trainingReadiness,
                trend = dashboard.trends.trainingReadiness,
                sparklineColor = GarminText,
                modifier = Modifier.weight(1f),
            )
        }
        Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
        Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
            StatCell(
                label = "SLEEP SCORE",
                value = dashboard.today.sleepScore,
                trend = dashboard.trends.sleepScore,
                sparklineColor = GarminAccent,
                modifier = Modifier.weight(1f),
            )
            Box(Modifier.width(2.dp).fillMaxHeight().background(GarminDivider))
            StatCell(
                label = "RESTING HR / HRV",
                value = dashboard.today.restingHeartRate,
                unit = dashboard.today.hrv?.let { "bpm · ${it.toInt()}ms" },
                trend = dashboard.trends.restingHeartRate,
                sparklineColor = GarminText,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun StatCell(
    label: String,
    value: Double?,
    unit: String? = null,
    trend: List<Double?>,
    sparklineColor: Color,
    modifier: Modifier = Modifier,
) {
    Column(modifier.padding(16.dp)) {
        Text(label, fontSize = 11.sp, letterSpacing = 0.5.sp, color = GarminNeutral700)
        Row(verticalAlignment = Alignment.Bottom, modifier = Modifier.padding(top = 6.dp)) {
            Text(
                text = value?.let { it.toInt().toString() } ?: "—",
                fontSize = 34.sp,
                fontWeight = FontWeight.Bold,
                color = GarminText,
            )
            if (unit != null) {
                Text(unit, fontSize = 13.sp, color = GarminNeutral700, modifier = Modifier.padding(start = 8.dp))
            }
        }
        Sparkline(
            values = trend,
            color = sparklineColor,
            modifier = Modifier.fillMaxWidth().height(28.dp).padding(top = 10.dp),
        )
    }
}

@Composable
private fun Sparkline(values: List<Double?>, color: Color, modifier: Modifier = Modifier) {
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
