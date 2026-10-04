package com.mdmesh.core.net

import com.mdmesh.proto.AgentCheckInRequest
import com.mdmesh.proto.AgentCheckInResponse
import com.mdmesh.proto.AgentEnrollByCredentialsRequest
import com.mdmesh.proto.AgentEnrollRequest
import com.mdmesh.proto.AgentEnrollResponse
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Query
import com.mdmesh.proto.LeaderboardResponse
import com.mdmesh.proto.IndoorBundleDto
import com.mdmesh.proto.IndoorSurveyRequest

/**
 * Retrofit contract for the device <-> server agent v1 protocol.
 * Paths and shapes mirror `proto/endpoints.md`.
 *
 * Both calls return the server's `{status,message,data}` envelope. The sync loop is
 * the source of truth; push (MQTT/long-poll) is only an optimisation that triggers an
 * early check-in.
 */
interface MdmApi {

    /** Token-gated enrollment. Returns the server-issued opaque device id. */
    @POST("rest/public/agent/v1/enroll")
    suspend fun enroll(@Body request: AgentEnrollRequest): ResponseEnvelope<AgentEnrollResponse>

    /** "Lite" tier enrollment: email + master password instead of a pre-minted token. Same
     *  response shape as [enroll]. */
    @POST("rest/public/agent/v1/enrollByCredentials")
    suspend fun enrollByCredentials(
        @Body request: AgentEnrollByCredentialsRequest,
    ): ResponseEnvelope<AgentEnrollResponse>

    /**
     * Advertise capabilities + ack prior commands; receive the next gated batch.
     * [authorization] is `Bearer <deviceSecret>` (the per-device secret from enrollment).
     */
    @POST("rest/public/agent/v1/checkin")
    suspend fun checkIn(
        @Header("Authorization") authorization: String,
        @Body request: AgentCheckInRequest,
    ): ResponseEnvelope<AgentCheckInResponse>

    /** Latest shop sales leaderboard for this device's customer (`data` is null before the shop
     *  collector has ever pushed one). Same Bearer device-secret auth as [checkIn]. */
    @GET("rest/public/agent/v1/leaderboard")
    suspend fun leaderboard(
        @Header("Authorization") authorization: String,
        @Query("deviceId") deviceId: String,
    ): ResponseEnvelope<LeaderboardResponse>

    /** The store floor plan + Wi-Fi survey for this device's customer (`data` is null when no plan exists). */
    @GET("rest/public/agent/v1/indoor")
    suspend fun indoorBundle(
        @Header("Authorization") authorization: String,
        @Query("deviceId") deviceId: String,
    ): ResponseEnvelope<IndoorBundleDto>

    /** Uploads one surveyed point (plan position + Wi-Fi readings). */
    @POST("rest/public/agent/v1/indoor/survey")
    suspend fun indoorSurvey(
        @Header("Authorization") authorization: String,
        @Body request: IndoorSurveyRequest,
    ): ResponseEnvelope<Unit>
}
