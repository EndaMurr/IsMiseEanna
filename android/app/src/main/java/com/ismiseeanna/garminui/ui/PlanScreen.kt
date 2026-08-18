package com.ismiseeanna.garminui.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RectangleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ismiseeanna.garminui.data.GarminApiFactory
import com.ismiseeanna.garminui.data.PlanProgressResponse
import com.ismiseeanna.garminui.data.SessionSummary
import com.ismiseeanna.garminui.data.Settings
import com.ismiseeanna.garminui.data.WeeklyCheckInResponse
import com.ismiseeanna.garminui.ui.theme.GarminAccent
import com.ismiseeanna.garminui.ui.theme.GarminDivider
import com.ismiseeanna.garminui.ui.theme.GarminNeutral700
import com.ismiseeanna.garminui.ui.theme.GarminText
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

@Composable
fun PlanScreen(settings: Settings) {
    val scope = rememberCoroutineScope()
    var baseUrl by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var raceDateInput by remember { mutableStateOf("") }
    var savedRaceDate by remember { mutableStateOf("") }

    var checkIn by remember { mutableStateOf<WeeklyCheckInResponse?>(null) }
    var checkInError by remember { mutableStateOf<String?>(null) }
    var progress by remember { mutableStateOf<PlanProgressResponse?>(null) }
    var progressError by remember { mutableStateOf<String?>(null) }

    suspend fun loadCheckIn() {
        try {
            checkIn = GarminApiFactory.create(baseUrl).getWeeklyCheckIn("Bearer $token")
            checkInError = null
        } catch (e: Exception) {
            checkInError = e.message ?: "Couldn't load this week's check-in."
        }
    }

    suspend fun loadProgress() {
        if (savedRaceDate.isBlank()) return
        try {
            progress = GarminApiFactory.create(baseUrl)
                .getPlanProgress("Bearer $token", savedRaceDate)
            progressError = null
        } catch (e: Exception) {
            progressError = e.message ?: "Couldn't load plan progress."
        }
    }

    // Check-in and progress load independently - a missing/invalid race date
    // shouldn't block the check-in section, which doesn't need one.
    LaunchedEffect(Unit) {
        baseUrl = settings.baseUrl.first()
        token = settings.apiToken.first()
        savedRaceDate = settings.raceDate.first()
        raceDateInput = savedRaceDate
        if (baseUrl.isBlank() || token.isBlank()) {
            checkInError = "Set the server address and token on the Status tab first."
            return@LaunchedEffect
        }
        loadCheckIn()
        loadProgress()
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        SectionHeader("THIS PLAN", topPadding = 16.dp)
        if (savedRaceDate.isBlank()) {
            Column(Modifier.padding(20.dp)) {
                Text(
                    "Set your race date to see which week of your plan you're in.",
                    color = GarminNeutral700,
                    fontSize = 13.sp,
                )
                OutlinedTextField(
                    value = raceDateInput,
                    onValueChange = { raceDateInput = it },
                    label = { Text("Race date (YYYY-MM-DD)") },
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    singleLine = true,
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = GarminDivider,
                        unfocusedBorderColor = GarminDivider,
                    ),
                )
                Button(
                    onClick = {
                        scope.launch {
                            settings.setRaceDate(raceDateInput.trim())
                            savedRaceDate = raceDateInput.trim()
                            loadProgress()
                        }
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = GarminAccent,
                        contentColor = Color.White,
                    ),
                    shape = RectangleShape,
                    modifier = Modifier.padding(top = 12.dp),
                ) {
                    Text("Save")
                }
            }
        } else {
            Column(Modifier.padding(20.dp)) {
                WeekProgressBar(
                    currentWeek = progress?.currentWeek,
                    totalWeeks = progress?.totalWeeks,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    progress?.daysUntilRace?.let { days ->
                        if (days >= 0) "$days days to race day" else "Race day has passed"
                    } ?: "—",
                    color = GarminText,
                    fontSize = 13.sp,
                    modifier = Modifier.padding(top = 8.dp),
                )
                if (progressError != null) {
                    Text(
                        progressError!!,
                        color = GarminAccent,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }
        }

        SectionHeader("THIS WEEK", topPadding = 8.dp)
        if (checkInError != null) {
            Text(
                checkInError!!,
                color = GarminAccent,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
            )
        } else if (checkIn == null) {
            Text(
                "Loading…",
                color = GarminNeutral700,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
            )
        } else {
            SessionSection("Missed", checkIn!!.sessionsMissed)
            SessionSection("Upcoming", checkIn!!.sessionsUpcoming)
            SessionSection("Completed", checkIn!!.sessionsCompleted)

            SectionHeader("RECOVERY TREND", topPadding = 16.dp)
            Column(Modifier.padding(20.dp)) {
                Text("Training readiness", color = GarminNeutral700, fontSize = 11.sp)
                Sparkline(
                    values = checkIn!!.recoveryTrend.trainingReadiness,
                    color = GarminAccent,
                    modifier = Modifier.fillMaxWidth().height(28.dp).padding(top = 6.dp, bottom = 16.dp),
                )
                Text("HRV", color = GarminNeutral700, fontSize = 11.sp)
                Sparkline(
                    values = checkIn!!.recoveryTrend.hrv,
                    color = GarminText,
                    modifier = Modifier.fillMaxWidth().height(28.dp).padding(top = 6.dp),
                )
            }
        }
    }
}

@Composable
private fun SectionHeader(label: String, topPadding: Dp) {
    Text(
        label,
        fontSize = 11.sp,
        letterSpacing = 1.sp,
        color = GarminNeutral700,
        modifier = Modifier.padding(start = 20.dp, top = topPadding, bottom = 4.dp),
    )
    Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
}

@Composable
private fun WeekProgressBar(currentWeek: Int?, totalWeeks: Int?, modifier: Modifier = Modifier) {
    if (currentWeek == null || totalWeeks == null || totalWeeks <= 0) {
        Text("Week — of —", color = GarminText, fontSize = 16.sp)
        return
    }
    Text("Week $currentWeek of $totalWeeks", color = GarminText, fontSize = 16.sp)
    Row(modifier.padding(top = 8.dp)) {
        for (week in 1..totalWeeks) {
            Box(
                Modifier
                    .weight(1f)
                    .height(8.dp)
                    .padding(horizontal = 1.dp)
                    .background(if (week <= currentWeek) GarminAccent else GarminDivider)
            )
        }
    }
}

@Composable
private fun SessionSection(label: String, sessions: List<SessionSummary>) {
    Column {
        Text(
            "$label (${sessions.size})",
            fontSize = 11.sp,
            letterSpacing = 0.5.sp,
            color = GarminNeutral700,
            modifier = Modifier.padding(start = 20.dp, top = 12.dp, bottom = 4.dp),
        )
        if (sessions.isEmpty()) {
            Text(
                "None",
                color = GarminNeutral700,
                fontSize = 13.sp,
                modifier = Modifier.padding(start = 20.dp, bottom = 4.dp),
            )
        } else {
            sessions.forEach { SessionRow(it) }
        }
    }
}

@Composable
private fun SessionRow(session: SessionSummary) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(session.name ?: "Untitled session", color = GarminText)
            Text(session.date ?: "—", color = GarminNeutral700)
        }
        Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
    }
}
