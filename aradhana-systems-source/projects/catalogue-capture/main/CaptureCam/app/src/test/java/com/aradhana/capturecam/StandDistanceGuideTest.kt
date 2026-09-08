package com.aradhana.capturecam

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class StandDistanceGuideTest {
    @Test
    fun smallItemAtMaxZoomAsksForCloserStand() {
        val result = StandDistanceGuide.calculate(0.20f, 0.20f, 3.125f, 3.125f)!!
        assertEquals(StandDistanceGuide.Direction.CLOSER, StandDistanceGuide.direction(result.rawDistanceRatio))
        assertTrue(result.rawDistanceRatio < 0.30f)
    }

    @Test
    fun currentWideViewAccountsForRemainingOpticalZoom() {
        val result = StandDistanceGuide.calculate(0.30f, 0.30f, 1.0f, 3.0f)!!
        assertEquals(StandDistanceGuide.Direction.FARTHER, StandDistanceGuide.direction(result.rawDistanceRatio))
        assertTrue(result.projectedAreaAtMaxZoom > result.targetArea)
    }

    @Test
    fun targetSizedItemAtMaxZoomIsReady() {
        val side = kotlin.math.sqrt(StandDistanceGuide.DESIRED_FRAME_AREA)
        val result = StandDistanceGuide.calculate(side, side, 3.125f, 3.125f)!!
        assertEquals(StandDistanceGuide.Direction.READY, StandDistanceGuide.direction(result.rawDistanceRatio))
    }

    @Test
    fun elongatedPoseUsesSafeNonClippingTarget() {
        val result = StandDistanceGuide.calculate(0.50f, 0.10f, 3.125f, 3.125f)!!
        assertTrue(result.targetWidth <= 0.92f)
        assertTrue(result.targetHeight <= 0.92f)
        assertTrue(result.targetArea < StandDistanceGuide.DESIRED_FRAME_AREA)
    }

    @Test
    fun invalidDetectorBoxReturnsNull() {
        assertEquals(null, StandDistanceGuide.calculate(0f, 0.2f, 1f, 3.125f))
        assertEquals(null, StandDistanceGuide.calculate(0.2f, 0.2f, 0f, 3.125f))
        assertNotNull(StandDistanceGuide.calculate(0.2f, 0.2f, 1f, 3.125f))
    }

    @Test
    fun categoryAspectOverridesNoisyDetectedAspect() {
        val result = StandDistanceGuide.calculate(
            widthFraction = 0.4f,
            heightFraction = 0.1f,
            currentZoom = 3.125f,
            maxZoom = 3.125f,
            desiredArea = 0.05f,
            targetAspect = 2f / 3f
        )!!
        assertEquals(2f / 3f, result.targetWidth / result.targetHeight, 0.01f)
    }
}
