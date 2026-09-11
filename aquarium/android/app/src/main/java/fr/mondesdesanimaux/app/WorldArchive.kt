package fr.mondesdesanimaux.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream
import kotlin.math.min

data class WorldAnimal(
    val image: Bitmap,
    val kind: String,
    val habitat: String,
    var x: Float,
    var y: Float,
    var direction: Int,
    val size: Float,
    val speed: Float,
    val ground: Float?,
    // Keep the complete Python record, including the rig, for subsequent migration stages.
    val original: JSONObject,
    val phase: Float,
) {
    val isBird = kind in setOf("perroquet", "pigeon", "moineau", "aigle")
    val isOnSand = kind == "crabe" || kind == "etoile"
    private val bounds = when {
        isBird -> 145f to 105f
        habitat == "prairie" -> 200f to 180f
        kind == "meduse" -> 150f to 200f
        kind == "crabe" -> 160f to 110f
        kind == "etoile" -> 130f to 130f
        kind == "tortue" -> 190f to 150f
        else -> 180f to 240f
    }
    private val ratio = min(bounds.first / image.width, bounds.second / image.height) * size
    val width = image.width * ratio
    val height = image.height * ratio
    val headLeft = original.optJSONObject("rig")?.optBoolean("head_left", true) ?: true
    val animation = BasicAnimation(kind, phase, direction)
    val meshVertices = FloatArray(BasicAnimation.VERTEX_FLOATS)
    var social = false
    var socialJump = 0f
    var socialCooldown = 1f + phase % 2f
}

data class AnimalWorld(
    val name: String,
    val screens: Int,
    val cameraX: Float,
    val cameraY: Float,
    val zoom: Float,
    val horizontalAuto: Boolean,
    val verticalAuto: Boolean,
    val horizontalSpeed: Float,
    val verticalSpeed: Float,
    val animals: List<WorldAnimal>,
    val original: JSONObject,
) {
    val width get() = screens * 1200f
}

/** Read the existing desktop ZIP format directly. Never extract paths onto disk. */
object WorldArchive {
    const val MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
    private const val MAX_EXPANDED_BYTES = 64 * 1024 * 1024
    private const val MAX_ANIMALS = 200
    private const val MAX_DECODED_PIXELS = 16 * 1024 * 1024
    private val seaKinds = setOf("poisson", "meduse", "crabe", "etoile", "tortue")
    private val landKinds = setOf("chat", "chien", "lapin", "vache", "cochon", "mouton", "poule",
        "cheval", "lion", "elephant", "girafe", "zebre", "rhinoceros", "perroquet", "pigeon", "moineau", "aigle")

    fun read(input: InputStream): AnimalWorld {
        val outer = entries(input)
        val meta = json(outer, "world.json")
        require(meta.getInt("version") == 1) { "Version de monde non prise en charge." }
        val settings = meta.getJSONObject("settings")
        val screens = settings.optInt("screens", 1).coerceIn(1, 5)
        val animals = mutableListOf<WorldAnimal>()
        var pixels = 0L
        try {
            for (habitat in listOf("mer", "prairie")) {
                val data = entries(ByteArrayInputStream(required(outer, "$habitat.zip")))
                val population = json(data, if (habitat == "mer") "aquarium.json" else "prairie.json")
                require(population.getInt("version") == 1) { "Version de population non prise en charge." }
                val records = population.getJSONArray("fishes")
                require(animals.size + records.length() <= MAX_ANIMALS) { "Maximum : $MAX_ANIMALS animaux par monde." }
                for (index in 0 until records.length()) {
                    val record = records.getJSONObject(index)
                    val kind = record.getString("kind")
                    require(kind in if (habitat == "mer") seaKinds else landKinds) { "Espèce inconnue : $kind" }
                    val encoded = required(data, record.getString("image"))
                    val options = BitmapFactory.Options().apply {
                        inJustDecodeBounds = true
                        // Android defaults to 0, meaning "no sampling" to the decoder.
                        // Our dimension arithmetic needs an explicit non-zero divisor.
                        inSampleSize = 1
                    }
                    BitmapFactory.decodeByteArray(encoded, 0, encoded.size, options)
                    require(options.outWidth in 1..8192 && options.outHeight in 1..8192) { "Dimensions d’image invalides." }
                    while (options.outWidth / options.inSampleSize > 1024 || options.outHeight / options.inSampleSize > 1024) {
                        options.inSampleSize *= 2
                    }
                    pixels += (options.outWidth / options.inSampleSize + 1).toLong() *
                        (options.outHeight / options.inSampleSize + 1)
                    require(pixels <= MAX_DECODED_PIXELS) { "Les dessins de ce monde sont trop volumineux." }
                    // Validate all metadata before allocating the bitmap.
                    val x = record.finite("x", 600f).coerceIn(0f, screens * 1200f)
                    val y = record.finite("y", 350f).coerceIn(0f, 700f)
                    val size = record.finite("size", 1f).coerceIn(.05f, 2f)
                    val speed = record.finite("speed", 1f).coerceIn(0f, 2f)
                    val ground = if (record.has("ground")) record.finite("ground", 600f) else null
                    options.inJustDecodeBounds = false
                    val bitmap = BitmapFactory.decodeByteArray(encoded, 0, encoded.size, options)
                        ?: error("Dessin illisible : ${record.getString("image")}")
                    animals += WorldAnimal(bitmap, kind, habitat, x, y,
                        if (record.optInt("direction", -1) < 0) -1 else 1,
                        size, speed, ground, record, animals.size * 1.73f)
                }
            }
            val camera = meta.optJSONArray("camera")
            val x = (camera?.optDouble(0, 0.0) ?: 0.0).toFloat()
            val y = (camera?.optDouble(1, 350.0) ?: 350.0).toFloat()
            require(x.isFinite() && y.isFinite()) { "Position de caméra invalide." }
            return AnimalWorld(meta.optString("name", "Mon monde").take(80), screens, x, y,
                settings.finite("zoom", 1f).coerceIn(.5f, 2f),
                settings.optBoolean("auto", false), settings.optBoolean("vertical_auto", false),
                settings.finite("scroll_speed", 1f).coerceIn(.25f, 3f),
                settings.finite("vertical_speed", 1f).coerceIn(.25f, 3f), animals, meta)
        } catch (e: Exception) {
            animals.forEach { it.image.recycle() }
            throw e
        }
    }

    /** Produce an empty, self-contained world in the desktop format as well. */
    fun appendAnimal(input: InputStream, output: OutputStream, drawing: Bitmap,
                     species: AnimalSpecies, size: Float, x: Float, scanId: String) {
        require(scanId.matches(Regex("[a-zA-Z0-9-]{1,80}"))) { "Identifiant de scan invalide." }
        require(size.isFinite() && size in .25f..2f && x.isFinite()) { "Taille ou position invalide." }
        val outer = entries(input).toMutableMap()
        val meta = json(outer, "world.json")
        require(meta.getInt("version") == 1) { "Version de monde inconnue." }
        var count = 0
        var alreadyAdded = false
        for ((habitat, manifest) in listOf("mer" to "aquarium", "prairie" to "prairie")) {
            val population = json(entries(ByteArrayInputStream(required(outer, "$habitat.zip"))), "$manifest.json")
            val records = population.getJSONArray("fishes")
            count += records.length()
            for (i in 0 until records.length()) if (records.getJSONObject(i).optString("scan_id") == scanId) alreadyAdded = true
        }
        if (!alreadyAdded) {
            require(count < MAX_ANIMALS) { "Ce monde contient déjà $MAX_ANIMALS animaux." }
            val habitat = species.habitat
            val files = entries(ByteArrayInputStream(required(outer, "$habitat.zip"))).toMutableMap()
            val manifest = if (habitat == "mer") "aquarium.json" else "prairie.json"
            val population = json(files, manifest)
            val name = "scan_$scanId.png"
            val encoded = ByteArrayOutputStream()
            check(drawing.compress(Bitmap.CompressFormat.PNG, 100, encoded)) { "Impossible d’enregistrer le dessin." }
            val width = meta.getJSONObject("settings").optInt("screens", 1).coerceIn(1, 5) * 1200f
            val record = JSONObject().put("image", name).put("kind", species.id)
                .put("size", size).put("speed", 1).put("direction", -1)
                .put("rig", JSONObject.NULL).put("scan_id", scanId)
            val animal = WorldAnimal(drawing, species.id, habitat, 0f, 0f, -1, size, 1f, null, record, 0f)
            val ground = if (animal.isBird) 350f else 620f
            val y = when {
                habitat == "prairie" -> ground - animal.height / 2
                animal.isOnSand -> 660f - animal.height / 2
                else -> 350f
            }
            record.put("x", x.coerceIn(animal.width / 2 + 20, width - animal.width / 2 - 20))
                .put("y", y)
            if (habitat == "prairie") record.put("ground", ground)
            population.getJSONArray("fishes").put(record)
            files[name] = encoded.toByteArray()
            files[manifest] = population.toString().toByteArray(Charsets.UTF_8)
            val nested = ByteArrayOutputStream()
            writeEntries(nested, files)
            outer["$habitat.zip"] = nested.toByteArray()
        }
        writeEntries(output, outer)
    }

    /** Edit one exact record, including old imports without scan IDs. A stale
     * selection must fail rather than modify a different animal after deletion. */
    fun editAnimal(input: InputStream, output: OutputStream, habitat: String, index: Int,
                   expectedRecord: String, size: Float, speed: Float, delete: Boolean) {
        require(habitat == "mer" || habitat == "prairie") { "Habitat invalide." }
        require(size.isFinite() && size in .05f..2f && speed.isFinite() && speed in 0f..2f) {
            "Taille ou vitesse invalide."
        }
        val outer = entries(input).toMutableMap()
        val files = entries(ByteArrayInputStream(required(outer, "$habitat.zip"))).toMutableMap()
        val manifest = if (habitat == "mer") "aquarium.json" else "prairie.json"
        val population = json(files, manifest)
        val records = population.getJSONArray("fishes")
        require(index in 0 until records.length() && records.getJSONObject(index).toString() == expectedRecord) {
            "Cet animal a changé. Rouvre le monde avant de réessayer."
        }
        val record = records.getJSONObject(index)
        if (delete) {
            records.remove(index)
            val imageName = record.getString("image")
            // Imported animals can share the same PNG.
            if ((0 until records.length()).none { records.getJSONObject(it).getString("image") == imageName }
                && imageName.endsWith(".png", ignoreCase = true)) files.remove(imageName)
        } else {
            // Preserve the foot position when resizing a ground animal.
            val kind = record.getString("kind")
            val grounded = habitat == "prairie" && kind !in setOf("perroquet", "pigeon", "moineau", "aigle") ||
                kind == "crabe" || kind == "etoile"
            if (grounded && size != record.finite("size", 1f).coerceIn(.05f, 2f)) {
                val encoded = required(files, record.getString("image"))
                val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true; inSampleSize = 1 }
                BitmapFactory.decodeByteArray(encoded, 0, encoded.size, bounds)
                require(bounds.outWidth > 0 && bounds.outHeight > 0) { "Dessin illisible." }
                val box = if (kind == "crabe") 160f to 110f else if (kind == "etoile") 130f to 130f else 200f to 180f
                val baseHeight = bounds.outHeight * min(box.first / bounds.outWidth, box.second / bounds.outHeight)
                val oldSize = record.finite("size", 1f).coerceIn(.05f, 2f)
                record.put("y", (record.finite("y", 350f) + baseHeight / 2 * (oldSize - size)).coerceIn(0f, 700f))
            }
            record.put("size", size).put("speed", speed)
        }
        files[manifest] = population.toString().toByteArray(Charsets.UTF_8)
        val nested = ByteArrayOutputStream()
        writeEntries(nested, files)
        outer["$habitat.zip"] = nested.toByteArray()
        writeEntries(output, outer)
    }

    fun duplicateAnimal(input: InputStream, output: OutputStream, habitat: String, index: Int,
                        expectedRecord: String, token: String) {
        require(habitat in listOf("mer", "prairie") && token.matches(Regex("[a-zA-Z0-9-]{1,80}")))
        val outer = entries(input).toMutableMap()
        var count = 0
        for (area in listOf("mer", "prairie")) {
            val population = json(entries(ByteArrayInputStream(required(outer, "$area.zip"))),
                if (area == "mer") "aquarium.json" else "prairie.json")
            val records = population.getJSONArray("fishes")
            count += records.length()
            for (i in 0 until records.length()) if (records.getJSONObject(i).optString("scan_id") == token) {
                writeEntries(output, outer)
                return
            }
        }
        require(count < MAX_ANIMALS) { "Ce monde contient déjà $MAX_ANIMALS animaux." }
        val files = entries(ByteArrayInputStream(required(outer, "$habitat.zip"))).toMutableMap()
        val manifest = if (habitat == "mer") "aquarium.json" else "prairie.json"
        val population = json(files, manifest)
        val records = population.getJSONArray("fishes")
        require(index in 0 until records.length() && records.getJSONObject(index).toString() == expectedRecord) {
            "Cet animal a changé. Rouvre le monde avant de réessayer."
        }
        val original = records.getJSONObject(index)
        val copy = JSONObject(original.toString())
        val name = "copy_$token.png"
        require(!files.containsKey(name)) { "Ce dessin existe déjà." }
        files[name] = required(files, original.getString("image"))
        val width = json(outer, "world.json").getJSONObject("settings").optInt("screens", 1).coerceIn(1, 5) * 1200f
        val x = original.finite("x", 600f)
        copy.put("image", name).put("scan_id", token)
            .put("x", (if (x + 220 < width - 220) x + 220 else x - 220).coerceIn(220f, width - 220))
        records.put(copy)
        files[manifest] = population.toString().toByteArray(Charsets.UTF_8)
        val nested = ByteArrayOutputStream()
        writeEntries(nested, files)
        outer["$habitat.zip"] = nested.toByteArray()
        writeEntries(output, outer)
    }

    private fun writeEntries(output: OutputStream, data: Map<String, ByteArray>) {
        ZipOutputStream(output).use { zip ->
            for ((name, bytes) in data) {
                zip.putNextEntry(ZipEntry(name)); zip.write(bytes); zip.closeEntry()
            }
        }
    }

    fun createEmpty(output: OutputStream, name: String) {
        val settings = JSONObject().put("screens", 2).put("auto", false)
            .put("scroll_speed", 1).put("vertical_auto", false)
            .put("vertical_speed", 1).put("zoom", 1)
        val meta = JSONObject().put("version", 1)
            .put("name", name.trim().take(40).ifEmpty { "Nouveau monde" })
            .put("settings", settings).put("camera", org.json.JSONArray().put(0).put(350))
        ZipOutputStream(output).use { zip ->
            fun write(name: String, bytes: ByteArray) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(bytes)
                zip.closeEntry()
            }
            write("world.json", meta.toString().toByteArray(Charsets.UTF_8))
            for ((habitat, manifest) in listOf("mer" to "aquarium", "prairie" to "prairie")) {
                val bytes = ByteArrayOutputStream()
                ZipOutputStream(bytes).use { population ->
                    population.putNextEntry(ZipEntry("$manifest.json"))
                    population.write(JSONObject().put("version", 1)
                        .put("fishes", org.json.JSONArray()).put("view", settings)
                        .toString().toByteArray(Charsets.UTF_8))
                    population.closeEntry()
                }
                write("$habitat.zip", bytes.toByteArray())
            }
            val preview = Bitmap.createBitmap(300, 175, Bitmap.Config.ARGB_8888)
            try {
                val canvas = android.graphics.Canvas(preview)
                val paint = android.graphics.Paint()
                canvas.drawColor(android.graphics.Color.rgb(20, 120, 175))
                paint.color = android.graphics.Color.rgb(224, 201, 143)
                canvas.drawRect(0f, 87.5f, 300f, 112.5f, paint)
                paint.color = android.graphics.Color.rgb(104, 164, 84)
                canvas.drawRect(0f, 112.5f, 300f, 175f, paint)
                val png = ByteArrayOutputStream()
                check(preview.compress(Bitmap.CompressFormat.PNG, 100, png)) { "Impossible de créer l’aperçu." }
                write("preview.png", png.toByteArray())
            } finally {
                preview.recycle()
            }
        }
    }

    private fun entries(input: InputStream): Map<String, ByteArray> {
        val result = mutableMapOf<String, ByteArray>()
        var total = 0
        ZipInputStream(input).use { zip ->
            val buffer = ByteArray(8192)
            while (true) {
                val entry = zip.nextEntry ?: break
                require(result.size < 512) { "Archive contenant trop de fichiers." }
                require(!entry.isDirectory && entry.name.matches(Regex("[A-Za-z0-9_.-]+"))) { "Nom de fichier invalide." }
                require(!result.containsKey(entry.name)) { "Fichier en double dans l’archive." }
                val out = ByteArrayOutputStream()
                while (true) {
                    val count = zip.read(buffer)
                    if (count < 0) break
                    total += count
                    require(total <= MAX_EXPANDED_BYTES && out.size() + count <= MAX_ARCHIVE_BYTES) { "Archive trop volumineuse." }
                    out.write(buffer, 0, count)
                }
                result[entry.name] = out.toByteArray()
                zip.closeEntry()
            }
        }
        return result
    }

    private fun required(data: Map<String, ByteArray>, name: String): ByteArray =
        requireNotNull(data[name]) { "Fichier manquant : $name" }

    private fun json(data: Map<String, ByteArray>, name: String): JSONObject {
        val bytes = required(data, name)
        require(bytes.size <= 2 * 1024 * 1024) { "Métadonnées trop volumineuses." }
        return JSONObject(bytes.toString(Charsets.UTF_8))
    }

    private fun JSONObject.finite(key: String, default: Float): Float {
        val value = optDouble(key, default.toDouble()).toFloat()
        require(value.isFinite()) { "Valeur invalide : $key" }
        return value
    }
}
