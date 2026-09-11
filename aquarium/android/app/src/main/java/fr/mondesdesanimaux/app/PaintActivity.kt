package fr.mondesdesanimaux.app

import android.app.Activity
import android.app.AlertDialog
import android.graphics.*
import android.os.Bundle
import android.util.AtomicFile
import android.view.MotionEvent
import android.view.View
import android.widget.*
import java.io.File
import kotlin.math.*

class PaintActivity : Activity() {
    private lateinit var drawing: PaintDrawing
    private lateinit var board: DrawingView
    private lateinit var folder: File
    private lateinit var toolLabel: TextView

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val session = intent.getStringExtra("session")
        if (session == null || !session.matches(Regex("[a-f0-9-]{36}"))) { finish(); return }
        folder = File(filesDir, "scan/$session").apply { mkdirs() }
        val draft = AtomicFile(File(folder, "paint.json"))
        drawing = try { draft.openRead().bufferedReader().use { PaintDrawing.restore(it.readText()) } }
            catch (_: java.io.FileNotFoundException) { PaintDrawing() }
            catch (_: Exception) {
                Toast.makeText(this, "Le brouillon n’a pas pu être restauré.", Toast.LENGTH_LONG).show()
                PaintDrawing()
            }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(230, 240, 236))
            setOnApplyWindowInsetsListener { view, insets ->
                if (android.os.Build.VERSION.SDK_INT >= 30) {
                    val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.displayCutout())
                    view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
                } else {
                    @Suppress("DEPRECATION")
                    view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
                }
                insets
            }
        }
        root.addView(TextView(this).apply {
            text = "Dessine ton animal · tête à gauche ←\nColorie aussi l’intérieur. Le damier restera transparent."
            textSize = 16f; setPadding(dp(12), dp(8), dp(12), dp(8))
        })
        fun row(build: LinearLayout.() -> Unit) {
            root.addView(HorizontalScrollView(this).apply { addView(LinearLayout(this@PaintActivity).apply(build)) })
        }
        row {
            for ((name, color) in listOf("Noir" to Color.BLACK, "Blanc" to Color.WHITE, "Rouge" to Color.RED,
                "Orange" to 0xFFFF8800.toInt(), "Jaune" to Color.YELLOW, "Vert" to 0xFF228844.toInt(),
                "Bleu" to Color.BLUE, "Rose" to 0xFFFF66AA.toInt(), "Marron" to 0xFF885533.toInt())) {
                addView(button(name) { drawing.color = color; drawing.eraser = false; updateTool() }.apply { setTextColor(if (color == Color.WHITE || color == Color.YELLOW) Color.DKGRAY else color) })
            }
        }
        toolLabel = TextView(this).apply { setPadding(dp(12), 0, dp(12), 0) }
        root.addView(toolLabel)
        root.addView(SeekBar(this).apply {
            max = 78; progress = drawing.brushWidth.toInt() - 2
            contentDescription = "Épaisseur du pinceau"
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(bar: SeekBar?, value: Int, user: Boolean) {
                    if (user) { drawing.brushWidth = value + 2f; updateTool() }
                }
                override fun onStartTrackingTouch(bar: SeekBar?) = Unit
                override fun onStopTrackingTouch(bar: SeekBar?) = Unit
            })
        })
        row {
            addView(button("Gomme") { drawing.eraser = !drawing.eraser; updateTool() })
            addView(button("Annuler le trait") { if (drawing.strokes.isNotEmpty()) drawing.strokes.removeAt(drawing.strokes.lastIndex); board.invalidate() })
            addView(button("Tout effacer") {
                AlertDialog.Builder(this@PaintActivity).setTitle("Effacer le dessin ?")
                    .setPositiveButton("Effacer") { _, _ -> drawing.strokes.clear(); board.invalidate() }
                    .setNegativeButton("Annuler", null).show()
            })
        }
        board = DrawingView()
        root.addView(board, LinearLayout.LayoutParams(-1, 0, 1f))
        row {
            addView(button("Retour") { finish() })
            addView(button("Utiliser ce dessin") { accept() })
        }
        setContentView(root)
        updateTool()
        root.requestApplyInsets()
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun button(text: String, action: () -> Unit) = Button(this).apply {
        this.text = text; isAllCaps = false; minHeight = dp(48); setOnClickListener { action() }
    }
    private fun updateTool() {
        toolLabel.text = "${if (drawing.eraser) "Gomme" else "Pinceau"} · épaisseur ${drawing.brushWidth.toInt()}"
        toolLabel.setTextColor(if (drawing.eraser || drawing.color == Color.WHITE || drawing.color == Color.YELLOW) Color.DKGRAY else drawing.color)
    }
    private fun accept() {
        try {
            val bitmap = drawing.export()
            try {
                val file = AtomicFile(File(folder, "paint.png"))
                val output = file.startWrite()
                try {
                    check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)) { "Enregistrement impossible." }
                    file.finishWrite(output)
                } catch (e: Exception) { file.failWrite(output); throw e }
            } finally { bitmap.recycle() }
            setResult(RESULT_OK); finish()
        } catch (e: Exception) {
            AlertDialog.Builder(this).setMessage(e.localizedMessage).setPositiveButton("Fermer", null).show()
        }
    }
    override fun onPause() {
        if (::drawing.isInitialized) {
            try {
                val file = AtomicFile(File(folder, "paint.json")); val output = file.startWrite()
                try { output.write(drawing.serialize().toByteArray(Charsets.UTF_8)); file.finishWrite(output) }
                catch (e: Exception) { file.failWrite(output); throw e }
            } catch (_: Exception) { Toast.makeText(this, "Impossible de conserver le brouillon.", Toast.LENGTH_LONG).show() }
        }
        super.onPause()
    }

    private inner class DrawingView : View(this@PaintActivity) {
        private val bounds = RectF()
        private val paint = Paint()
        private var stroke: PaintDrawing.Stroke? = null
        private var pointCount = 0
        override fun onDraw(canvas: Canvas) {
            val side = min(width, height).toFloat()
            bounds.set((width - side) / 2, (height - side) / 2, (width + side) / 2, (height + side) / 2)
            canvas.drawColor(Color.rgb(180, 198, 193))
            canvas.save(); canvas.clipRect(bounds)
            canvas.translate(bounds.left, bounds.top)
            canvas.scale(side / PaintDrawing.SIZE, side / PaintDrawing.SIZE)
            for (y in 0 until PaintDrawing.SIZE step 32) for (x in 0 until PaintDrawing.SIZE step 32) {
                paint.color = if ((x / 32 + y / 32) % 2 == 0) Color.WHITE else Color.rgb(220, 225, 222)
                canvas.drawRect(x.toFloat(), y.toFloat(), x + 32f, y + 32f, paint)
            }
            // Erase only drawing pixels, never the checkerboard beneath them.
            canvas.saveLayer(0f, 0f, 1024f, 1024f, null)
            drawing.render(canvas)
            canvas.restore(); canvas.restore()
        }
        override fun onTouchEvent(event: MotionEvent): Boolean {
            if (bounds.isEmpty) return false
            fun point(x: Float, y: Float) = PointF(((x - bounds.left) / bounds.width() * 1024).coerceIn(0f, 1024f),
                ((y - bounds.top) / bounds.height() * 1024).coerceIn(0f, 1024f))
            when (event.actionMasked) {
                MotionEvent.ACTION_DOWN -> {
                    if (!bounds.contains(event.x, event.y)) return false
                    pointCount = drawing.strokes.sumOf { it.points.size }
                    if (pointCount >= PaintDrawing.MAX_POINTS) {
                        Toast.makeText(context, "Dessin plein : annule quelques traits pour continuer.", Toast.LENGTH_SHORT).show()
                        return false
                    }
                    stroke = PaintDrawing.Stroke(drawing.color, drawing.brushWidth, drawing.eraser, mutableListOf(point(event.x, event.y)))
                    drawing.strokes += stroke!!; pointCount++
                    parent.requestDisallowInterceptTouchEvent(true)
                }
                MotionEvent.ACTION_MOVE -> if (event.pointerCount == 1 && pointCount < PaintDrawing.MAX_POINTS) {
                    stroke?.points?.add(point(event.x, event.y)); pointCount++
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    stroke = null; parent.requestDisallowInterceptTouchEvent(false)
                    if (event.actionMasked == MotionEvent.ACTION_UP) performClick()
                }
            }
            invalidate(); return true
        }
        override fun performClick(): Boolean { super.performClick(); return true }
    }
}
