package fr.mondesdesanimaux.app

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.abs

class BasicAnimationTest {
    @Test fun allSpeciesProduceFinitePosesThroughSeveralBehaviours() {
        for (species in AnimalSpecies.all) {
            val animation = BasicAnimation(species.id, 0f, -1)
            val mesh = FloatArray(BasicAnimation.VERTEX_FLOATS)
            var changed = false
            for (frame in 0 until 3600) {
                animation.advance(1f / 60, 180f, 140f, if (frame < 1800) -1 else 1)
                val pose = animation.pose
                animation.fillMesh(mesh, 180f, 140f, true)
                assertTrue(species.id, mesh.all { it.isFinite() })
                assertTrue(species.id, pose.speed.isFinite() && pose.offsetY.isFinite() && pose.angle.isFinite())
                assertTrue(species.id, pose.scaleX in .5f..1.5f && pose.scaleY in .5f..1.5f)
                if (abs(pose.offsetY) > .1f || abs(pose.angle) > .1f || abs(pose.scaleX - 1) > .001f) changed = true
            }
            assertTrue("No animation for ${species.id}", changed)
        }
    }

    @Test fun fishTailMovesWhileTheHeadStaysStable() {
        val animation = BasicAnimation("poisson", 0f, -1)
        val before = FloatArray(BasicAnimation.VERTEX_FLOATS)
        val after = FloatArray(BasicAnimation.VERTEX_FLOATS)
        animation.fillMesh(before, 180f, 100f, true)
        animation.advance(.1f, 180f, 100f, -1)
        animation.fillMesh(after, 180f, 100f, true)
        assertEquals(before[0], after[0], .001f)
        assertEquals(before[1], after[1], .001f)
        assertTrue(abs(before[BasicAnimation.COLUMNS * 2 + 1] - after[BasicAnimation.COLUMNS * 2 + 1]) > .1f)
    }

    @Test fun aHeadRightImageUsesTheSameCanonicalPoseAsAHeadLeftImage() {
        val animation = BasicAnimation("poisson", 1f, -1)
        val left = FloatArray(BasicAnimation.VERTEX_FLOATS)
        val right = FloatArray(BasicAnimation.VERTEX_FLOATS)
        animation.fillMesh(left, 180f, 100f, true)
        animation.fillMesh(right, 180f, 100f, false)
        for (row in 0..BasicAnimation.ROWS) for (col in 0..BasicAnimation.COLUMNS) {
            val a = (row * (BasicAnimation.COLUMNS + 1) + col) * 2
            val b = (row * (BasicAnimation.COLUMNS + 1) + BasicAnimation.COLUMNS - col) * 2
            assertEquals(left[a], right[b], .001f)
            assertEquals(left[a + 1], right[b + 1], .001f)
        }
    }

    @Test fun pauseFreezesAnimationAndTurnsAreProgressive() {
        val animation = BasicAnimation("chat", 1f, -1)
        animation.advance(.05f, 180f, 100f, 1)
        assertTrue(animation.facing > -1f && animation.facing < 1f)
        val phase = animation.phase
        val facing = animation.facing
        animation.advance(0f, 180f, 100f, 1)
        assertEquals(phase, animation.phase, 0f)
        assertEquals(facing, animation.facing, 0f)
    }
}
