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
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class AnimalSettingsTest {
    private fun fixture(): ByteArray {
        var bytes = ByteArrayOutputStream().also { WorldArchive.createEmpty(it, "Réglages") }.toByteArray()
        val image = Bitmap.createBitmap(40, 40, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.RED) }
        try {
            for ((i, kind) in listOf("poisson", "poisson", "chat").withIndex()) {
                bytes = ByteArrayOutputStream().also {
                    WorldArchive.appendAnimal(ByteArrayInputStream(bytes), it, image, AnimalSpecies.find(kind), 1f, 600f, "animal-$i")
                }.toByteArray()
            }
        } finally { image.recycle() }
        return bytes
    }

    private fun read(bytes: ByteArray) = WorldArchive.read(ByteArrayInputStream(bytes))
    private fun edit(bytes: ByteArray, habitat: String, index: Int, record: String,
                     size: Float = 1f, speed: Float = 1f, delete: Boolean = false) =
        ByteArrayOutputStream().also {
            WorldArchive.editAnimal(ByteArrayInputStream(bytes), it, habitat, index, record, size, speed, delete)
        }.toByteArray()

    @Test fun settingsPersistForOnlyTheSelectedAnimalAndPreservePngs() {
        val bytes = fixture()
        val before = read(bytes)
        val updated = edit(bytes, "mer", 1, before.animals[1].original.toString(), .5f, 0f)
        val after = read(updated)
        assertEquals(.5f, after.animals[1].size, 0f)
        assertEquals(0f, after.animals[1].speed, 0f)
        assertEquals(before.animals[0].original.toString(), after.animals[0].original.toString())
        val outerBefore = entries(bytes)
        val outerAfter = entries(updated)
        assertArrayEquals(outerBefore["prairie.zip"], outerAfter["prairie.zip"])
        assertArrayEquals(outerBefore["world.json"], outerAfter["world.json"])
        val seaAfter = entries(outerAfter.getValue("mer.zip"))
        for ((name, png) in entries(outerBefore.getValue("mer.zip"))) {
            if (name.endsWith(".png")) assertArrayEquals(png, seaAfter[name])
        }
    }

    @Test fun resizingLandAnimalKeepsItsFeetOnTheGround() {
        val bytes = fixture()
        val old = read(bytes).animals.last()
        val after = read(edit(bytes, "prairie", 0, old.original.toString(), 2f, 2f)).animals.last()
        assertEquals(old.y + old.height / 2, after.y + after.height / 2, .01f)
        assertEquals(2f, after.speed, 0f)
    }

    @Test fun deletingOneOfTwoIdenticalSpeciesKeepsTheOtherAndCanEmptyAHabitat() {
        val bytes = fixture()
        val old = read(bytes)
        val updated = edit(bytes, "mer", 0, old.animals[0].original.toString(), delete = true)
        val after = read(updated)
        assertEquals(2, after.animals.size)
        assertEquals("animal-1", after.animals[0].original.getString("scan_id"))
        assertFalse(entries(entries(updated).getValue("mer.zip")).containsKey("scan_animal-0.png"))
        val emptySea = read(edit(updated, "mer", 0, after.animals[0].original.toString(), delete = true))
        assertEquals(listOf("chat"), emptySea.animals.map { it.kind })
    }

    @Test fun staleSelectionAndInvalidSettingsLeaveStoredArchiveUntouched() {
        val context = RuntimeEnvironment.getApplication()
        val file = File(context.filesDir, "worlds/settings-test.zip")
        file.parentFile!!.mkdirs()
        val bytes = fixture()
        file.writeBytes(bytes)
        val expected = read(bytes).animals[0].original.toString()
        for ((index, speed) in listOf(1 to 1f, 0 to Float.NaN, 0 to -1f)) {
            try {
                WorldRepository.editAnimal(context, file.name, "mer", index, expected, 1f, speed, false)
                fail("Invalid or stale edit must fail")
            } catch (_: IllegalArgumentException) { }
            assertArrayEquals(bytes, file.readBytes())
        }
        WorldRepository.editAnimal(context, file.name, "mer", 0, expected, .75f, 1.5f, false)
        val saved = WorldRepository.open(context, file.name).use { WorldArchive.read(it) }
        assertEquals(.75f, saved.animals[0].size, 0f)
        assertEquals(1.5f, saved.animals[0].speed, 0f)
    }

    @Test fun sharedDrawingAndImportedRigSurviveEditingAndDeletion() {
        val outer = entries(fixture()).toMutableMap()
        val sea = entries(outer.getValue("mer.zip")).toMutableMap()
        val population = JSONObject(sea.getValue("aquarium.json").toString(Charsets.UTF_8))
        val records = population.getJSONArray("fishes")
        val second = records.getJSONObject(1)
        second.put("image", records.getJSONObject(0).getString("image"))
        second.remove("scan_id")
        second.put("rig", JSONObject().put("head_left", false).put("custom", "preserved"))
        sea["aquarium.json"] = population.toString().toByteArray(Charsets.UTF_8)
        outer["mer.zip"] = zip(sea)
        val bytes = zip(outer)
        val before = read(bytes)
        val deleted = edit(bytes, "mer", 0, before.animals[0].original.toString(), delete = true)
        val survivor = read(deleted).animals[0]
        val updated = read(edit(deleted, "mer", 0, survivor.original.toString(), 1.5f, .5f)).animals[0]
        assertEquals(Color.RED, updated.image.getPixel(20, 20))
        assertEquals(second.getJSONObject("rig").toString(), updated.original.getJSONObject("rig").toString())
    }

    @Test fun duplicatePreservesSettingsAndCanBeDeletedIndependently() {
        val bytes = fixture()
        val original = read(bytes).animals.last()
        val adjusted = edit(bytes, "prairie", 0, original.original.toString(), 1.5f, .5f)
        val target = read(adjusted).animals.last()
        fun duplicate(input: ByteArray) = ByteArrayOutputStream().also {
            WorldArchive.duplicateAnimal(ByteArrayInputStream(input), it, "prairie", 0, target.original.toString(), "copy-test")
        }.toByteArray()
        val copied = duplicate(adjusted)
        val reopened = read(copied)
        val copy = reopened.animals.last()
        assertEquals(4, reopened.animals.size)
        assertEquals(1.5f, copy.size, 0f)
        assertEquals(.5f, copy.speed, 0f)
        assertNotEquals(target.original.getString("image"), copy.original.getString("image"))
        assertNotEquals(target.x, copy.x)
        assertEquals(Color.RED, copy.image.getPixel(20, 20))
        assertEquals(4, read(duplicate(copied)).animals.size)
        val afterDelete = read(edit(copied, "prairie", 0, target.original.toString(), delete = true))
        assertEquals(3, afterDelete.animals.size)
        assertEquals("copy-test", afterDelete.animals.last().original.getString("scan_id"))
    }

    @Test fun failedDuplicationLeavesArchiveUnchanged() {
        val context = RuntimeEnvironment.getApplication()
        val file = File(context.filesDir, "worlds/duplicate-test.zip")
        file.parentFile!!.mkdirs()
        val bytes = fixture(); file.writeBytes(bytes)
        try {
            WorldRepository.duplicateAnimal(context, file.name, "mer", 0, "stale-record", "new-copy")
            fail("Stale selection must fail")
        } catch (_: IllegalArgumentException) { }
        assertArrayEquals(bytes, file.readBytes())
    }

    private fun zip(files: Map<String, ByteArray>): ByteArray = ByteArrayOutputStream().also { out ->
        ZipOutputStream(out).use { zip ->
            for ((name, bytes) in files) {
                zip.putNextEntry(ZipEntry(name)); zip.write(bytes); zip.closeEntry()
            }
        }
    }.toByteArray()

    private fun entries(bytes: ByteArray): Map<String, ByteArray> {
        val result = mutableMapOf<String, ByteArray>()
        ZipInputStream(ByteArrayInputStream(bytes)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                result[entry.name] = zip.readBytes()
                zip.closeEntry()
            }
        }
        return result
    }
}
