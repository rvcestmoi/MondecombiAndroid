package fr.mondesdesanimaux.app

import android.content.Context
import android.graphics.*
import android.view.MotionEvent
import android.view.View
import kotlin.math.*

class ScanImageView(context: Context) : View(context) {
    var bitmap: Bitmap? = null
    var preview = false
    var mirrored = false
    var selection = RectF(.04f, .04f, .96f, .96f)
    var onCropChanged: ((RectF) -> Unit)? = null
    private val imageRect = RectF()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG)
    private val frame = RectF()
    private var mode = 0
    private var startX = 0f
    private var startY = 0f
    private var original = RectF()

    init {
        contentDescription = "Cadrage du dessin : déplace les quatre coins du cadre, ou trace un nouveau rectangle."
        isFocusable = true
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawColor(Color.rgb(27, 61, 66))
        val image = bitmap ?: return
        val margin = 12 * resources.displayMetrics.density
        val scale = min((width - 2 * margin) / image.width, (height - 2 * margin) / image.height)
        if (scale <= 0) return
        val w = image.width * scale; val h = image.height * scale
        imageRect.set((width - w) / 2, (height - h) / 2, (width + w) / 2, (height + h) / 2)
        canvas.save()
        canvas.clipRect(imageRect)
        val tile = max(8f, 14 * resources.displayMetrics.density)
        var row = 0
        var y = imageRect.top
        while (y < imageRect.bottom) {
            var col = 0
            var x = imageRect.left
            while (x < imageRect.right) {
                paint.color = if ((row + col) % 2 == 0) Color.rgb(230, 235, 233) else Color.rgb(192, 207, 203)
                canvas.drawRect(x, y, x + tile, y + tile, paint)
                col++; x += tile
            }
            row++; y += tile
        }
        if (preview && mirrored) canvas.scale(-1f, 1f, imageRect.centerX(), imageRect.centerY())
        paint.color = Color.WHITE
        canvas.drawBitmap(image, null, imageRect, paint)
        canvas.restore()
        if (!preview) {
            frame.set(imageRect.left + selection.left * w, imageRect.top + selection.top * h,
                imageRect.left + selection.right * w, imageRect.top + selection.bottom * h)
            paint.color = Color.argb(150, 0, 20, 25)
            canvas.drawRect(imageRect.left, imageRect.top, imageRect.right, frame.top, paint)
            canvas.drawRect(imageRect.left, frame.bottom, imageRect.right, imageRect.bottom, paint)
            canvas.drawRect(imageRect.left, frame.top, frame.left, frame.bottom, paint)
            canvas.drawRect(frame.right, frame.top, imageRect.right, frame.bottom, paint)
            paint.color = Color.rgb(255, 226, 151)
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = 2 * resources.displayMetrics.density
            canvas.drawRect(frame, paint)
            paint.style = Paint.Style.FILL
            for (x in listOf(frame.left, frame.right)) for (cy in listOf(frame.top, frame.bottom)) {
                canvas.drawCircle(x, cy, 7 * resources.displayMetrics.density, paint)
            }
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!isEnabled || preview || bitmap == null || imageRect.isEmpty) return false
        val x = ((event.x - imageRect.left) / imageRect.width()).coerceIn(0f, 1f)
        val y = ((event.y - imageRect.top) / imageRect.height()).coerceIn(0f, 1f)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                startX = x; startY = y; original = RectF(selection)
                val radius = 28 * resources.displayMetrics.density
                fun near(cx: Float, cy: Float) = hypot(event.x - cx, event.y - cy) <= radius
                mode = when {
                    near(frame.left, frame.top) -> 1
                    near(frame.right, frame.top) -> 2
                    near(frame.right, frame.bottom) -> 3
                    near(frame.left, frame.bottom) -> 4
                    selection.contains(x, y) -> 5
                    else -> 6
                }
                parent.requestDisallowInterceptTouchEvent(true)
            }
            MotionEvent.ACTION_MOVE -> {
                if (event.pointerCount != 1) return true
                val minimum = .04f
                when (mode) {
                    1 -> { selection.left = min(x, selection.right - minimum); selection.top = min(y, selection.bottom - minimum) }
                    2 -> { selection.right = max(x, selection.left + minimum); selection.top = min(y, selection.bottom - minimum) }
                    3 -> { selection.right = max(x, selection.left + minimum); selection.bottom = max(y, selection.top + minimum) }
                    4 -> { selection.left = min(x, selection.right - minimum); selection.bottom = max(y, selection.top + minimum) }
                    5 -> {
                        val dx = (x - startX).coerceIn(-original.left, 1 - original.right)
                        val dy = (y - startY).coerceIn(-original.top, 1 - original.bottom)
                        selection.set(original); selection.offset(dx, dy)
                    }
                    6 -> if (abs(x - startX) >= minimum && abs(y - startY) >= minimum) {
                        selection.set(min(x, startX), min(y, startY), max(x, startX), max(y, startY))
                    }
                }
                onCropChanged?.invoke(RectF(selection))
                invalidate()
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                parent.requestDisallowInterceptTouchEvent(false)
                if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
            }
        }
        return true
    }

    override fun performClick(): Boolean { super.performClick(); return true }
}
