package fr.mondesdesanimaux.app

import android.content.Context
import android.graphics.Bitmap
import android.util.AtomicFile
import java.io.File
import java.io.InputStream

object WorldRepository {
    private fun destination(context: Context, id: String): File {
        require(id.matches(Regex("[a-zA-Z0-9_-]+\\.zip"))) { "Identifiant de monde invalide." }
        return File(File(context.filesDir, "worlds").apply { mkdirs() }, id)
    }

    fun open(context: Context, id: String): InputStream {
        val file = destination(context, id)
        return if (file.exists() || File(file.path + ".bak").exists()) AtomicFile(file).openRead()
        else context.assets.open("worlds/$id")
    }

    /** Validate the complete new archive before atomically replacing the local world.
     * Bundled examples get a local override; the packaged originals remain intact. */
    @Synchronized
    fun addAnimal(context: Context, id: String, image: Bitmap, species: AnimalSpecies,
                  size: Float, x: Float, scanId: String) {
        val file = destination(context, id)
        val temporary = File.createTempFile("addition-", ".zip", file.parentFile)
        try {
            open(context, id).use { source ->
                temporary.outputStream().use { out -> WorldArchive.appendAnimal(source, out, image, species, size, x, scanId) }
            }
            require(temporary.length() <= WorldArchive.MAX_ARCHIVE_BYTES) { "Le monde dépasse la limite de 32 Mo." }
            val verified = temporary.inputStream().use { WorldArchive.read(it) }
            verified.animals.forEach { it.image.recycle() }
            val atomic = AtomicFile(file)
            val output = atomic.startWrite()
            try {
                temporary.inputStream().use { it.copyTo(output) }
                atomic.finishWrite(output)
            } catch (e: Exception) {
                atomic.failWrite(output)
                throw e
            }
        } finally { temporary.delete() }
    }
}
