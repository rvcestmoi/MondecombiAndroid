package fr.mondesdesanimaux.app

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.os.SystemClock
import android.provider.MediaStore
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import androidx.lifecycle.Lifecycle
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.util.UUID

/** Exercises the real screen and storage on a device using a simulated camera
 * result. Does not activate the camera sensor or read the user's photo library. */
@RunWith(AndroidJUnit4::class)
class ScanFlowTest {
    @Test fun cameraResultCropRotateAndAdditionSurviveRecreationAndReopen() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        instrumentation.uiAutomation.executeShellCommand("input keyevent KEYCODE_WAKEUP").use {
            java.io.FileInputStream(it.fileDescriptor).readBytes()
        }
        val context = instrumentation.targetContext
        val id = "test-scan-${UUID.randomUUID()}.zip"
        val file = File(context.filesDir, "worlds/$id").apply { parentFile!!.mkdirs() }
        file.outputStream().use { WorldArchive.createEmpty(it, "Test du scan") }
        val monitor = object : Instrumentation.ActivityMonitor() {
            override fun onStartActivity(intent: Intent): Instrumentation.ActivityResult? {
                if (intent.action != MediaStore.ACTION_IMAGE_CAPTURE) return null
                @Suppress("DEPRECATION")
                val uri = intent.getParcelableExtra<Uri>(MediaStore.EXTRA_OUTPUT)!!
                val bitmap = fixture()
                context.contentResolver.openOutputStream(uri)!!.use { bitmap.compress(Bitmap.CompressFormat.JPEG, 95, it) }
                bitmap.recycle()
                return Instrumentation.ActivityResult(Activity.RESULT_OK, Intent())
            }
        }
        instrumentation.addMonitor(monitor)
        try {
            ActivityScenario.launch<ScanActivity>(Intent(context, ScanActivity::class.java)
                .putExtra("worldId", id).putExtra("worldX", 600f)).use { scenario ->
                scenario.onActivity { it.window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON) }
                click(scenario, "Prendre une photo")
                waitEnabled(scenario, "Détourer le dessin")
                scenario.recreate()
                waitEnabled(scenario, "Détourer le dessin")
                click(scenario, "Tourner ↻")
                waitEnabled(scenario, "Détourer le dessin")
                click(scenario, "Détourer le dessin")
                waitEnabled(scenario, "Ajouter au monde")
                scenario.recreate()
                waitEnabled(scenario, "Ajouter au monde")
                click(scenario, "Ajouter au monde")
                val deadline = SystemClock.uptimeMillis() + 15000
                while (scenario.state != Lifecycle.State.DESTROYED && SystemClock.uptimeMillis() < deadline) SystemClock.sleep(50)
                assertEquals(Lifecycle.State.DESTROYED, scenario.state)
            }
            val reopened = WorldRepository.open(context, id).use { WorldArchive.read(it) }
            assertEquals(1, reopened.animals.size)
            assertEquals("poisson", reopened.animals.single().kind)
            val drawing = reopened.animals.single().image
            assertEquals(0, Color.alpha(drawing.getPixel(0, 0)))
            assertEquals(255, Color.alpha(drawing.getPixel(drawing.width / 2, drawing.height / 2)))
            reopened.animals.forEach { it.image.recycle() }
        } finally {
            instrumentation.removeMonitor(monitor)
            file.delete()
        }
    }

    private fun fixture(): Bitmap {
        val pixels = IntArray(200 * 160) { Color.WHITE }
        for (y in 35..124) for (x in 40..159) {
            pixels[y * 200 + x] = if (x < 46 || x > 153 || y < 41 || y > 118) Color.BLACK else Color.rgb(240, 120, 100)
        }
        for (y in 70..82) for (x in 58..70) pixels[y * 200 + x] = Color.WHITE
        return Bitmap.createBitmap(pixels, 200, 160, Bitmap.Config.ARGB_8888)
    }

    private fun find(view: View, text: String): Button? {
        if (view is Button && view.text.toString() == text) return view
        if (view is ViewGroup) for (i in 0 until view.childCount) find(view.getChildAt(i), text)?.let { return it }
        return null
    }

    private fun click(scenario: ActivityScenario<ScanActivity>, text: String) {
        scenario.onActivity {
            val button = requireNotNull(find(it.window.decorView, text))
            assertTrue("Button should be enabled: $text", button.isEnabled)
            assertEquals(View.VISIBLE, button.visibility)
            button.performClick()
        }
    }

    private fun waitEnabled(scenario: ActivityScenario<ScanActivity>, text: String) {
        val deadline = SystemClock.uptimeMillis() + 15000
        var ready = false
        while (!ready && SystemClock.uptimeMillis() < deadline) {
            scenario.onActivity { activity ->
                ready = find(activity.window.decorView, text)?.let { it.isEnabled && it.isShown } ?: false
            }
            if (!ready) SystemClock.sleep(50)
        }
        assertTrue("Timed out waiting for $text", ready)
    }
}
