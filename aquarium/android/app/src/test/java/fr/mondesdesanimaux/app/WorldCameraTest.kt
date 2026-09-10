package fr.mondesdesanimaux.app

import org.junit.Assert.*
import org.junit.Test

class WorldCameraTest {
    @Test fun dragUsesWorldCoordinatesAndStopsAtEdges() {
        val camera = WorldCamera().apply { x = 200f; y = 300f }
        camera.drag(100f, 50f)
        assertEquals(100f, camera.x, .001f)
        assertEquals(250f, camera.y, .001f)
        camera.drag(10000f, -10000f)
        assertEquals(0f, camera.x, .001f)
        assertEquals(800f, camera.y, .001f)
    }

    @Test fun pinchKeepsThePointUnderTheFingers() {
        val camera = WorldCamera().apply { x = 300f; y = 200f }
        val beforeX = camera.x + 500 / camera.scale
        val beforeY = camera.y + 300 / camera.scale
        camera.zoomAt(1.5f, 500f, 300f)
        assertEquals(beforeX, camera.x + 500 / camera.scale, .001f)
        assertEquals(beforeY, camera.y + 300 / camera.scale, .001f)
    }

    @Test fun portraitAndLandscapeRemainInsideTheWorld() {
        val camera = WorldCamera()
        for ((w, h) in listOf(400f to 800f, 1200f to 600f, 1800f to 1200f)) {
            camera.viewportWidth = w; camera.viewportHeight = h
            camera.x = 10000f; camera.y = 10000f
            camera.clamp()
            assertTrue(camera.x >= 0 && camera.y >= 0)
            assertTrue(camera.x + camera.visibleWidth <= camera.worldWidth + .01f)
            assertTrue(camera.y + camera.visibleHeight <= 1500.01f)
        }
    }

    @Test fun smallWorldIsCenteredAtMinimumZoom() {
        val camera = WorldCamera().apply { worldWidth = 1200f; zoom = .5f }
        camera.clamp()
        assertEquals(0f, camera.x, .001f)
        assertEquals(300f, camera.offsetX, .001f)
    }

    @Test fun invalidAndExtremeZoomCannotBreakTheCamera() {
        val camera = WorldCamera()
        camera.zoomAt(Float.NaN, 50f, 50f)
        assertEquals(1f, camera.zoom, .001f)
        camera.zoomAt(100f, 50f, 50f)
        assertEquals(2f, camera.zoom, .001f)
        camera.zoomAt(.001f, 50f, 50f)
        assertEquals(.5f, camera.zoom, .001f)
        camera.x = Float.NaN; camera.y = Float.POSITIVE_INFINITY
        camera.clamp()
        assertTrue(camera.x.isFinite() && camera.y.isFinite())
    }

    @Test fun habitatNavigationReachesBothHabitats() {
        val camera = WorldCamera()
        camera.centerOn(350f)
        assertEquals(0f, camera.y, .001f)
        camera.centerOn(1200f)
        assertEquals(800f, camera.y, .001f)
    }
}
