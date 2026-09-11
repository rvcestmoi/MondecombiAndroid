package fr.mondesdesanimaux.app

import android.graphics.*
import org.json.JSONArray
import org.json.JSONObject

/** Vector strokes are the editable draft; only the final transparent PNG enters the world. */
class PaintDrawing {
    class Stroke(val color: Int, val width: Float, val erase: Boolean, val points: MutableList<PointF>)
    val strokes = mutableListOf<Stroke>()
    var color = Color.BLACK
    var brushWidth = 16f
    var eraser = false
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeCap = Paint.Cap.ROUND; strokeJoin = Paint.Join.ROUND }

    fun render(canvas: Canvas) {
        for (stroke in strokes) {
            paint.color = stroke.color
            paint.strokeWidth = stroke.width
            paint.xfermode = if (stroke.erase) PorterDuffXfermode(PorterDuff.Mode.CLEAR) else null
            paint.style = Paint.Style.FILL
            val first = stroke.points.firstOrNull() ?: continue
            canvas.drawCircle(first.x, first.y, stroke.width / 2, paint)
            paint.style = Paint.Style.STROKE
            val path = Path().apply {
                moveTo(first.x, first.y)
                stroke.points.drop(1).forEach { lineTo(it.x, it.y) }
            }
            canvas.drawPath(path, paint)
        }
        paint.xfermode = null
    }

    fun export(): Bitmap {
        val bitmap = Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888)
        render(Canvas(bitmap))
        val pixels = IntArray(SIZE * SIZE)
        bitmap.getPixels(pixels, 0, SIZE, 0, 0, SIZE, SIZE)
        var left = SIZE; var top = SIZE; var right = -1; var bottom = -1
        for (i in pixels.indices) if (Color.alpha(pixels[i]) > 0) {
            val x = i % SIZE; val y = i / SIZE
            left = minOf(left, x); right = maxOf(right, x)
            top = minOf(top, y); bottom = maxOf(bottom, y)
        }
        if (right < left) { bitmap.recycle(); error("Dessine ton animal avant de continuer.") }
        left = maxOf(0, left - 2); top = maxOf(0, top - 2)
        right = minOf(SIZE - 1, right + 2); bottom = minOf(SIZE - 1, bottom + 2)
        val trimmed = Bitmap.createBitmap(bitmap, left, top, right - left + 1, bottom - top + 1)
        if (trimmed !== bitmap) bitmap.recycle()
        return trimmed
    }

    fun serialize(): String {
        val records = JSONArray()
        strokes.forEach { stroke ->
            val points = JSONArray()
            stroke.points.forEach { points.put(it.x.toDouble()); points.put(it.y.toDouble()) }
            records.put(JSONObject().put("color", stroke.color).put("width", stroke.width)
                .put("erase", stroke.erase).put("points", points))
        }
        return JSONObject().put("color", color).put("width", brushWidth).put("eraser", eraser).put("strokes", records).toString()
    }

    companion object {
        const val SIZE = 1024
        const val MAX_POINTS = 30000
        fun restore(text: String): PaintDrawing {
            val json = JSONObject(text)
            return PaintDrawing().apply {
                color = json.getInt("color"); brushWidth = json.getDouble("width").toFloat().coerceIn(2f, 80f)
                eraser = json.getBoolean("eraser")
                val records = json.getJSONArray("strokes")
                require(records.length() <= MAX_POINTS)
                var count = 0
                for (i in 0 until records.length()) {
                    val record = records.getJSONObject(i)
                    val points = record.getJSONArray("points")
                    require(points.length() % 2 == 0)
                    count += points.length() / 2
                    require(count <= MAX_POINTS)
                    val list = mutableListOf<PointF>()
                    for (j in 0 until points.length() step 2) {
                        val x = points.getDouble(j).toFloat(); val y = points.getDouble(j + 1).toFloat()
                        require(x.isFinite() && y.isFinite())
                        list += PointF(x.coerceIn(0f, SIZE.toFloat()), y.coerceIn(0f, SIZE.toFloat()))
                    }
                    strokes += Stroke(record.getInt("color"), record.getDouble("width").toFloat().coerceIn(2f, 80f), record.getBoolean("erase"), list)
                }
            }
        }
    }
}
