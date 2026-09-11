package fr.mondesdesanimaux.app

import android.content.Context
import android.graphics.*
import android.os.SystemClock
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.ViewConfiguration
import kotlin.math.*

/** Native, continuously redrawn scene; no Python interpreter or network required. */
class WorldView(context: Context) : View(context) {
    val camera = WorldCamera()
    var world: AnimalWorld? = null
        private set
    var playing = true
    var autoScroll = false
    var verticalAutoScroll = false
    var onCameraChanged: (() -> Unit)? = null
    private var active = false
    private var lastFrame = 0L
    private var elapsed = 0f
    private val interactions = AnimalInteractions()
    private var autoDirectionX = 1
    private var autoDirectionY = 1
    private var manualUntil = 0L
    private var pointerId = -1
    private var lastX = 0f
    private var lastY = 0f
    private var downX = 0f
    private var downY = 0f
    private var moved = false
    private val slop = ViewConfiguration.get(context).scaledTouchSlop
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val path = Path()
    private val rect = RectF()
    private val scaler = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            camera.zoomAt(detector.scaleFactor, detector.focusX, detector.focusY)
            manualNavigation()
            moved = true
            return true
        }
    })

    init {
        contentDescription = "Monde animé. Glissez pour explorer, pincez pour zoomer. Les boutons Mer, Prairie et Zoom permettent aussi la navigation."
        isFocusable = true
    }

    fun showWorld(value: AnimalWorld) {
        interactions.clear()
        world = value
        camera.worldWidth = value.width
        camera.x = value.cameraX
        camera.y = value.cameraY
        camera.zoom = value.zoom
        camera.clamp()
        autoScroll = value.horizontalAuto
        verticalAutoScroll = value.verticalAuto
        elapsed = 0f
        lastFrame = 0L
        invalidate()
    }

    fun setActive(value: Boolean) {
        active = value
        lastFrame = 0L
        if (value) postInvalidateOnAnimation()
    }

    fun manualNavigation() {
        manualUntil = SystemClock.uptimeMillis() + 3000
        invalidate()
        onCameraChanged?.invoke()
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        camera.viewportWidth = max(1, w).toFloat()
        camera.viewportHeight = max(1, h).toFloat()
        camera.clamp()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        canvas.drawColor(Color.rgb(18, 59, 66))
        val scene = world
        if (scene != null) {
            val now = SystemClock.uptimeMillis()
            val dt = if (lastFrame == 0L || !active) 0f else ((now - lastFrame) / 1000f).coerceAtMost(.05f)
            lastFrame = now
            if (playing) {
                elapsed += dt
                advance(scene, dt, now)
            }
            canvas.save()
            canvas.translate(camera.offsetX, camera.offsetY)
            canvas.scale(camera.scale, camera.scale)
            canvas.translate(-camera.x, -camera.y)
            canvas.clipRect(0f, 0f, scene.width, WorldCamera.WORLD_HEIGHT)
            drawScenery(canvas, scene.width)
            scene.animals.forEach { drawAnimal(canvas, it) }
            drawInteractions(canvas)
            canvas.restore()
        }
        if (active && isShown) postInvalidateOnAnimation()
    }

    private fun advance(scene: AnimalWorld, dt: Float, now: Long) {
        interactions.update(scene.animals, dt, scene.width)
        for (animal in scene.animals) {
            animal.animation.advance(dt * animal.speed, animal.width, animal.height, animal.direction, animal.social)
            val speed = animal.animation.pose.speed * animal.speed
            if (!animal.social) animal.x += animal.direction * speed * dt
            val margin = animal.width / 2 + 20
            if (animal.x < margin) { animal.x = margin; animal.direction = 1 }
            if (animal.x > scene.width - margin) { animal.x = scene.width - margin; animal.direction = -1 }
        }
        if (now >= manualUntil) {
            if (autoScroll) {
                camera.x += autoDirectionX * 90 * scene.horizontalSpeed * dt
                if (camera.x <= 0 || camera.x >= scene.width - camera.visibleWidth) autoDirectionX *= -1
            }
            if (verticalAutoScroll) {
                camera.y += autoDirectionY * 90 * scene.verticalSpeed * dt
                if (camera.y <= 0 || camera.y >= WorldCamera.WORLD_HEIGHT - camera.visibleHeight) autoDirectionY *= -1
            }
            camera.clamp()
        }
    }

    private fun fill(canvas: Canvas, color: Int, left: Float, top: Float, right: Float, bottom: Float) {
        paint.color = color
        canvas.drawRect(left, top, right, bottom, paint)
    }

    private fun oval(canvas: Canvas, color: Int, left: Float, top: Float, right: Float, bottom: Float) {
        paint.color = color
        rect.set(left, top, right, bottom)
        canvas.drawOval(rect, paint)
    }

    private fun drawScenery(canvas: Canvas, width: Float) {
        fill(canvas, Color.rgb(20, 120, 175), 0f, 0f, width, 700f)
        for (x in 0..width.toInt() step 220) {
            val offset = sin(elapsed * .5f + x) * 40
            path.reset()
            path.moveTo(x + offset, 0f)
            path.lineTo(x + 100 + offset, 0f)
            path.lineTo(x + 250f, 700f)
            path.close()
            paint.color = Color.argb(12, 255, 255, 255)
            canvas.drawPath(path, paint)
        }
        fill(canvas, Color.rgb(194, 166, 105), 0f, 630f, width, 700f)
        for (x in 100..width.toInt() step 325) {
            oval(canvas, Color.rgb(90, 90, 80), x.toFloat(), 600f, x + 100f, 650f)
        }
        paint.color = Color.rgb(30, 120, 50)
        paint.strokeWidth = 7f
        paint.strokeCap = Paint.Cap.ROUND
        for (x in 50..width.toInt() step 130) {
            canvas.drawLine(x.toFloat(), 630f, x + sin(elapsed * 2 + x) * 10,
                600f - ((x * 37) % 100), paint)
        }
        fill(canvas, Color.rgb(224, 201, 143), 0f, 700f, width, 800f)
        fill(canvas, Color.rgb(104, 164, 84), 0f, 800f, width, 1500f)
        for (x in -40..width.toInt() step 70) {
            val offset = sin(elapsed * 1.5f + x * .01f) * 4
            oval(canvas, Color.rgb(241, 232, 190), x.toFloat(), 692f + offset, x + 95f, 712f + offset)
            oval(canvas, Color.rgb(104, 164, 84), x.toFloat(), 788f, x + 95f, 813f)
        }
        for (x in 110..width.toInt() step 1000) {
            fill(canvas, Color.rgb(126, 87, 57), x - 12f, 1130f, x + 12f, 1320f)
            paint.color = Color.rgb(59, 131, 75)
            canvas.drawCircle(x.toFloat(), 1110f, 80f, paint)
            paint.color = Color.rgb(79, 150, 78)
            canvas.drawCircle(x - 35f, 1085f, 55f, paint)
        }
        for ((i, x) in (30..width.toInt() step 35).withIndex()) {
            for (band in 0..3) {
                val y = 830f + band * 170 + (i * 37) % 130
                paint.color = Color.rgb(65, 125, 60)
                paint.strokeWidth = 2f
                canvas.drawLine(x.toFloat(), y, x + 2f, y - 8, paint)
                paint.color = Color.rgb(255, 222, 135)
                canvas.drawCircle(x + 2f, y - 9, 3f, paint)
            }
        }
    }

    private fun drawAnimal(canvas: Canvas, animal: WorldAnimal) {
        val motion = animal.animation
        val pose = motion.pose
        val lower = animal.height / 2 + 5
        val upper = (if (animal.habitat == "mer" && !animal.isOnSand) 630f else 700f) - animal.height / 2
        val localY = (animal.y + pose.offsetY - animal.socialJump).coerceIn(lower, max(lower, upper))
        val y = localY + if (animal.habitat == "prairie") WorldCamera.LAND_Y else 0f
        if (animal.x + animal.width * 2 < camera.x || animal.x - animal.width * 2 > camera.x + camera.visibleWidth ||
            y + animal.height * 2 < camera.y || y - animal.height * 2 > camera.y + camera.visibleHeight) return
        canvas.save()
        canvas.translate(animal.x, y)
        val facing = if (abs(motion.facing) < .08f) (if (motion.facing < 0) -.08f else .08f) else motion.facing
        canvas.scale(-facing, 1f)
        val groundAnchor = animal.habitat == "prairie" && !animal.isBird || animal.isOnSand
        if (groundAnchor) canvas.translate(0f, animal.height / 2)
        canvas.rotate(pose.angle)
        canvas.scale(pose.scaleX, pose.scaleY)
        if (groundAnchor) canvas.translate(0f, -animal.height / 2)
        paint.color = Color.WHITE
        motion.fillMesh(animal.meshVertices, animal.width, animal.height, animal.headLeft)
        canvas.drawBitmapMesh(animal.image, BasicAnimation.COLUMNS, BasicAnimation.ROWS,
            animal.meshVertices, 0, null, 0, paint)
        canvas.restore()
    }

    private fun drawInteractions(canvas: Canvas) {
        paint.textSize = 22f
        paint.typeface = Typeface.DEFAULT_BOLD
        paint.textAlign = Paint.Align.CENTER
        for (pair in interactions.pairs) {
            val a = pair.a; val b = pair.b
            val x = (a.x + b.x) / 2
            val y = min(a.y - a.height / 2 - a.socialJump, b.y - b.height / 2 - b.socialJump) - 24 +
                if (pair.sea) 0f else WorldCamera.LAND_Y
            val half = paint.measureText(pair.label) / 2 + 12
            paint.color = Color.argb(210, 18, 59, 66)
            canvas.drawRoundRect(x - half, y - 25, x + half, y + 8, 8f, 8f, paint)
            paint.color = Color.rgb(255, 235, 185)
            canvas.drawText(pair.label, x, y, paint)
            if (pair.kind == "bisou" && pair.contact > 0) {
                val heartY = y - 48 - pair.contact * 20
                paint.color = Color.rgb(255, 100, 150)
                canvas.drawCircle(x - 5, heartY, 7f, paint)
                canvas.drawCircle(x + 5, heartY, 7f, paint)
                path.reset()
                path.moveTo(x - 11, heartY + 2); path.lineTo(x + 11, heartY + 2)
                path.lineTo(x, heartY + 15); path.close()
                canvas.drawPath(path, paint)
            }
        }
        paint.textAlign = Paint.Align.LEFT
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaler.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                parent.requestDisallowInterceptTouchEvent(true)
                pointerId = event.getPointerId(0)
                lastX = event.x; lastY = event.y
                downX = event.x; downY = event.y
                moved = false
                manualNavigation()
            }
            MotionEvent.ACTION_POINTER_DOWN -> moved = true
            MotionEvent.ACTION_MOVE -> {
                val index = event.findPointerIndex(pointerId)
                if (index >= 0) {
                    val x = event.getX(index); val y = event.getY(index)
                    if (abs(x - downX) + abs(y - downY) > slop) moved = true
                    if (!scaler.isInProgress && event.pointerCount == 1 && moved) {
                        camera.drag(x - lastX, y - lastY)
                        manualNavigation()
                    }
                    lastX = x; lastY = y
                }
            }
            MotionEvent.ACTION_POINTER_UP -> {
                val index = if (event.actionIndex == 0) 1 else 0
                pointerId = event.getPointerId(index)
                lastX = event.getX(index); lastY = event.getY(index)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                if (!moved && event.actionMasked == MotionEvent.ACTION_UP) performClick()
                pointerId = -1
                parent.requestDisallowInterceptTouchEvent(false)
                onCameraChanged?.invoke()
            }
        }
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
