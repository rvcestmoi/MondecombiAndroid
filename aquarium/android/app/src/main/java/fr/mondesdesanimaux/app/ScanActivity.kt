package fr.mondesdesanimaux.app

import android.app.Activity
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.Intent
import android.graphics.Color
import android.graphics.RectF
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.widget.*
import androidx.core.content.FileProvider

class ScanActivity : Activity() {
    private lateinit var model: ScanModel
    private lateinit var image: ScanImageView
    private lateinit var status: TextView
    private lateinit var cropTools: LinearLayout
    private lateinit var previewTools: LinearLayout
    private lateinit var sizeText: TextView
    private lateinit var toleranceText: TextView
    private lateinit var extract: Button
    private lateinit var add: Button
    private lateinit var rotate: Button
    private lateinit var overlay: FrameLayout
    private lateinit var orientationCheck: CheckBox
    private lateinit var headSide: Button
    private val controls = mutableListOf<View>()
    private var returning = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val worldId = intent.getStringExtra("worldId")
        if (worldId == null || !worldId.matches(Regex("[a-zA-Z0-9_-]+\\.zip"))) { finish(); return }
        @Suppress("DEPRECATION")
        val retained = lastNonConfigurationInstance as? ScanModel
        model = retained ?: ScanModel(applicationContext, worldId, savedInstanceState)
        if (retained == null && savedInstanceState == null) {
            model.speciesId = intent.getStringExtra("initialSpecies") ?: "poisson"
        }
        buildLayout()
        model.onChanged = { render() }
        if (Build.VERSION.SDK_INT >= 33) {
            onBackInvokedDispatcher.registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT) { cancelScan() }
        }
        render()
        if (retained == null) model.restore()
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun label(value: String, size: Float = 14f) = TextView(this).apply {
        text = value; textSize = size; setTextColor(Color.WHITE)
        setPadding(dp(12), dp(4), dp(12), dp(4))
    }
    private fun button(value: String, action: () -> Unit) = Button(this).apply {
        text = value; textSize = 12f; isAllCaps = false; minHeight = dp(48)
        setOnClickListener { if (!model.busy) action() }
        controls += this
    }
    private fun row() = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; setPadding(dp(8), 0, dp(8), 0) }
    private fun scrollingRow(root: LinearLayout, content: LinearLayout) {
        root.addView(HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; addView(content) })
    }

    private fun buildLayout() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(18, 59, 66))
            setOnApplyWindowInsetsListener { view, insets ->
                if (Build.VERSION.SDK_INT >= 30) {
                    val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                    view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
                } else {
                    @Suppress("DEPRECATION")
                    view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                        insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
                }
                insets
            }
        }
        root.addView(label("Ajouter un animal", 21f))
        scrollingRow(root, row().apply {
            addView(button("Prendre une photo") { camera() })
            addView(button("Choisir une image") { pickImage() })
            addView(button("Dessiner un animal") {
                model.waitingPaint = true
                @Suppress("DEPRECATION")
                startActivityForResult(Intent(this@ScanActivity, PaintActivity::class.java).putExtra("session", model.sessionId), PAINT)
            })
            rotate = button("Tourner ↻") { model.rotate() }
            addView(rotate)
            addView(button("Annuler") { cancelScan() })
        })
        val species = Spinner(this).apply {
            setBackgroundColor(Color.rgb(230, 240, 236))
            adapter = ArrayAdapter(this@ScanActivity, android.R.layout.simple_spinner_dropdown_item,
                AnimalSpecies.all.map { "${if (it.habitat == "mer") "Mer" else "Prairie"} · ${it.label}" })
            setSelection(AnimalSpecies.all.indexOfFirst { it.id == model.speciesId }.coerceAtLeast(0))
            onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
                override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                    model.speciesId = AnimalSpecies.all[position].id
                    if (::image.isInitialized) {
                        image.speciesId = model.speciesId
                        image.invalidate()
                    }
                }
                override fun onNothingSelected(parent: AdapterView<*>?) = Unit
            }
        }
        controls += species
        val properties = row()
        properties.addView(species, LinearLayout.LayoutParams(0, dp(48), 1f))
        sizeText = label("Taille ${model.sizePercent} %", 12f)
        properties.addView(sizeText)
        properties.addView(SeekBar(this).apply {
            max = 175; progress = model.sizePercent - 25
            contentDescription = "Taille de l’animal, de 25 à 200 pour cent"
            controls += this
            setOnSeekBarChangeListener(listener { value ->
                model.sizePercent = value + 25
                sizeText.text = getString(R.string.scan_size, model.sizePercent)
            })
        }, LinearLayout.LayoutParams(dp(110), dp(48)))
        root.addView(properties)
        status = label("", 13f)
        root.addView(status)

        val stage = FrameLayout(this)
        image = ScanImageView(this).apply { onCropChanged = { model.crop = it } }
        stage.addView(image, FrameLayout.LayoutParams(-1, -1))
        overlay = FrameLayout(this).apply {
            setBackgroundColor(Color.argb(210, 18, 59, 66)); isClickable = true
            addView(ProgressBar(this@ScanActivity), FrameLayout.LayoutParams(dp(48), dp(48), Gravity.CENTER))
        }
        stage.addView(overlay, FrameLayout.LayoutParams(-1, -1))
        root.addView(stage, LinearLayout.LayoutParams(-1, 0, 1f))

        cropTools = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val tuning = row()
        toleranceText = label("Détourage ${model.tolerance}", 12f)
        tuning.addView(toleranceText)
        tuning.addView(SeekBar(this).apply {
            max = 90; progress = model.tolerance - 10
            contentDescription = "Force du détourage : augmenter pour retirer davantage de papier"
            controls += this
            setOnSeekBarChangeListener(listener {
                model.tolerance = it + 10
                toleranceText.text = getString(R.string.scan_tolerance, model.tolerance)
            })
        }, LinearLayout.LayoutParams(0, dp(48), 1f))
        cropTools.addView(tuning)
        headSide = button("Tête à gauche ⇄") {
            model.mirrored = !model.mirrored
            render()
        }
        cropTools.addView(headSide)
        cropTools.addView(row().apply {
            addView(button("Cadre entier") {
                model.crop = RectF(0f, 0f, 1f, 1f); render()
            })
            extract = button("Détourer le dessin") { model.extract() }
            addView(extract, LinearLayout.LayoutParams(0, dp(52), 1f))
        })
        root.addView(cropTools)
        previewTools = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        orientationCheck = CheckBox(this).apply {
            text = "Mon dessin regarde vers la droite (inverser)"
            setTextColor(Color.WHITE)
            isChecked = model.mirrored
            controls += this
            setOnCheckedChangeListener { _, checked -> model.mirrored = checked; image.mirrored = checked; image.invalidate() }
        }
        previewTools.addView(orientationCheck)
        previewTools.addView(CheckBox(this).apply {
            text = "Aperçu animé"
            setTextColor(Color.WHITE)
            isChecked = true
            controls += this
            setOnCheckedChangeListener { _, checked -> image.animated = checked; image.invalidate() }
        })
        previewTools.addView(row().apply {
            addView(button("Revoir le cadre") { model.recrop() })
            add = button("Ajouter au monde") { model.add(intent.getFloatExtra("worldX", 600f)) }
            addView(add, LinearLayout.LayoutParams(0, dp(52), 1f))
        })
        root.addView(previewTools)
        setContentView(root)
        root.requestApplyInsets()
    }

    private fun listener(onProgress: (Int) -> Unit) = object : SeekBar.OnSeekBarChangeListener {
        override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) { if (fromUser) onProgress(progress) }
        override fun onStartTrackingTouch(seekBar: SeekBar?) = Unit
        override fun onStopTrackingTouch(seekBar: SeekBar?) = Unit
    }

    private fun render() {
        if (isDestroyed) return
        if (model.saved && !returning) {
            returning = true
            setResult(RESULT_OK, Intent().putExtra("worldId", model.worldId)
                .putExtra("habitat", AnimalSpecies.find(model.speciesId).habitat))
            finish()
            return
        }
        val preview = model.cutout != null
        image.bitmap = model.cutout ?: model.source
        image.preview = preview
        image.speciesId = model.speciesId
        image.mirrored = model.mirrored
        orientationCheck.isChecked = model.mirrored
        headSide.text = getString(if (model.mirrored) R.string.scan_head_right else R.string.scan_head_left)
        image.contentDescription = getString(if (!preview && model.mirrored) R.string.scan_head_right_hint else R.string.scan_head_left_hint)
        image.selection = RectF(model.crop)
        image.isEnabled = !model.busy
        image.invalidate()
        controls.forEach { it.isEnabled = !model.busy }
        rotate.isEnabled = !model.busy && model.source != null
        extract.isEnabled = !model.busy && model.source != null
        add.isEnabled = !model.busy && preview
        overlay.visibility = if (model.busy) View.VISIBLE else View.GONE
        cropTools.visibility = if (!preview && model.source != null) View.VISIBLE else View.GONE
        previewTools.visibility = if (preview) View.VISIBLE else View.GONE
        status.setTextColor(if (model.error != null) Color.rgb(255, 210, 160) else Color.WHITE)
        status.text = model.error ?: when {
            model.busy -> "Traitement en cours…"
            preview -> "Aperçu de l’espèce choisie, tête à gauche. Décoche « Aperçu animé » pour vérifier le détourage."
            model.source != null -> "Place la tête du côté du repère TÊTE. Change le côté avec le bouton ⇄. Garde une marge de papier autour du dessin."
            else -> "Photographie un dessin sur papier clair, bien éclairé, ou choisis une image."
        }
    }

    @Suppress("DEPRECATION")
    private fun camera() {
        model.cameraFile.delete()
        val uri = FileProvider.getUriForFile(this, "$packageName.scanfiles", model.cameraFile)
        val request = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, uri)
            clipData = ClipData.newRawUri("Photo du dessin", uri)
            addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        model.waitingCamera = true
        try { startActivityForResult(request, CAMERA) }
        catch (_: ActivityNotFoundException) {
            model.waitingCamera = false
            model.error = "Aucune application appareil photo disponible. Utilise Choisir une image."
            render()
        } catch (_: SecurityException) {
            model.waitingCamera = false
            model.error = "L’appareil photo n’est pas accessible. Utilise Choisir une image."
            render()
        }
    }

    @Suppress("DEPRECATION")
    private fun pickImage() {
        model.waitingPhoto = true
        try {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE); type = "image/*"
            }, PHOTO)
        } catch (_: ActivityNotFoundException) {
            model.waitingPhoto = false
            model.error = "Aucun sélecteur d’images disponible sur cet appareil."; render()
        }
    }

    @Deprecated("Platform result API")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == PAINT) {
            model.waitingPaint = false
            if (resultCode == RESULT_OK) model.takePaintResult() else model.restore()
        } else if (requestCode == CAMERA) {
            model.waitingCamera = false
            val uri = FileProvider.getUriForFile(this, "$packageName.scanfiles", model.cameraFile)
            revokeUriPermission(uri, Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION)
            if (resultCode == RESULT_OK) model.takePhotoResult() else model.restore()
        } else if (requestCode == PHOTO) {
            model.waitingPhoto = false
            val uri = data?.data
            if (resultCode == RESULT_OK && uri != null) model.importPhoto(uri) else model.restore()
        }
    }

    private fun cancelScan() {
        if (model.busy) return
        if (model.source == null) { finish(); return }
        AlertDialog.Builder(this).setTitle("Annuler ce scan ?")
            .setMessage("Le dessin n’a pas encore été ajouté au monde.")
            .setPositiveButton("Abandonner") { _, _ -> finish() }
            .setNegativeButton("Continuer", null).show()
    }

    @Deprecated("Uses onBackInvokedDispatcher on newer Android")
    @android.annotation.SuppressLint("GestureBackNavigation") // API 26–32 fallback; API 33+ is registered in onCreate.
    override fun onBackPressed() { cancelScan() }

    @Deprecated("Retain only the model, never an activity or view")
    override fun onRetainNonConfigurationInstance(): Any = model

    override fun onSaveInstanceState(outState: Bundle) {
        model.saveState(outState)
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        if (::model.isInitialized) {
            model.onChanged = null
            if (isFinishing) model.close()
        }
        super.onDestroy()
    }

    companion object { private const val CAMERA = 10; private const val PHOTO = 11; private const val PAINT = 12 }
}
