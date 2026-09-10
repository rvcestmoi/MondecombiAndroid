package fr.mondesdesanimaux.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.graphics.RectF
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import java.io.File
import java.util.UUID
import java.util.concurrent.Executors

/** Retained across rotation, with disk-backed photos for process recreation. */
class ScanModel(private val context: Context, val worldId: String, state: Bundle?) {
    val sessionId = state?.getString("session")?.takeIf { it.matches(Regex("[a-f0-9-]{36}")) }
        ?: UUID.randomUUID().toString()
    private val folder = File(context.filesDir, "scan/$sessionId").apply { mkdirs() }
    val cameraFile = File(folder, "camera.jpg")
    private val sourceFile = File(folder, "source.png")
    private val cutoutFile = File(folder, "cutout.png")
    private val cutoutVersion = File(folder, "cutout.version")
    var source: Bitmap? = null
        private set
    var cutout: Bitmap? = null
        private set
    var crop = state?.getFloatArray("crop")?.let { RectF(it[0], it[1], it[2], it[3]) } ?: RectF(.04f, .04f, .96f, .96f)
    var speciesId = state?.getString("species") ?: "poisson"
    var sizePercent = state?.getInt("size", 100) ?: 100
    var tolerance = state?.getInt("tolerance", 45) ?: 45
    var mirrored = state?.getBoolean("mirrored", false) ?: false
    var waitingCamera = state?.getBoolean("waitingCamera", false) ?: false
    var waitingPhoto = state?.getBoolean("waitingPhoto", false) ?: false
    var busy = false
        private set
    var saved = false
        private set
    var error: String? = null
    var onChanged: (() -> Unit)? = null
    private var closed = false
    private val main = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()

    fun restore() {
        // A pending external result must take precedence over the previous draft.
        if (!waitingCamera && !waitingPhoto && source == null && sourceFile.exists()) job {
            source = DrawingScan.decodePhoto(sourceFile)
            if (cutoutFile.exists() && cutoutVersion.exists() && cutoutVersion.readText() == "2") {
                cutout = BitmapFactory.decodeFile(cutoutFile.path)
            }
        }
    }

    fun saveState(out: Bundle) {
        out.putString("session", sessionId)
        out.putString("species", speciesId)
        out.putInt("size", sizePercent)
        out.putInt("tolerance", tolerance)
        out.putBoolean("mirrored", mirrored)
        out.putBoolean("waitingCamera", waitingCamera)
        out.putBoolean("waitingPhoto", waitingPhoto)
        out.putFloatArray("crop", floatArrayOf(crop.left, crop.top, crop.right, crop.bottom))
    }

    fun importPhoto(uri: Uri) = job {
        val raw = File(folder, "import.bin")
        try {
            requireNotNull(context.contentResolver.openInputStream(uri)) { "Photo inaccessible." }.use { input ->
                raw.outputStream().use { output ->
                    val buffer = ByteArray(8192)
                    var total = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        total += count
                        require(total <= 32L * 1024 * 1024) { "La photo dépasse 32 Mo." }
                        output.write(buffer, 0, count)
                    }
                }
            }
            replaceSource(DrawingScan.decodePhoto(raw))
        } finally { raw.delete() }
    }

    fun takePhotoResult() {
        waitingCamera = false
        job { replaceSource(DrawingScan.decodePhoto(cameraFile)) }
    }

    private fun writePng(image: Bitmap, file: File) {
        val atomic = android.util.AtomicFile(file)
        val output = atomic.startWrite()
        try {
            check(image.compress(Bitmap.CompressFormat.PNG, 100, output)) { "Impossible d’enregistrer le dessin." }
            atomic.finishWrite(output)
        } catch (e: Exception) { atomic.failWrite(output); throw e }
    }

    private fun replaceSource(image: Bitmap) {
        writePng(image, sourceFile)
        source = image
        cutout = null
        cutoutFile.delete()
        cutoutVersion.delete()
        crop = RectF(.04f, .04f, .96f, .96f)
        mirrored = false
    }

    fun rotate() {
        val photo = source ?: return
        job {
            replaceSource(Bitmap.createBitmap(photo, 0, 0, photo.width, photo.height,
                Matrix().apply { postRotate(90f) }, true))
        }
    }

    fun extract() {
        val photo = source ?: return
        val selected = RectF(crop)
        val threshold = tolerance
        job {
            val image = DrawingScan.extract(photo, selected, threshold)
            writePng(image, cutoutFile)
            cutoutVersion.writeText("2")
            cutout = image
        }
    }

    fun recrop() {
        if (busy) return
        cutout = null
        cutoutFile.delete()
        cutoutVersion.delete()
        onChanged?.invoke()
    }

    fun add(x: Float) {
        val drawing = cutout ?: return
        val flip = mirrored
        val species = AnimalSpecies.find(speciesId)
        val size = sizePercent / 100f
        job {
            val image = if (flip) Bitmap.createBitmap(drawing, 0, 0, drawing.width, drawing.height,
                Matrix().apply { setScale(-1f, 1f) }, true) else drawing
            try {
                WorldRepository.addAnimal(context, worldId, image, species, size, x, sessionId)
                saved = true
            } finally { if (image !== drawing) image.recycle() }
        }
    }

    private fun job(action: () -> Unit) {
        if (busy || closed) return
        busy = true; error = null
        onChanged?.invoke()
        worker.execute {
            try { action() } catch (e: Exception) { error = e.localizedMessage ?: "Le scan a échoué." }
            main.post {
                busy = false
                if (closed) cleanup() else onChanged?.invoke()
            }
        }
    }

    fun close() {
        closed = true
        onChanged = null
        worker.shutdown()
        if (!busy) cleanup()
    }

    private fun cleanup() {
        // Only this scan's private files. Never touch world archives.
        folder.listFiles()?.forEach { if (it.isFile) it.delete() }
        folder.delete()
    }
}
