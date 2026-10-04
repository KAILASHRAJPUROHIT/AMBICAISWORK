package com.mdmesh.proto

import kotlinx.serialization.Serializable

/** A named rectangular area of the store (counter, vault, billing...), in plan metres. */
@Serializable
data class IndoorZoneDto(
    val name: String,
    val x: Double,
    val y: Double,
    val w: Double,
    val h: Double,
)

/**
 * The store's floor plan. [northDeg] is the compass bearing of the plan's "up" (+y) direction, so a plan drawn with
 * its top pointing north-east has northDeg = 45. Each wall is `[x1, y1, x2, y2]` in metres.
 */
@Serializable
data class IndoorPlanDto(
    val widthM: Double,
    val heightM: Double,
    val northDeg: Double = 0.0,
    val walls: List<List<Double>> = emptyList(),
    val zones: List<IndoorZoneDto> = emptyList(),
)

/** One surveyed point: plan position plus the Wi-Fi readings (BSSID -> dBm) heard there. */
@Serializable
data class IndoorPointDto(
    val x: Double,
    val y: Double,
    val rssi: Map<String, Int>,
    val mag: Double? = null,
)

/** Everything the device needs to position itself: the plan and every surveyed point. */
@Serializable
data class IndoorBundleDto(
    val updatedAt: Long = 0,
    val plan: IndoorPlanDto,
    val points: List<IndoorPointDto> = emptyList(),
)

/** A survey reading sent to the server. */
@Serializable
data class IndoorSurveyRequest(
    val deviceId: String,
    val x: Double,
    val y: Double,
    val rssi: Map<String, Int>,
    val mag: Double? = null,
)

/** The device's own indoor position estimate, reported in telemetry. [spreadM] is how unsure it is, in metres. */
@Serializable
data class IndoorFixDto(
    val x: Double,
    val y: Double,
    val spreadM: Double,
    val zone: String? = null,
    val at: Long,
)
