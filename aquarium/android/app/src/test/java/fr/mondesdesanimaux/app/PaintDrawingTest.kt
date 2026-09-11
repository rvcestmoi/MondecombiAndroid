package fr.mondesdesanimaux.app

import android.graphics.Color
import android.graphics.PointF
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28, 36])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class PaintDrawingTest {
    private fun stroke(color: Int, width: Float, erase: Boolean, vararg points: PointF) =
        PaintDrawing.Stroke(color, width, erase, points.toMutableList())

    @Test fun transparentExportPreservesSeparatePartsAndWhitePaint() {
        val drawing = PaintDrawing()
        drawing.strokes += stroke(Color.RED, 40f, false, PointF(100f, 100f), PointF(200f, 100f))
        drawing.strokes += stroke(Color.WHITE, 20f, false, PointF(300f, 100f))
        val image = drawing.export()
        val colors = IntArray(image.width * image.height)
        image.getPixels(colors, 0, image.width, 0, 0, image.width, image.height)
        assertTrue(colors.any { it == Color.RED })
        assertTrue(colors.any { it == Color.WHITE })
        assertTrue(colors.any { Color.alpha(it) == 0 })
        assertTrue(image.width < 1024 && image.height < 1024)
        image.recycle()
    }

    @Test fun eraserRemovesInkAndUndoRestoresItAfterDraftReload() {
        val drawing = PaintDrawing()
        drawing.strokes += stroke(Color.BLUE, 60f, false, PointF(100f, 100f), PointF(300f, 100f))
        drawing.strokes += stroke(Color.BLACK, 30f, true, PointF(200f, 70f), PointF(200f, 130f))
        val restored = PaintDrawing.restore(drawing.serialize())
        val erased = restored.export()
        assertEquals(0, Color.alpha(erased.getPixel(erased.width / 2, erased.height / 2)))
        restored.strokes.removeAt(restored.strokes.lastIndex)
        val undone = restored.export()
        assertEquals(Color.BLUE, undone.getPixel(undone.width / 2, undone.height / 2))
        erased.recycle(); undone.recycle()
    }

    @Test fun emptyOrFullyErasedDrawingCannotBeAdded() {
        val drawing = PaintDrawing()
        for (erase in listOf(false, true)) {
            if (erase) {
                drawing.strokes += stroke(Color.RED, 10f, false, PointF(100f, 100f))
                drawing.strokes += stroke(Color.BLACK, 40f, true, PointF(100f, 100f))
            }
            try { drawing.export(); fail("Empty drawing must be rejected") }
            catch (_: IllegalStateException) { }
        }
    }
}
