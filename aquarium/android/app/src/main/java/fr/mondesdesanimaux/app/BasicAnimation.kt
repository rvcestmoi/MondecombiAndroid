package fr.mondesdesanimaux.app

import kotlin.math.*

/** Whole-drawing animation only: no joints, rig data, or skeletal editor. */
class BasicAnimation(val kind: String, seed: Float, direction: Int) {
    class Pose {
        var offsetY = 0f
        var angle = 0f
        var scaleX = 1f
        var scaleY = 1f
        var speed = 0f
        var gait = 1f
    }
    private data class Action(val mode: String, val seconds: Float, val speed: Float, val amplitude: Float)
    val pose = Pose()
    var facing = direction.toFloat()
        private set
    var phase = seed
        private set
    private var wait = 3f + abs(seed % 5f)
    private var actionIndex = (abs(seed).toInt() % 2) - 1
    private var actionTime = 0f
    private var active: Action? = null
    private val bird = kind in birds
    private val land = kind !in sea && !bird
    val grounded: Boolean get() = land || kind == "crabe" || kind == "etoile"
    val baseSpeed = when (kind) {
        "etoile" -> 9f; "meduse" -> 17f; "crabe" -> 38f; "tortue" -> 40f
        "lapin" -> 65f; "elephant", "rhinoceros", "vache" -> 28f
        "cheval", "zebre" -> 65f
        else -> if (bird) 85f else if (land) 35f else 65f
    }

    init { pose.speed = baseSpeed }

    fun advance(dt: Float, width: Float, height: Float, direction: Int, social: Boolean = false) {
        if (!dt.isFinite() || dt <= 0f) return
        val delta = dt.coerceAtMost(.1f)
        val hz = when (kind) { "moineau" -> 4.5f; "aigle" -> 1.4f; "perroquet" -> 2.8f; else -> 2f }
        phase = (phase + delta * hz * TAU) % (TAU * 100)
        facing += (direction - facing) * min(1f, delta * 8)
        pose.angle = 0f; pose.scaleX = 1f; pose.scaleY = 1f
        pose.speed = baseSpeed; pose.gait = 1f
        pose.offsetY = when {
            kind == "lapin" -> -abs(sin(phase)) * min(22f, height * .13f)
            land -> -abs(sin(phase)) * min(4f, height * .025f)
            bird -> sin(phase * .35f) * 9
            kind == "poisson" || kind == "tortue" -> sin(phase * .3f) * 6
            else -> 0f
        }
        if (kind == "meduse") {
            pose.scaleX = 1 + .07f * sin(phase)
            pose.scaleY = 1 - .06f * sin(phase)
            pose.offsetY = -sin(phase) * 5
        }
        if (kind == "etoile") pose.angle = sin(phase * .12f) * 10
        if (social) {
            active = null
            wait = 6f
            pose.offsetY = 0f
            return
        }
        if (active == null) {
            wait -= delta
            if (wait <= 0) {
                val options = actions[kind] ?: return
                actionIndex = (actionIndex + 1) % options.size
                active = options[actionIndex]
                actionTime = 0f
            }
        }
        val action = active ?: return
        actionTime += delta
        val t = (actionTime / action.seconds).coerceIn(0f, 1f)
        val envelope = sin(PI.toFloat() * t)
        val wave = sin(actionTime * TAU * 2)
        // Blend into and out of each action, including its travel speed.
        pose.speed += (action.speed - baseSpeed) * envelope
        pose.gait = if (action.mode == "glide" || action.mode == "rest") 1 - .95f * envelope
            else if (action.speed == 0f && land) 1 - envelope else 1f
        pose.offsetY *= pose.gait
        val amp = action.amplitude * min(1.5f, max(.3f, width / 180f))
        when (action.mode) {
            "hop" -> pose.offsetY -= abs(wave) * amp * envelope
            "graze", "sniff", "peck" -> pose.angle = -amp * envelope * if (action.mode == "peck") max(0f, wave) else .7f + .3f * wave
            "chew" -> pose.scaleX = 1 + .035f * wave * envelope
            "stretch" -> {
                if (kind == "girafe") pose.scaleY = 1 + .15f * envelope
                else { pose.scaleX = 1 + .12f * envelope; pose.scaleY = 1 - .12f * envelope }
            }
            "rear" -> { pose.angle = amp * envelope; pose.offsetY -= height * .12f * envelope }
            "roll", "sway", "scratch", "roar" -> {
                pose.angle = amp * wave * envelope
                if (action.mode == "roar") pose.scaleY = 1 + .08f * envelope
            }
            "rest" -> pose.scaleY = 1 - .25f * envelope
            "flutter" -> pose.offsetY += amp * wave * envelope
            "wave", "circle" -> {
                pose.offsetY += amp * sin(t * TAU) * envelope
                if (action.mode == "circle") pose.angle = 10 * sin(t * TAU) * envelope
            }
            "dive" -> { pose.offsetY += amp * envelope; pose.angle = -18 * sin(t * TAU) * envelope }
            "pulse" -> { pose.offsetY -= amp * envelope; pose.scaleX *= 1 - .12f * max(0f, wave) * envelope }
            "surface" -> pose.offsetY -= min(180f, height + 50) * envelope
            "dart" -> pose.scaleX = 1 + .05f * envelope
        }
        if (t >= 1f) { active = null; wait = 6f + abs(phase % 6f) }
    }

    /** Deform a small regular texture grid. Head-left coordinates keep the head
     * stable while a fish's tail sways; imported head-right images are normalized. */
    fun fillMesh(vertices: FloatArray, width: Float, height: Float, headLeft: Boolean) {
        var index = 0
        for (row in 0..ROWS) for (column in 0..COLUMNS) {
            val sourceX = column.toFloat() / COLUMNS
            val u = if (headLeft) sourceX else 1 - sourceX
            val v = row.toFloat() / ROWS
            var x = (u - .5f) * width
            var y = (v - .5f) * height
            when {
                kind == "poisson" || kind == "tortue" -> {
                    val tail = ((u - .42f) / .58f).coerceAtLeast(0f)
                    y += height * (if (kind == "tortue") .025f else .07f) * tail * tail * sin(phase - tail * 2) * pose.gait
                }
                kind == "meduse" -> {
                    val tentacle = ((v - .4f) / .6f).coerceAtLeast(0f)
                    x += width * .035f * tentacle * tentacle * sin(phase - v * 3 + u * TAU)
                }
                bird -> {
                    val wing = ((.65f - v) / .65f).coerceAtLeast(0f)
                    val body = ((u - .18f) / .82f).coerceIn(0f, 1f)
                    y += height * .22f * wing * sin(body * PI.toFloat()) * sin(phase) * pose.gait
                }
                land || kind == "crabe" -> {
                    val feet = ((v - .5f) * 2).coerceAtLeast(0f)
                    x += width * .035f * feet * feet * sin(phase + u * TAU) * pose.gait
                    y -= height * .025f * feet * max(0f, sin(phase + u * TAU)) * pose.gait
                }
            }
            vertices[index++] = x; vertices[index++] = y
        }
    }

    companion object {
        const val COLUMNS = 12
        const val ROWS = 10
        const val VERTEX_FLOATS = (COLUMNS + 1) * (ROWS + 1) * 2
        private const val TAU = 6.2831855f
        private val birds = setOf("perroquet", "pigeon", "moineau", "aigle")
        private val sea = setOf("poisson", "meduse", "crabe", "etoile", "tortue")
        // Same two spontaneous behaviours as the desktop version, approximated
        // through whole-image poses and texture deformation without a skeleton.
        private val actions = mapOf(
            "chat" to listOf(Action("stretch", 3f, 0f, 0f), Action("hop", 2f, 45f, 24f)),
            "chien" to listOf(Action("sniff", 3f, 12f, 9f), Action("hop", 3f, 130f, 10f)),
            "lapin" to listOf(Action("hop", 3f, 90f, 30f), Action("graze", 3f, 0f, 8f)),
            "vache" to listOf(Action("graze", 4f, 3f, 12f), Action("chew", 4f, 0f, 0f)),
            "cochon" to listOf(Action("sniff", 4f, 14f, 14f), Action("roll", 3f, 0f, 16f)),
            "mouton" to listOf(Action("graze", 4f, 5f, 10f), Action("hop", 2f, 65f, 22f)),
            "poule" to listOf(Action("peck", 3f, 5f, 18f), Action("scratch", 3f, -8f, 5f)),
            "cheval" to listOf(Action("hop", 4f, 155f, 12f), Action("rear", 2.5f, 0f, 25f)),
            "lion" to listOf(Action("roar", 3f, 0f, 10f), Action("rest", 5f, 0f, 0f)),
            "elephant" to listOf(Action("sway", 4f, 0f, 7f), Action("hop", 4f, 36f, 3f)),
            "girafe" to listOf(Action("stretch", 4f, 0f, 0f), Action("graze", 4f, 0f, 18f)),
            "zebre" to listOf(Action("hop", 4f, 115f, 9f), Action("graze", 3f, 4f, 12f)),
            "rhinoceros" to listOf(Action("hop", 3f, 95f, 4f), Action("scratch", 3f, -5f, 8f)),
            "perroquet" to listOf(Action("wave", 4f, 80f, 30f), Action("flutter", 3f, 0f, 7f)),
            "pigeon" to listOf(Action("circle", 4f, 42f, 20f), Action("glide", 4f, 105f, 0f)),
            "moineau" to listOf(Action("wave", 3f, 145f, 16f), Action("flutter", 2f, 0f, 12f)),
            "aigle" to listOf(Action("circle", 5f, 65f, 38f), Action("dive", 4f, 120f, 80f)),
            "poisson" to listOf(Action("dart", 2f, 190f, 0f), Action("wave", 4f, 65f, 25f)),
            "meduse" to listOf(Action("pulse", 4f, 5f, 65f), Action("wave", 5f, 20f, 15f)),
            "crabe" to listOf(Action("dart", 2f, 90f, 0f), Action("scratch", 3f, 0f, 8f)),
            "etoile" to listOf(Action("roll", 5f, 0f, 35f), Action("wave", 5f, 12f, 0f)),
            "tortue" to listOf(Action("surface", 5f, 18f, 0f), Action("glide", 4f, 50f, 0f)),
        )
    }
}
