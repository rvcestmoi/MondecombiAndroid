package fr.mondesdesanimaux.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Looper
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import java.io.File
import java.util.UUID

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class ScanModelTest {
    @Test fun returningCameraPhotoWinsOverAnOlderDraftAfterProcessRecreation() = returningPhoto(true)
    @Test fun returningImportedPhotoWinsOverAnOlderDraftAfterProcessRecreation() = returningPhoto(false)

    private fun returningPhoto(camera: Boolean) {
        val context = RuntimeEnvironment.getApplication()
        val session = UUID.randomUUID().toString()
        val directory = File(context.filesDir, "scan/$session").apply { mkdirs() }
        val previous = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
        File(directory, "source.png").outputStream().use { previous.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val incoming = Bitmap.createBitmap(60, 80, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.RED) }
        val photo = File(directory, "camera.jpg")
        photo.outputStream().use { incoming.compress(Bitmap.CompressFormat.PNG, 100, it) }
        val state = Bundle().apply {
            putString("session", session)
            putBoolean(if (camera) "waitingCamera" else "waitingPhoto", true)
        }
        val model = ScanModel(context, "example.zip", state)
        try {
            model.restore()
            assertFalse("Old draft must not occupy the loader while a result is pending", model.busy)
            assertNull(model.source)
            if (camera) model.takePhotoResult() else {
                model.waitingPhoto = false
                model.importPhoto(Uri.fromFile(photo))
            }
            val deadline = System.nanoTime() + 10_000_000_000L
            while (model.busy && System.nanoTime() < deadline) {
                shadowOf(Looper.getMainLooper()).idle()
                Thread.sleep(10)
            }
            assertFalse(model.busy)
            assertNull(model.error)
            assertEquals(60, model.source!!.width)
            assertEquals(80, model.source!!.height)
            assertEquals(Color.RED, model.source!!.getPixel(20, 20))
        } finally { model.close() }
    }
}
