package com.ismiseeanna.garminui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.ismiseeanna.garminui.ui.MainScreen
import com.ismiseeanna.garminui.ui.theme.GarminBackground
import com.ismiseeanna.garminui.ui.theme.GarminUiTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            GarminUiTheme {
                Surface(modifier = Modifier.fillMaxSize(), color = GarminBackground) {
                    MainScreen()
                }
            }
        }
    }
}
