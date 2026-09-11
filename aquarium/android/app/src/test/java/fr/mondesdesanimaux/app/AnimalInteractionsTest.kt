package fr.mondesdesanimaux.app

import android.graphics.Bitmap
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import kotlin.random.Random

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [26, 36])
class AnimalInteractionsTest {
    private fun animal(kind: String, x: Float, speed: Float = 1f): WorldAnimal {
        val habitat = AnimalSpecies.find(kind).habitat
        val image = Bitmap.createBitmap(40, 40, Bitmap.Config.ARGB_8888)
        val a = WorldAnimal(image, kind, habitat, x, 350f, -1, 1f, speed, null, JSONObject(), 0f)
        if (habitat == "prairie") a.y = (if (a.isBird) 350 else 620) - a.height / 2
        a.socialCooldown = 0f
        return a
    }
    private fun step(engine: AnimalInteractions, animals: List<WorldAnimal>, dt: Float = .05f) {
        engine.update(animals, dt, 2400f)
        animals.forEach { it.animation.advance(dt * it.speed, it.width, it.height, it.direction, it.social) }
    }

    @Test fun encountersStartAutomaticallyForNearbyCompatibleAnimalsOnly() {
        val compatible = listOf("poisson" to "poisson", "chat" to "chien", "pigeon" to "aigle")
        for ((first, second) in compatible) {
            val engine = AnimalInteractions(Random(1))
            val animals = listOf(animal(first, 500f), animal(second, 650f))
            var seen = false
            repeat(200) { step(engine, animals); seen = seen || engine.pairs.isNotEmpty() }
            assertTrue("$first / $second", seen)
        }
        for ((first, second) in listOf("poisson" to "tortue", "chat" to "pigeon", "poisson" to "chat", "crabe" to "crabe")) {
            val engine = AnimalInteractions(Random(1))
            val animals = listOf(animal(first, 500f), animal(second, 510f))
            repeat(300) { step(engine, animals) }
            assertTrue(engine.pairs.isEmpty())
        }
    }

    @Test fun pauseAndZeroSpeedDoNotMoveAnimalsOrAdvanceEncounters() {
        val engine = AnimalInteractions(Random(2))
        val a = animal("poisson", 500f); val b = animal("poisson", 600f)
        engine.start(a, b, "jeu")
        engine.update(listOf(a, b), 0f, 2400f)
        assertEquals(0f, engine.pairs.single().time, 0f)
        assertEquals(500f, a.x, 0f)
        engine.clear()
        val still = animal("poisson", 500f, 0f)
        repeat(300) { step(engine, listOf(still, b)) }
        assertTrue(engine.pairs.isEmpty())
        assertEquals(500f, still.x, 0f)
    }

    @Test fun kissMakesContactAndEndsWithCooldownInBothHabitats() {
        for (kind in listOf("poisson", "chat")) {
            val engine = AnimalInteractions(Random(3))
            val a = animal(kind, 500f); val b = animal(kind, 700f)
            engine.start(a, b, "bisou")
            var contact = false
            var ended = false
            repeat(250) {
                if (!ended) {
                    step(engine, listOf(a, b))
                    contact = contact || engine.pairs.any { it.contact > 0 }
                    ended = engine.pairs.isEmpty()
                }
            }
            assertTrue(kind, contact)
            assertTrue(kind, ended)
            assertFalse(a.social)
            assertTrue(a.socialCooldown in 5f..9f)
        }
    }

    @Test fun playPursuitAndJumpsMoveThenReleasePartnersWithinBounds() {
        for ((species, mode) in listOf("poisson" to "jeu", "poisson" to "poursuite", "chat" to "jeu", "lapin" to "sauts")) {
            val engine = AnimalInteractions(Random(4))
            val a = animal(species, 120f); val b = animal(species, 220f)
            engine.start(a, b, mode)
            var jumped = false
            var moved = false
            repeat(180) {
                step(engine, listOf(a, b))
                jumped = jumped || a.socialJump > 1
                moved = moved || kotlin.math.abs(a.x - 120f) > 1
                assertTrue(a.x.isFinite() && a.y.isFinite())
                assertTrue(a.x >= a.width / 2 + 20 && a.x <= 2400 - a.width / 2 - 20)
            }
            assertTrue("$species / $mode must move", moved)
            if (species != "poisson") assertTrue(jumped)
            assertTrue(engine.pairs.isEmpty())
            assertEquals(0f, a.socialJump, 0f)
        }
    }

    @Test fun removalAndWorldChangeReleaseTheSurvivingPartner() {
        val engine = AnimalInteractions(Random(5))
        val a = animal("chat", 500f); val b = animal("chien", 600f)
        engine.start(a, b, "sauts")
        step(engine, listOf(a, b))
        step(engine, listOf(b))
        assertTrue(engine.pairs.isEmpty())
        assertFalse(b.social)
        assertEquals(0f, b.socialJump, 0f)
        engine.start(a, b, "jeu")
        engine.clear()
        assertFalse(a.social)
        assertFalse(b.social)
    }

    @Test fun oneAnimalCannotParticipateInTwoEncounters() {
        val engine = AnimalInteractions(Random(6))
        val a = animal("poisson", 500f); val b = animal("poisson", 600f); val c = animal("poisson", 550f)
        engine.start(a, b, "jeu")
        repeat(30) { step(engine, listOf(a, b, c)) }
        assertEquals(1, engine.pairs.size)
        assertFalse(c.social)
    }
}
