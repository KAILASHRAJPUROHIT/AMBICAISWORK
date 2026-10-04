package com.mdmesh.core.indoor

import com.mdmesh.proto.IndoorBundleDto
import com.mdmesh.proto.IndoorPlanDto
import com.mdmesh.proto.IndoorZoneDto
import com.mdmesh.proto.ProtocolJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class IndoorGeometryTest {

    private val plan = IndoorPlanDto(
        widthM = 20.0, heightM = 10.0, northDeg = 0.0,
        walls = listOf(listOf(10.0, 0.0, 10.0, 7.0), listOf(1.0, 2.0)), // second wall is malformed and ignored
        zones = listOf(
            IndoorZoneDto("Showroom", 0.0, 0.0, 20.0, 10.0),
            IndoorZoneDto("Counter 2", 4.0, 4.0, 3.0, 2.0),
        ),
    )

    @Test fun `the smallest zone containing a point wins`() {
        assertEquals("Counter 2", IndoorGeometry.zoneAt(plan, 5.0, 5.0))
        assertEquals("Showroom", IndoorGeometry.zoneAt(plan, 15.0, 5.0))
        assertNull(IndoorGeometry.zoneAt(plan, 25.0, 5.0))
    }

    @Test fun `walls become obstacles and malformed walls are skipped`() {
        val fp = IndoorGeometry.floorPlan(plan)
        assertEquals(1, fp.walls.size)
        assertFalse(fp.canMove(Pt(9.0, 3.0), Pt(11.0, 3.0)))
        assertTrue(fp.canMove(Pt(9.0, 8.0), Pt(11.0, 8.0)))
    }

    @Test fun `compass bearings map onto plan headings`() {
        // Plan up is north: walking north is heading +90 degrees (up), east is 0, south is -90, west is 180.
        assertEquals(Math.PI / 2, IndoorGeometry.planHeadingRad(0.0, 0.0), 1e-9)
        assertEquals(0.0, IndoorGeometry.planHeadingRad(90.0, 0.0), 1e-9)
        assertEquals(-Math.PI / 2, IndoorGeometry.planHeadingRad(180.0, 0.0), 1e-9)
        // Plan drawn with its top pointing east (north offset 90): walking east is "up" on the plan.
        assertEquals(Math.PI / 2, IndoorGeometry.planHeadingRad(90.0, 90.0), 1e-9)
    }

    @Test fun `the server response shape decodes, ignoring unknown fields`() {
        val json = """
            {"updatedAt":1760000000000,
             "plan":{"widthM":20.0,"heightM":10.0,"northDeg":15.0,"walls":[[10,0,10,7]],
                     "zones":[{"name":"Vault","x":1,"y":1,"w":2,"h":2}],"futureField":true},
             "points":[{"x":1.5,"y":2.5,"rssi":{"aa:bb:cc:dd:ee:01":-55,"aa:bb:cc:dd:ee:02":-71},"mag":48.2}]}
        """.trimIndent()
        val b = ProtocolJson.json.decodeFromString(IndoorBundleDto.serializer(), json)
        assertEquals(20.0, b.plan.widthM, 0.0)
        assertEquals("Vault", b.plan.zones.single().name)
        assertEquals(-55, b.points.single().rssi["aa:bb:cc:dd:ee:01"])
        val map = IndoorGeometry.fingerprintMap(b)
        assertEquals(48.2, map.expectedMagAt(Pt(1.5, 2.5))!!, 1e-9)
    }

    @Test fun `phone hotspots and random addresses are recognised`() {
        assertTrue(WifiScanner.isLocallyAdministered("46:80:eb:96:f5:ea"))
        assertFalse(WifiScanner.isLocallyAdministered("7c:f1:7e:2e:fa:a2"))
        assertNull(WifiScanner.normalise("not-a-mac"))
        assertEquals("7c:f1:7e:2e:fa:a2", WifiScanner.normalise("7C:F1:7E:2E:FA:A2"))
    }

    @Test fun `scans are averaged per network over the scans that heard it`() {
        val avg = WifiScanner.average(
            listOf(mapOf("a" to -50, "b" to -70), mapOf("a" to -60), mapOf("a" to -55, "b" to -74)),
        )
        assertEquals(-55, avg["a"])
        assertEquals(-72, avg["b"])
    }

    @Test fun `a matching magnetic reading raises the likelihood and a very different one lowers it`() {
        val map = FingerprintMap(listOf(Fingerprint(Pt(2.0, 2.0), mapOf("x" to -60), mag = 50.0)))
        val scan = mapOf("x" to -60)
        val near = map.likelihood(Pt(2.0, 2.0), scan, mag = 50.0)
        val far = map.likelihood(Pt(2.0, 2.0), scan, mag = 90.0)
        assertTrue("near=$near far=$far", near > far)
    }
}
