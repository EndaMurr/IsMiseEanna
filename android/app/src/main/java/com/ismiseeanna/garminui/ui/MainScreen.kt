package com.ismiseeanna.garminui.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.weight
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ismiseeanna.garminui.data.Settings
import com.ismiseeanna.garminui.ui.theme.GarminAccent
import com.ismiseeanna.garminui.ui.theme.GarminAccent700
import com.ismiseeanna.garminui.ui.theme.GarminBackground
import com.ismiseeanna.garminui.ui.theme.GarminDivider
import com.ismiseeanna.garminui.ui.theme.GarminNeutral700
import com.ismiseeanna.garminui.ui.theme.GarminText
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

enum class Tab { DASHBOARD, CHAT, STATUS }

@Composable
fun MainScreen() {
    var tab by remember { mutableStateOf(Tab.DASHBOARD) }
    val context = LocalContext.current
    val settings = remember { Settings(context) }

    Column(modifier = Modifier.fillMaxSize().background(GarminBackground)) {
        TopBar()
        Box(modifier = Modifier.weight(1f)) {
            when (tab) {
                Tab.DASHBOARD -> DashboardScreen(settings)
                Tab.CHAT -> ChatScreen(settings)
                Tab.STATUS -> StatusScreen(settings)
            }
        }
        BottomNav(current = tab, onSelect = { tab = it })
    }
}

@Composable
private fun TopBar() {
    val today = remember {
        LocalDate.now().format(DateTimeFormatter.ofPattern("EEEE, MMMM d", Locale.getDefault()))
    }
    Column {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 16.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Bottom,
        ) {
            Column {
                Text("Garmin UI", fontWeight = FontWeight.Bold, fontSize = 20.sp, color = GarminText)
                Text(today, fontSize = 12.sp, color = GarminNeutral700)
            }
            Box(modifier = Modifier.size(8.dp).background(GarminAccent))
        }
        Box(modifier = Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
    }
}

@Composable
private fun BottomNav(current: Tab, onSelect: (Tab) -> Unit) {
    Column {
        Box(modifier = Modifier.fillMaxWidth().height(2.dp).background(GarminDivider))
        Row(modifier = Modifier.fillMaxWidth()) {
            NavItem(
                label = "Dashboard",
                selected = current == Tab.DASHBOARD,
                icon = { tint -> DashboardIcon(tint) },
                onClick = { onSelect(Tab.DASHBOARD) },
            )
            NavItem(
                label = "Chat",
                selected = current == Tab.CHAT,
                icon = { tint -> ChatIcon(tint) },
                onClick = { onSelect(Tab.CHAT) },
            )
            NavItem(
                label = "Status",
                selected = current == Tab.STATUS,
                icon = { tint -> StatusIcon(tint) },
                onClick = { onSelect(Tab.STATUS) },
            )
        }
    }
}

@Composable
private fun RowScope.NavItem(
    label: String,
    selected: Boolean,
    icon: @Composable (Color) -> Unit,
    onClick: () -> Unit,
) {
    val tint = if (selected) GarminAccent700 else GarminNeutral700
    Column(
        modifier = Modifier
            .weight(1f)
            .clickable(
                interactionSource = remember { MutableInteractionSource() },
                indication = null,
                onClick = onClick,
            )
            .padding(top = 10.dp, bottom = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        icon(tint)
        Text(label, fontSize = 11.sp, color = tint)
    }
}
