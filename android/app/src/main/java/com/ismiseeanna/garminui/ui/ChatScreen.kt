package com.ismiseeanna.garminui.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.RectangleShape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ismiseeanna.garminui.data.ChatMessage
import com.ismiseeanna.garminui.data.ChatRequest
import com.ismiseeanna.garminui.data.GarminApiFactory
import com.ismiseeanna.garminui.data.Settings
import com.ismiseeanna.garminui.ui.theme.GarminAccent
import com.ismiseeanna.garminui.ui.theme.GarminDivider
import com.ismiseeanna.garminui.ui.theme.GarminNeutral700
import com.ismiseeanna.garminui.ui.theme.GarminText
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private data class DisplayMessage(val who: String, val text: String, val isUser: Boolean)

@Composable
fun ChatScreen(settings: Settings) {
    val scope = rememberCoroutineScope()
    val messages = remember {
        mutableStateListOf(
            DisplayMessage(
                who = "Assistant",
                text = "Ask me about your activities, sleep, recovery, or schedule a workout.",
                isUser = false,
            )
        )
    }
    var input by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val listState = rememberLazyListState()

    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(vertical = 16.dp, horizontal = 20.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            items(messages) { message -> MessageBubble(message) }
            if (error != null) {
                item { Text(error!!, color = GarminAccent, fontSize = 12.sp) }
            }
        }
        Box(Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text("Message the assistant") },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = GarminDivider,
                    unfocusedBorderColor = GarminDivider,
                ),
                singleLine = true,
            )
            Button(
                onClick = {
                    val text = input.trim()
                    if (text.isBlank() || sending) return@Button
                    input = ""
                    messages.add(DisplayMessage(who = "You", text = text, isUser = true))
                    sending = true
                    error = null
                    scope.launch {
                        try {
                            val baseUrl = settings.baseUrl.first()
                            val token = settings.apiToken.first()
                            if (baseUrl.isBlank() || token.isBlank()) {
                                error = "Set the server address and token on the Status tab first."
                                return@launch
                            }
                            val history = messages.map {
                                ChatMessage(role = if (it.isUser) "user" else "assistant", content = it.text)
                            }
                            val response = GarminApiFactory.create(baseUrl)
                                .chat("Bearer $token", ChatRequest(history))
                            messages.add(DisplayMessage(who = "Assistant", text = response.reply, isUser = false))
                        } catch (e: Exception) {
                            error = e.message ?: "Couldn't reach the assistant."
                        } finally {
                            sending = false
                        }
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = GarminAccent, contentColor = Color.White),
                shape = RectangleShape,
                modifier = Modifier.padding(start = 8.dp),
            ) {
                Text(if (sending) "..." else "Send")
            }
        }
    }
}

@Composable
private fun MessageBubble(message: DisplayMessage) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (message.isUser) Alignment.End else Alignment.Start,
    ) {
        Text(
            message.who.uppercase(),
            fontSize = 10.sp,
            letterSpacing = 0.5.sp,
            color = GarminNeutral700,
            fontWeight = FontWeight.Medium,
        )
        Text(
            message.text,
            fontSize = 14.sp,
            color = GarminText,
            modifier = Modifier.padding(top = 4.dp),
        )
    }
}
