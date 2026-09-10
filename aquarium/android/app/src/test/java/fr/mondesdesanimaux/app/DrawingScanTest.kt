package fr.mondesdesanimaux.app

import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.RectF
import androidx.exifinterface.media.ExifInterface
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class DrawingScanTest {
    @Test fun brokenOutlineKeepsTheWhiteInteriorAtDifferentPhotoSizes() {
        for (scale in listOf(1, 4)) {
            val length = 120 * scale
            val pixels = IntArray(length * length) { Color.WHITE }
            for (y in 30 * scale until 90 * scale) for (x in 30 * scale until 90 * scale) {
                if (x < 33 * scale || x >= 87 * scale || y < 33 * scale || y >= 87 * scale) {
                    pixels[y * length + x] = Color.BLACK
                }
            }
            // A break wider than one pixel let the paper flood into the body.
            for (y in 55 * scale until 58 * scale) for (x in 29 * scale..34 * scale) pixels[y * length + x] = Color.WHITE
            val photo = Bitmap.createBitmap(pixels, length, length, Bitmap.Config.ARGB_8888)
            val result = DrawingScan.extract(photo, RectF(0f, 0f, 1f, 1f), 45)
            assertEquals("Interior at scale $scale", Color.WHITE, result.getPixel(result.width / 2, result.height / 2))
            assertEquals(0, Color.alpha(result.getPixel(0, 0)))
        }
    }

    @Test fun animalCutByTheTopOfTheCropDoesNotBecomeAnEmptyOutline() {
        val pixels = IntArray(120 * 120) { Color.WHITE }
        for (y in 0..89) for (x in 30..89) {
            if (x < 33 || x > 86 || y > 86) pixels[y * 120 + x] = Color.BLACK
        }
        val photo = Bitmap.createBitmap(pixels, 120, 120, Bitmap.Config.ARGB_8888)
        val result = DrawingScan.extract(photo, RectF(0f, 0f, 1f, 1f), 45)
        assertEquals(Color.WHITE, result.getPixel(result.width / 2, result.height / 2))
        assertEquals(Color.WHITE, result.getPixel(result.width / 2, 0))
        assertEquals(0, Color.alpha(result.getPixel(0, 0)))
    }

    @Test fun wideConcaveSpacesOutsideTheAnimalStayTransparent() {
        val pixels = IntArray(120 * 120) { Color.WHITE }
        for (y in 30..89) for (x in 30..89) {
            if (x < 40 || x >= 80 || y >= 80) pixels[y * 120 + x] = Color.BLACK
        }
        val photo = Bitmap.createBitmap(pixels, 120, 120, Bitmap.Config.ARGB_8888)
        val result = DrawingScan.extract(photo, RectF(0f, 0f, 1f, 1f), 45)
        assertEquals(0, Color.alpha(result.getPixel(result.width / 2, 10)))
        assertEquals(Color.BLACK, result.getPixel(result.width / 2, result.height - 5))
    }

    private fun drawing(paper: Int = Color.WHITE, ink: Int = Color.BLACK): Bitmap {
        val pixels = IntArray(120 * 120) { paper }
        for (y in 30..89) for (x in 30..89) {
            if (x < 33 || x > 86 || y < 33 || y > 86) pixels[y * 120 + x] = ink
        }
        pixels[8 * 120 + 8] = Color.BLACK // A speck, not part of the animal.
        return Bitmap.createBitmap(pixels, 120, 120, Bitmap.Config.ARGB_8888)
    }

    @Test fun removesPaperButKeepsWhiteInsideClosedDrawing() {
        val result = DrawingScan.extract(drawing(), RectF(0f, 0f, 1f, 1f), 45)
        assertEquals(64, result.width)
        assertEquals(64, result.height)
        assertEquals(0, Color.alpha(result.getPixel(0, 0)))
        assertEquals(Color.WHITE, result.getPixel(32, 32))
        assertEquals(Color.BLACK, result.getPixel(2, 2))
    }

    @Test fun paleColorIsNotMistakenForWhitePaper() {
        val pink = Color.rgb(248, 210, 225)
        val result = DrawingScan.extract(drawing(ink = pink), RectF(0f, 0f, 1f, 1f), 45)
        assertEquals(pink, result.getPixel(2, 2))
        assertEquals(255, Color.alpha(result.getPixel(32, 32)))
    }

    @Test fun grayPaperIsEstimatedFromBorder() {
        val gray = Color.rgb(180, 180, 180)
        val result = DrawingScan.extract(drawing(gray), RectF(0f, 0f, 1f, 1f), 45)
        assertEquals(0, Color.alpha(result.getPixel(0, 0)))
        assertEquals(gray, result.getPixel(32, 32))
    }

    @Test fun blankPaperReturnsAnActionableError() {
        val blank = Bitmap.createBitmap(120, 120, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.WHITE) }
        try { DrawingScan.extract(blank, RectF(0f, 0f, 1f, 1f), 45); fail("Blank paper is not an animal") }
        catch (e: IllegalArgumentException) { assertTrue(e.message.orEmpty().contains("Aucun dessin")) }
    }

    @Test fun tinyCropIsRejected() {
        try { DrawingScan.extract(drawing(), RectF(0f, 0f, .01f, .01f), 45); fail("Tiny crop") }
        catch (_: IllegalArgumentException) { }
    }

    @Test fun existingTransparentDrawingKeepsItsAlpha() {
        val png = drawing(Color.TRANSPARENT).copy(Bitmap.Config.ARGB_8888, true)
        // Fill inside the outline; transparent background should stay transparent.
        for (y in 33..86) for (x in 33..86) png.setPixel(x, y, Color.WHITE)
        val result = DrawingScan.extract(png, RectF(0f, 0f, 1f, 1f), 45)
        assertEquals(0, Color.alpha(result.getPixel(0, 0)))
        assertEquals(Color.WHITE, result.getPixel(32, 32))
    }

    @Test fun exifRotationAndReflectionHaveCorrectOrientation() {
        val expected = mapOf(
            ExifInterface.ORIENTATION_NORMAL to floatArrayOf(2f, 3f),
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL to floatArrayOf(-2f, 3f),
            ExifInterface.ORIENTATION_ROTATE_180 to floatArrayOf(-2f, -3f),
            ExifInterface.ORIENTATION_FLIP_VERTICAL to floatArrayOf(2f, -3f),
            ExifInterface.ORIENTATION_TRANSPOSE to floatArrayOf(3f, 2f),
            ExifInterface.ORIENTATION_ROTATE_90 to floatArrayOf(-3f, 2f),
            ExifInterface.ORIENTATION_TRANSVERSE to floatArrayOf(-3f, -2f),
            ExifInterface.ORIENTATION_ROTATE_270 to floatArrayOf(3f, -2f),
        )
        for ((exif, want) in expected) {
            val point = floatArrayOf(2f, 3f)
            DrawingScan.orientationMatrix(exif).mapPoints(point)
            assertArrayEquals(want, point, .001f)
        }
    }
}
