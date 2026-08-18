package com.ismiseeanna.garminui.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.settingsStore by preferencesDataStore(name = "garmin_ui_settings")

private val BASE_URL_KEY = stringPreferencesKey("base_url")
private val API_TOKEN_KEY = stringPreferencesKey("api_token")
private val RACE_DATE_KEY = stringPreferencesKey("race_date")

/** Where to reach the ismiseeanna-mcp backend, and the shared bearer token to use. */
class Settings(context: Context) {
    // Use the application context, not the caller's (often an Activity) —
    // preferencesDataStore's delegate is keyed per Context instance, and an
    // Activity context gets replaced on recreation (e.g. rotation), which
    // would open the same file from two DataStore instances at once.
    private val context: Context = context.applicationContext

    val baseUrl: Flow<String> =
        context.settingsStore.data.map { it[BASE_URL_KEY] ?: "" }

    val apiToken: Flow<String> =
        context.settingsStore.data.map { it[API_TOKEN_KEY] ?: "" }

    val raceDate: Flow<String> =
        context.settingsStore.data.map { it[RACE_DATE_KEY] ?: "" }

    suspend fun setBaseUrl(value: String) {
        context.settingsStore.edit { it[BASE_URL_KEY] = value }
    }

    suspend fun setApiToken(value: String) {
        context.settingsStore.edit { it[API_TOKEN_KEY] = value }
    }

    suspend fun setRaceDate(value: String) {
        context.settingsStore.edit { it[RACE_DATE_KEY] = value }
    }
}
