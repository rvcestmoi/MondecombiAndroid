package fr.mondesdesanimaux.app

import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class WorldArchiveTest {
    @Test fun newWorldNeedsNoExistingArchiveAndCanBeReopened() {
        val bytes = ByteArrayOutputStream()
        WorldArchive.createEmpty(bytes, "  Mon essai  ")
        val world = WorldArchive.read(ByteArrayInputStream(bytes.toByteArray()))
        assertEquals("Mon essai", world.name)
        assertTrue(world.animals.isEmpty())
        assertEquals(2, world.screens)
        assertEquals(350f, world.cameraY, .01f)
        assertFalse(world.horizontalAuto)
        assertFalse(world.verticalAuto)
        val reopened = WorldArchive.read(ByteArrayInputStream(bytes.toByteArray()))
        assertEquals(world.name, reopened.name)
        java.util.zip.ZipInputStream(ByteArrayInputStream(bytes.toByteArray())).use { zip ->
            val names = mutableSetOf<String>()
            while (true) { val entry = zip.nextEntry ?: break; names += entry.name; zip.closeEntry() }
            assertEquals(setOf("world.json", "mer.zip", "prairie.zip", "preview.png"), names)
        }
    }

    @Test fun blankNewWorldNameUsesDefault() {
        val bytes = ByteArrayOutputStream()
        WorldArchive.createEmpty(bytes, "   ")
        assertEquals("Nouveau monde", WorldArchive.read(ByteArrayInputStream(bytes.toByteArray())).name)
    }

    @Test fun everyBundledDesktopWorldLoadsItsRealImagesAndRecords() {
        val assets = RuntimeEnvironment.getApplication().assets
        val index = JSONObject(assets.open("worlds/index.json").bufferedReader().use { it.readText() })
        val entries = index.getJSONArray("worlds")
        assertTrue(entries.length() > 0)
        var rigCount = 0
        for (i in 0 until entries.length()) {
            val entry = entries.getJSONObject(i)
            val world = assets.open("worlds/${entry.getString("file")}").use { WorldArchive.read(it) }
            assertEquals(entry.getInt("animals"), world.animals.size)
            assertEquals(entry.getString("name"), world.name)
            assertTrue(world.animals.all { it.image.width > 0 && it.image.height > 0 })
            rigCount += world.animals.count { it.original.optJSONObject("rig") != null }
            world.animals.forEach { it.image.recycle() }
        }
        assertTrue("Desktop skeleton metadata must survive the import", rigCount > 0)
    }

    @Test fun unsupportedVersionIsRejected() {
        rejects(mapOf("world.json" to """{"version":99}"""), "Version")
    }

    @Test fun missingPopulationIsRejected() {
        rejects(mapOf("world.json" to """{"version":1,"settings":{}}"""), "mer.zip")
    }

    @Test fun traversalNamesAreRejected() {
        rejects(mapOf("../world.json" to "{}"), "Nom de fichier")
    }

    @Test fun randomBytesAreRejected() {
        try {
            WorldArchive.read(ByteArrayInputStream(byteArrayOf(1, 2, 3)))
            fail("An invalid ZIP must fail")
        } catch (_: IllegalArgumentException) { }
    }

    private fun rejects(files: Map<String, String>, message: String) {
        val bytes = ByteArrayOutputStream()
        ZipOutputStream(bytes).use { zip ->
            for ((name, value) in files) {
                zip.putNextEntry(ZipEntry(name))
                zip.write(value.toByteArray())
                zip.closeEntry()
            }
        }
        try {
            WorldArchive.read(ByteArrayInputStream(bytes.toByteArray()))
            fail("Invalid archive must fail")
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message.orEmpty(), e.message.orEmpty().contains(message))
        }
    }
}
