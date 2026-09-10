package fr.mondesdesanimaux.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.RectF
import androidx.exifinterface.media.ExifInterface
import java.io.File
import kotlin.math.*

/** Offline paper removal. Only paper connected to the crop border is removed:
 * enclosed white areas (eyes, belly, etc.) remain opaque. */
object DrawingScan {
    fun decodePhoto(file: File): Bitmap {
        require(file.length() in 1..32L * 1024 * 1024) { "Photo vide ou supérieure à 32 Mo." }
        val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true; inSampleSize = 1 }
        BitmapFactory.decodeFile(file.path, opts)
        require(opts.outWidth in 1..20000 && opts.outHeight in 1..20000 &&
            opts.outWidth.toLong() * opts.outHeight <= 120_000_000) { "Format ou dimensions de photo non pris en charge." }
        while (max(opts.outWidth, opts.outHeight) / opts.inSampleSize > 1600) opts.inSampleSize *= 2
        opts.inJustDecodeBounds = false
        opts.inPreferredConfig = Bitmap.Config.ARGB_8888
        val decoded = requireNotNull(BitmapFactory.decodeFile(file.path, opts)) { "Photo illisible." }
        val orientation = try {
            ExifInterface(file).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        } catch (_: java.io.IOException) { ExifInterface.ORIENTATION_NORMAL }
        val matrix = orientationMatrix(orientation)
        val oriented = Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, matrix, true)
        if (oriented !== decoded) decoded.recycle()
        val ratio = min(1f, 1200f / max(oriented.width, oriented.height))
        val resized = Bitmap.createScaledBitmap(oriented, max(1, (oriented.width * ratio).roundToInt()),
            max(1, (oriented.height * ratio).roundToInt()), true)
        if (resized !== oriented) oriented.recycle()
        return resized
    }

    internal fun orientationMatrix(orientation: Int) = Matrix().apply {
        when (orientation) {
            ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> setScale(-1f, 1f)
            ExifInterface.ORIENTATION_ROTATE_180 -> setRotate(180f)
            ExifInterface.ORIENTATION_FLIP_VERTICAL -> setScale(1f, -1f)
            ExifInterface.ORIENTATION_TRANSPOSE -> { setRotate(90f); postScale(-1f, 1f) }
            ExifInterface.ORIENTATION_ROTATE_90 -> setRotate(90f)
            ExifInterface.ORIENTATION_TRANSVERSE -> { setRotate(-90f); postScale(-1f, 1f) }
            ExifInterface.ORIENTATION_ROTATE_270 -> setRotate(-90f)
        }
    }

    fun extract(source: Bitmap, crop: RectF, tolerance: Int): Bitmap {
        require(listOf(crop.left, crop.top, crop.right, crop.bottom).all { it.isFinite() }) { "Cadrage invalide." }
        val left = (crop.left.coerceIn(0f, 1f) * source.width).toInt()
        val top = (crop.top.coerceIn(0f, 1f) * source.height).toInt()
        val right = (crop.right.coerceIn(0f, 1f) * source.width).toInt()
        val bottom = (crop.bottom.coerceIn(0f, 1f) * source.height).toInt()
        val w = right - left; val h = bottom - top
        require(w >= 12 && h >= 12) { "Trace un cadre plus grand autour du dessin." }
        require(w.toLong() * h <= 2_560_000) { "Photo trop grande : reprends une photo." }
        val pixels = IntArray(w * h)
        source.getPixels(pixels, 0, w, left, top, w, h)
        val n = pixels.size
        val outside = BooleanArray(n)
        // Transparent PNGs are already cut out; retain their original alpha.
        val transparent = pixels.count { Color.alpha(it) < 10 }
        if (transparent > n / 100) {
            for (i in pixels.indices) outside[i] = Color.alpha(pixels[i]) < 10
        } else {
            val border = ArrayList<Int>()
            for (x in 0 until w) { border += pixels[x]; border += pixels[(h - 1) * w + x] }
            for (y in 1 until h - 1) { border += pixels[y * w]; border += pixels[y * w + w - 1] }
            fun median(channel: (Int) -> Int) = border.map(channel).sorted()[border.size / 2].toFloat()
            val r = median(Color::red); val g = median(Color::green); val b = median(Color::blue)
            val light = (r + g + b) / 3
            require(light >= 100) { "Utilise une feuille claire et garde une marge de papier autour du dessin." }
            val threshold = tolerance.coerceIn(10, 100)
            val paper = BooleanArray(n) { i ->
                val p = pixels[i]
                val pr = Color.red(p).toFloat(); val pg = Color.green(p).toFloat(); val pb = Color.blue(p).toFloat()
                val chroma = max(abs((pr - pg) - (r - g)), abs((pb - pg) - (b - g)))
                Color.alpha(p) < 10 || (abs((pr + pg + pb) / 3 - light) < threshold && chroma < threshold * .65f)
            }
            val silhouette = closeOutline(paper, w, h)
            val queue = IntArray(n)
            var head = 0; var tail = 0
            fun push(i: Int) {
                if (!outside[i] && !silhouette[i]) { outside[i] = true; queue[tail++] = i }
            }
            for (x in 0 until w) { push(x); push((h - 1) * w + x) }
            for (y in 0 until h) { push(y * w); push(y * w + w - 1) }
            while (head < tail) {
                val i = queue[head++]; val x = i % w
                if (x > 0) push(i - 1)
                if (x < w - 1) push(i + 1)
                if (i >= w) push(i - w)
                if (i < n - w) push(i + w)
            }
            require(tail > n / 100) { "Fond non détecté : recadre avec une marge de papier clair ou ajuste le détourage." }
        }
        // Select the main connected drawing, ignoring specks on the paper.
        val visited = outside.copyOf()
        val queue = IntArray(n)
        var largest = IntArray(0)
        for (start in 0 until n) {
            if (visited[start]) continue
            var head = 0; var tail = 1
            queue[0] = start; visited[start] = true
            fun push(i: Int) { if (!visited[i]) { visited[i] = true; queue[tail++] = i } }
            while (head < tail) {
                val i = queue[head++]; val x = i % w
                if (x > 0) push(i - 1)
                if (x < w - 1) push(i + 1)
                if (i >= w) push(i - w)
                if (i < n - w) push(i + w)
            }
            if (tail > largest.size) largest = queue.copyOf(tail)
        }
        require(largest.size >= max(12, n / 1000)) { "Aucun dessin détecté. Resserre le cadre ou réduis le détourage." }
        val kept = BooleanArray(n)
        var minX = w; var minY = h; var maxX = 0; var maxY = 0
        for (i in largest) {
            kept[i] = true
            minX = min(minX, i % w); maxX = max(maxX, i % w)
            minY = min(minY, i / w); maxY = max(maxY, i / w)
        }
        for (i in pixels.indices) if (!kept[i]) pixels[i] = Color.TRANSPARENT
        minX = max(0, minX - 2); minY = max(0, minY - 2)
        maxX = min(w - 1, maxX + 2); maxY = min(h - 1, maxY + 2)
        val trimmed = Bitmap.createBitmap(pixels, minY * w + minX, w, maxX - minX + 1, maxY - minY + 1, Bitmap.Config.ARGB_8888)
        val scale = min(1f, 1024f / max(trimmed.width, trimmed.height))
        val result = Bitmap.createScaledBitmap(trimmed, max(1, (trimmed.width * scale).roundToInt()),
            max(1, (trimmed.height * scale).roundToInt()), true)
        if (result !== trimmed) trimmed.recycle()
        return result
    }

    /** Close short breaks in the ink mask, then flood only the outside of the
     * resulting silhouette. Work on the mask, never on the original RGB pixels. */
    private fun closeOutline(paper: BooleanArray, width: Int, height: Int): BooleanArray {
        val ink = BooleanArray(paper.size) { !paper[it] }
        // Scale with the photograph: a single pixel was insufficient for camera
        // noise, pencil strokes, and small gaps in a hand-drawn outline.
        val radius = max(2, ceil(min(width, height) * .012).toInt()).coerceAtMost(16)
        var closed = lineFilter(ink, width, height, radius, horizontal = true, dilate = true)
        closed = lineFilter(closed, width, height, radius, horizontal = false, dilate = true)
        closed = lineFilter(closed, width, height, radius, horizontal = true, dilate = false)
        closed = lineFilter(closed, width, height, radius, horizontal = false, dilate = false)
        for (i in ink.indices) closed[i] = closed[i] || ink[i]

        // If the crop cuts through the animal, two ink strokes can terminate on
        // its edge. Seal the intervening boundary so it is not seeded as paper.
        // This retains the photographed interior without inventing pixels beyond
        // the frame. Large openings away from the frame remain background.
        fun sealEdge(start: Int, step: Int, length: Int) {
            var first = -1; var last = -1
            for (p in 0 until length) if (ink[start + p * step]) {
                if (first == -1) first = p
                last = p
            }
            if (first >= 0 && last > first) for (p in first..last) closed[start + p * step] = true
        }
        sealEdge(0, 1, width)
        sealEdge((height - 1) * width, 1, width)
        sealEdge(0, width, height)
        sealEdge(width - 1, width, height)
        return closed
    }

    /** Separable sliding-window dilation/erosion: linear time, even for large scans. */
    private fun lineFilter(mask: BooleanArray, width: Int, height: Int, radius: Int,
                           horizontal: Boolean, dilate: Boolean): BooleanArray {
        val result = BooleanArray(mask.size)
        val length = if (horizontal) width else height
        val lines = if (horizontal) height else width
        val step = if (horizontal) 1 else width
        for (line in 0 until lines) {
            val start = if (horizontal) line * width else line
            var count = 0
            for (p in 0..min(radius, length - 1)) if (mask[start + p * step]) count++
            for (p in 0 until length) {
                val windowSize = min(length - 1, p + radius) - max(0, p - radius) + 1
                result[start + p * step] = if (dilate) count > 0 else count == windowSize
                val leaving = p - radius
                val entering = p + radius + 1
                if (leaving >= 0 && mask[start + leaving * step]) count--
                if (entering < length && mask[start + entering * step]) count++
            }
        }
        return result
    }
}
