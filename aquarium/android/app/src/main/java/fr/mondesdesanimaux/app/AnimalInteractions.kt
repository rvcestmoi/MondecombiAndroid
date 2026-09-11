package fr.mondesdesanimaux.app

import kotlin.math.*
import kotlin.random.Random

/** Encounters from aquarium.py/FishInteractions and animaux_terrestres.py/Interactions. */
class AnimalInteractions(private val random: Random = Random.Default) {
    class Pair(val a: WorldAnimal, val b: WorldAnimal, val kind: String) {
        var time = 0f
        var contact = 0f
        val sea = a.habitat == "mer"
        val centerX = (a.x + b.x) / 2
        val centerY = if (sea) (a.y + b.y) / 2 else (a.y + a.height / 2 + b.y + b.height / 2) / 2
        val label get() = when (kind) { "bisou" -> "Bisou"; "poursuite" -> "Attrape-moi !"; "sauts" -> "On saute !"; else -> "On joue !" }
    }
    private val active = mutableListOf<Pair>()
    val pairs: List<Pair> get() = active

    fun clear() {
        active.forEach { release(it) }
        active.clear()
    }

    private fun compatible(a: WorldAnimal, b: WorldAnimal) = a !== b && a.speed > 0 && b.speed > 0 &&
        a.habitat == b.habitat && if (a.habitat == "mer") a.kind == "poisson" && b.kind == "poisson"
        else a.isBird == b.isBird

    internal fun start(a: WorldAnimal, b: WorldAnimal, kind: String) {
        require(compatible(a, b) && !a.social && !b.social)
        require(kind in if (a.habitat == "mer") listOf("jeu", "bisou", "poursuite") else listOf("jeu", "bisou", "sauts"))
        a.social = true; b.social = true
        active += if (a.x <= b.x) Pair(a, b, kind) else Pair(b, a, kind)
    }

    fun update(animals: List<WorldAnimal>, dt: Float, worldWidth: Float) {
        if (!dt.isFinite() || dt <= 0) return
        val delta = dt.coerceAtMost(.05f)
        val iterator = active.iterator()
        while (iterator.hasNext()) {
            val pair = iterator.next()
            if (animals.none { it === pair.a } || animals.none { it === pair.b } || !compatible(pair.a, pair.b)) {
                release(pair); iterator.remove()
            }
        }
        animals.forEach { it.socialCooldown = max(0f, it.socialCooldown - delta) }
        for (i in animals.indices) {
            val a = animals[i]
            if (a.social || a.socialCooldown > 0 || a.speed <= 0) continue
            for (j in i + 1 until animals.size) {
                val b = animals[j]
                if (b.social || b.socialCooldown > 0 || !compatible(a, b)) continue
                val sea = a.habitat == "mer"
                val dy = if (sea) a.y - b.y else a.y + a.height / 2 - b.y - b.height / 2
                val near = hypot(a.x - b.x, dy) < if (sea) 290f else (a.width + b.width) / 2 + 140
                if (near && (sea || abs(dy) < 90) && random.nextFloat() < 1 - exp(-delta * if (sea) 1.2f else 1f)) {
                    val kinds = if (sea) listOf("jeu", "bisou", "poursuite") else listOf("jeu", "bisou", "sauts")
                    start(a, b, kinds[random.nextInt(kinds.size)])
                    break
                }
            }
        }
        val running = active.iterator()
        while (running.hasNext()) {
            val pair = running.next()
            pair.time += delta
            advancePair(pair, delta, worldWidth)
            if (pair.time > 12 || (pair.kind == "bisou" && pair.contact > 1.5f) ||
                (pair.kind != "bisou" && pair.time > if (pair.sea) 8 else 7)) {
                release(pair); running.remove()
            }
        }
    }

    private fun release(pair: Pair) {
        for (animal in listOf(pair.a, pair.b)) {
            animal.social = false; animal.socialJump = 0f
            animal.socialCooldown = 5 + random.nextFloat() * 4
        }
    }

    private fun advancePair(pair: Pair, dt: Float, width: Float) {
        val a = pair.a; val b = pair.b; val t = pair.time
        if (pair.sea) {
            val cx = pair.centerX.coerceIn(300f, max(300f, width - 300))
            val margin = max(a.height, b.height) / 2 + 95
            val cy = pair.centerY.coerceIn(margin, max(margin, 600 - margin))
            when (pair.kind) {
                "bisou" -> {
                    val closeA = follow(a, cx - a.width / 2, cy, 1, dt, width)
                    val closeB = follow(b, cx + b.width / 2, cy, -1, dt, width)
                    if (closeA && closeB && a.animation.facing > .9f && b.animation.facing < -.9f) pair.contact += dt
                }
                "jeu" -> {
                    val angle = t * .65f
                    follow(a, cx + 130 * cos(angle), cy + 55 * sin(angle), null, dt, width)
                    follow(b, cx - 130 * cos(angle), cy - 55 * sin(angle), null, dt, width)
                }
                else -> {
                    val angle = t * .45f
                    follow(a, cx + 180 * sin(angle), cy + 55 * sin(angle * 2), null, dt, width)
                    follow(b, a.x - a.direction * (a.width + b.width) * .6f, a.y + 15, null, dt, width)
                }
            }
        } else {
            val margin = (a.width + b.width) / 2 + 25
            var cx = pair.centerX.coerceIn(margin, max(margin, width - margin))
            if (pair.kind == "jeu") cx += sin(t * 1.2f) * min(60f, max(0f, width / 2 - margin))
            val closeA = follow(a, cx - a.width / 2, pair.centerY - a.height / 2, 1, dt, width)
            val closeB = follow(b, cx + b.width / 2, pair.centerY - b.height / 2, -1, dt, width)
            if (closeA && closeB) pair.contact += dt
            if (pair.kind != "bisou") {
                a.socialJump = max(0f, sin(t * 5)) * min(32f, a.height * .25f)
                b.socialJump = max(0f, sin(t * 5 + if (pair.kind == "sauts") 0f else PI.toFloat())) * min(32f, b.height * .25f)
            }
        }
    }

    private fun follow(a: WorldAnimal, targetX: Float, targetY: Float, face: Int?, dt: Float, width: Float): Boolean {
        val sea = a.habitat == "mer"
        val margin = a.width / 2 + 20
        val tx = targetX.coerceIn(margin, max(margin, width - margin))
        val lower = a.height / 2 + if (sea) 30 else 5
        val ty = targetY.coerceIn(lower, max(lower, (if (sea) 600 else 700) - a.height / 2))
        val dx = tx - a.x; val dy = ty - a.y
        a.direction = if (!sea && face != null) face else if (abs(dx) > 4) (if (dx > 0) 1 else -1) else face ?: a.direction
        val speed = a.animation.baseSpeed * a.speed * if (sea) 1.25f else 1.3f
        if (sea) {
            val distance = hypot(dx, dy)
            if (distance > 1 && a.animation.facing * a.direction > .5f) {
                val step = min(distance, speed * dt)
                a.x += dx / distance * step; a.y += dy / distance * step
            }
        } else {
            a.x += sign(dx) * min(abs(dx), speed * dt)
            a.y += dy * min(1f, dt * 3 * a.speed)
        }
        return abs(tx - a.x) < (if (sea) 7 else 5) && abs(ty - a.y) < (if (sea) 7 else 4)
    }
}
