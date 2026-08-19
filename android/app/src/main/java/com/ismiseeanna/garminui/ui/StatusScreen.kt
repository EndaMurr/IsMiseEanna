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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ismiseeanna.garminui.data.GarminApiFactory
import com.ismiseeanna.garminui.data.Settings
import com.ismiseeanna.garminui.data.StatusResponse
import com.ismiseeanna.garminui.ui.theme.GarminAccent
import com.ismiseeanna.garminui.ui.theme.GarminDivider
import com.ismiseeanna.garminui.ui.theme.GarminNeutral700
import com.ismiseeanna.garminui.ui.theme.GarminText
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

@Composable
fun StatusScreen(settings: Settings) {
    val scope = rememberCoroutineScope()
    var baseUrl by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var status by remember { mutableStateOf<StatusResponse?>(null) }
    var statusError by remember { mutableStateOf<String?>(null) }

    suspend fun refreshStatus() {
        if (baseUrl.isBlank() || token.isBlank()) return
        try {
            status = GarminApiFactory.create(baseUrl).getStatus("Bearer $token")
            statusError = null
        } catch (e: Exception) {
            statusError = e.message ?: "Couldn't reach the server."
        }
    }

    // Loads the saved settings once and checks status; typing in the fields
    // below only updates local state until Save is pressed, so this doesn't
    // re-fire on every keystroke.
    LaunchedEffect(Unit) {
        baseUrl = settings.baseUrl.first()
        token = settings.apiToken.first()
        refreshStatus()
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Text(
            "SERVER",
            fontSize = 11.sp,
            letterSpacing = 1.sp,
            color = GarminNeutral700,
            modifier = Modifier.padding(start = 20.dp, top = 16.dp, bottom = 4.dp),
        )
        Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))

        StatusRow("Connection") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier.size(8.dp).background(
                        if (status?.connected == true) GarminAccent else GarminNeutral700
                    )
                )
                Text(
                    if (status?.connected == true) "Connected" else "Disconnected",
                    modifier = Modifier.padding(start = 8.dp),
                    color = GarminText,
                )
            }
        }
        StatusRow("Server") { Text(status?.server ?: "—", color = GarminNeutral700) }
        StatusRow("Account") { Text(status?.account ?: "—", color = GarminNeutral700) }
        StatusRow("Running via") { Text(status?.runningVia ?: "—", color = GarminNeutral700) }

        if (statusError != null) {
            Text(
                statusError!!,
                color = GarminAccent,
                fontSize = 12.sp,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
            )
        }

        Text(
            "BACKEND SETTINGS",
            fontSize = 11.sp,
            letterSpacing = 1.sp,
            color = GarminNeutral700,
            modifier = Modifier.padding(start = 20.dp, top = 24.dp, bottom = 4.dp),
        )
        Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))

        Column(Modifier.padding(20.dp)) {
            OutlinedTextField(
                value = baseUrl,
                onValueChange = { baseUrl = it },
                label = { Text("Server address (e.g. http://192.168.1.20:8000)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = GarminDivider,
                    unfocusedBorderColor = GarminDivider,
                ),
            )
            OutlinedTextField(
                value = token,
                onValueChange = { token = it },
                label = { Text("API token") },
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
                        settings.setBaseUrl(baseUrl.trim())
                        settings.setApiToken(token.trim())
                        refreshStatus()
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = GarminAccent, contentColor = Color.White),
                shape = RectangleShape,
                modifier = Modifier.padding(top = 16.dp),
            ) {
                Text("Save")
            }
        }
    }
}

@Composable
private fun StatusRow(label: String, value: @Composable () -> Unit) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(label, color = GarminText)
            value()
        }
        Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
    }
}
