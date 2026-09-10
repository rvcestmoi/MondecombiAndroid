package fr.mondesdesanimaux.app

import android.graphics.Bitmap
import android.graphics.Color
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipInputStream

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class AnimalAdditionTest {
    private fun image() = Bitmap.createBitmap(40, 40, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.RED) }
    private fun empty(): ByteArray = ByteArrayOutputStream().also { WorldArchive.createEmpty(it, "Mon essai") }.toByteArray()
    private fun append(input: ByteArray, species: String, token: String): ByteArray = ByteArrayOutputStream().also { out ->
        WorldArchive.appendAnimal(ByteArrayInputStream(input), out, image(), AnimalSpecies.find(species), 1f, 600f, token)
    }.toByteArray()

    @Test fun bothHabitatsAreSavedAndReopenedWithCorrectSpeciesAndPixels() {
        val bytes = append(append(empty(), "poisson", "fish-test"), "chat", "cat-test")
        val world = WorldArchive.read(ByteArrayInputStream(bytes))
        assertEquals(2, world.animals.size)
        assertEquals(listOf("mer", "prairie"), world.animals.map { it.habitat })
        assertEquals(listOf("poisson", "chat"), world.animals.map { it.kind })
        assertTrue(world.animals.all { it.image.getPixel(20, 20) == Color.RED })
        assertNotNull(world.animals[1].ground)
    }

    @Test fun retryingTheSameScanDoesNotDuplicateTheAnimal() {
        val once = append(empty(), "poisson", "same-scan")
        val twice = append(once, "poisson", "same-scan")
        assertEquals(1, WorldArchive.read(ByteArrayInputStream(twice)).animals.size)
    }

    @Test fun previousImagesAndSkeletonRecordsArePreservedExactly() {
        val assets = RuntimeEnvironment.getApplication().assets
        val index = JSONObject(assets.open("worlds/index.json").bufferedReader().use { it.readText() })
        val original = assets.open("worlds/${index.getString("default")}").use { it.readBytes() }
        val updated = append(original, "poisson", "new-drawing")
        val before = entries(original)
        val after = entries(updated)
        assertArrayEquals(before["prairie.zip"], after["prairie.zip"])
        val seaBefore = entries(before.getValue("mer.zip"))
        val seaAfter = entries(after.getValue("mer.zip"))
        for ((name, bytes) in seaBefore) if (name.endsWith(".png")) assertArrayEquals(bytes, seaAfter[name])
        val recordsBefore = JSONObject(seaBefore.getValue("aquarium.json").toString(Charsets.UTF_8)).getJSONArray("fishes")
        val recordsAfter = JSONObject(seaAfter.getValue("aquarium.json").toString(Charsets.UTF_8)).getJSONArray("fishes")
        assertEquals(recordsBefore.length() + 1, recordsAfter.length())
        for (i in 0 until recordsBefore.length()) assertEquals(recordsBefore.get(i).toString(), recordsAfter.get(i).toString())
    }

    @Test fun failedAdditionLeavesStoredWorldIntact() {
        val context = RuntimeEnvironment.getApplication()
        val file = File(context.filesDir, "worlds/atomic-test.zip")
        file.parentFile!!.mkdirs()
        val original = empty()
        file.writeBytes(original)
        try {
            WorldRepository.addAnimal(context, file.name, image(), AnimalSpecies.find("chat"), -1f, 300f, "test")
            fail("Invalid size should fail")
        } catch (_: IllegalArgumentException) { }
        assertArrayEquals(original, file.readBytes())
        WorldRepository.addAnimal(context, file.name, image(), AnimalSpecies.find("chat"), 1f, 300f, "test")
        assertEquals(1, WorldRepository.open(context, file.name).use { WorldArchive.read(it) }.animals.size)
    }

    private fun entries(bytes: ByteArray): Map<String, ByteArray> {
        val result = mutableMapOf<String, ByteArray>()
        ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
            while (true) { val entry = zip.nextEntry ?: break; result[entry.name] = zip.readBytes(); zip.closeEntry() }
        }
        return result
    }
}
