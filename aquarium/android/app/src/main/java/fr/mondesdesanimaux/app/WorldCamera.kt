package fr.mondesdesanimaux.app

import kotlin.math.max

/** Camera in the original Python world's coordinates (1200 x screens, 1500). */
class WorldCamera {
    var worldWidth = 2400f
    var x = 0f
    var y = 350f
    var zoom = 1f
    var viewportWidth = 1200f
    var viewportHeight = 700f
    val scale: Float get() = max(viewportWidth / 1200f, viewportHeight / 900f) * zoom
    val visibleWidth: Float get() = viewportWidth / scale
    val visibleHeight: Float get() = viewportHeight / scale
    val offsetX: Float get() = max(0f, (viewportWidth - worldWidth * scale) / 2)
    val offsetY: Float get() = max(0f, (viewportHeight - WORLD_HEIGHT * scale) / 2)

    fun clamp() {
        zoom = if (zoom.isFinite()) zoom.coerceIn(.5f, 2f) else 1f
        x = if (x.isFinite()) x.coerceIn(0f, max(0f, worldWidth - visibleWidth)) else 0f
        y = if (y.isFinite()) y.coerceIn(0f, max(0f, WORLD_HEIGHT - visibleHeight)) else 350f
    }

    fun drag(dx: Float, dy: Float) {
        x -= dx / scale
        y -= dy / scale
        clamp()
    }

    fun zoomAt(factor: Float, focusX: Float, focusY: Float) {
        if (!factor.isFinite() || factor <= 0f) return
        val worldX = x + (focusX - offsetX) / scale
        val worldY = y + (focusY - offsetY) / scale
        zoom = (zoom * factor).coerceIn(.5f, 2f)
        x = worldX - (focusX - offsetX) / scale
        y = worldY - (focusY - offsetY) / scale
        clamp()
    }

    fun centerOn(worldY: Float) {
        y = worldY - visibleHeight / 2
        clamp()
    }

    companion object {
        const val WORLD_HEIGHT = 1500f
        const val LAND_Y = 800f
    }
}
