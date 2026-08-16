package com.ismiseeanna.garminui.data

import com.squareup.moshi.JsonClass
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

@JsonClass(generateAdapter = true)
data class DashboardToday(
    val bodyBattery: Double?,
    val trainingReadiness: Double?,
    val sleepScore: Double?,
    val restingHeartRate: Double?,
    val hrv: Double?,
)

@JsonClass(generateAdapter = true)
data class DashboardTrends(
    val bodyBattery: List<Double?>,
    val trainingReadiness: List<Double?>,
    val sleepScore: List<Double?>,
    val restingHeartRate: List<Double?>,
    val hrv: List<Double?>,
)

@JsonClass(generateAdapter = true)
data class DashboardResponse(
    val today: DashboardToday,
    val trends: DashboardTrends,
)

@JsonClass(generateAdapter = true)
data class StatusResponse(
    val connected: Boolean,
    val server: String,
    val account: String?,
    val runningVia: String,
)

@JsonClass(generateAdapter = true)
data class ChatMessage(
    val role: String,
    val content: String,
)

@JsonClass(generateAdapter = true)
data class ChatRequest(
    val messages: List<ChatMessage>,
)

@JsonClass(generateAdapter = true)
data class ChatResponse(
    val reply: String,
)

interface GarminApi {
    @GET("status")
    suspend fun getStatus(@Header("Authorization") auth: String): StatusResponse

    @GET("dashboard")
    suspend fun getDashboard(@Header("Authorization") auth: String): DashboardResponse

    @POST("chat")
    suspend fun chat(@Header("Authorization") auth: String, @Body request: ChatRequest): ChatResponse
}

object GarminApiFactory {
    fun create(baseUrl: String): GarminApi {
        val client = OkHttpClient.Builder().build()
        val moshi = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
        return Retrofit.Builder()
            .baseUrl(if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/")
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(GarminApi::class.java)
    }
}
