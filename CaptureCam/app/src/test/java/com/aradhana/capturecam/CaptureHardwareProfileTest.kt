package com.aradhana.capturecam

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CaptureHardwareProfileTest {
    @Test
    fun manufacturerTeleLimitProducesCorrectSubjectField() {
        assertEquals(108.37f, CaptureHardwareProfile.TELE_CLOSEST_FIELD_WIDTH_MM, 0.05f)
        assertEquals(72.09f, CaptureHardwareProfile.TELE_CLOSEST_FIELD_HEIGHT_MM, 0.05f)
    }

    @Test
    fun universalSeventyPercentRingCompositionIsPhysicallyImpossible() {
        val plan = CaptureHardwareProfile.telePlan(20f, 20f, 0.68f, 0.68f)!!
        assertFalse(plan.requestedCompositionAchievable)
        assertEquals(CaptureHardwareProfile.TELE_MAX_MAGNIFICATION, plan.appliedMagnification, 0.0001f)
        assertTrue(plan.projectedWidthPixels > 1_000)
    }

    @Test
    fun allExactStockCategoriesHaveProfiles() {
        assertEquals(57, CaptureCompositionProfiles.BY_CATEGORY.size)
    }

    @Test
    fun squarePhysicalGuideIsSquareWhenRenderedInThreeByTwoFrame() {
        val profile = CaptureCompositionProfiles.forCategory("ladies_ring_22")!!
        val (widthFraction, heightFraction) = profile.targetFrame()
        val renderedAspect = widthFraction * CaptureHardwareProfile.STILL_WIDTH_PX /
            (heightFraction * CaptureHardwareProfile.STILL_HEIGHT_PX)
        assertEquals(1f, renderedAspect, 0.01f)
    }

    @Test
    fun detectorRegionIsCenteredAndPaddedWithinFrame() {
        val region = CaptureCompositionProfiles.forCategory("bali_22")!!.detectorRegion()
        assertEquals(0.5f, (region.x0 + region.x1) / 2f, 0.0001f)
        assertEquals(0.5f, (region.y0 + region.y1) / 2f, 0.0001f)
        assertTrue(region.x0 >= 0f && region.y0 >= 0f)
        assertTrue(region.x1 <= 1f && region.y1 <= 1f)
    }
}
