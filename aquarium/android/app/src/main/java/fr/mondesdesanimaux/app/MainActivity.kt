package fr.mondesdesanimaux.app

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.WindowInsets
import android.widget.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private lateinit var scene: WorldView
    private lateinit var title: TextView
    private lateinit var detail: TextView
    private lateinit var zoomLabel: TextView
    private lateinit var pauseButton: Button
    private lateinit var progress: LinearLayout
    private val loader = Executors.newSingleThreadExecutor()
    private val prefs by lazy { getSharedPreferences("worlds", MODE_PRIVATE) }
    private var currentId = ""
    private var busy = false
    private var resumed = false
    private var pendingScanId: String? = null
    private var pendingScanHabitat: String? = null
    private var reloadAfterScan = false
    private data class Entry(val id: String, val name: String)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pendingScanId = savedInstanceState?.getString("pendingScanId")
        pendingScanHabitat = savedInstanceState?.getString("pendingScanHabitat")
        buildLayout()
        val catalog = catalog()
        val remembered = pendingScanId ?: prefs.getString("current", null)
        val defaultId = bundledIndex().optString("default")
        val initial = catalog.firstOrNull { it.id == remembered }
            ?: catalog.firstOrNull { it.id == defaultId } ?: catalog.firstOrNull()
        if (initial != null) load(initial) else {
            setBusy(false)
            detail.setText(R.string.empty_library)
        }
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
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(10), dp(18), dp(2))
        }
        title = text("Les mondes des animaux", 20f).apply {
            setTypeface(typeface, android.graphics.Typeface.BOLD)
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
        }
        detail = text("Ouverture de ton monde…", 12f).apply { setTextColor(Color.rgb(175, 213, 207)) }
        header.addView(title)
        header.addView(detail)
        root.addView(header)

        val actions = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL; setPadding(dp(8), 0, dp(8), 0) }
        actions.addView(button("Nouveau monde") { showNewWorld() })
        actions.addView(button("Ajouter un animal") { scanAnimal() })
        actions.addView(button("Mes mondes") { showLibrary() })
        actions.addView(button("Mer") { scene.camera.centerOn(350f); scene.manualNavigation() })
        actions.addView(button("Plage") { scene.camera.centerOn(750f); scene.manualNavigation() })
        actions.addView(button("Prairie") { scene.camera.centerOn(1200f); scene.manualNavigation() })
        pauseButton = button("Pause") {
            scene.playing = !scene.playing
            updateLabels()
        }
        actions.addView(pauseButton)
        actions.addView(button("Options") { showOptions(it) })
        root.addView(HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = false
            addView(actions)
        })

        val stage = FrameLayout(this)
        scene = WorldView(this).apply { onCameraChanged = { updateLabels() } }
        stage.addView(scene, FrameLayout.LayoutParams(-1, -1))
        progress = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.rgb(18, 59, 66))
            isClickable = true
            addView(ProgressBar(this@MainActivity), LinearLayout.LayoutParams(dp(44), dp(44)))
            addView(text("Chargement du monde…", 16f).apply { setPadding(0, dp(16), 0, 0) })
        }
        stage.addView(progress, FrameLayout.LayoutParams(-1, -1))
        root.addView(stage, LinearLayout.LayoutParams(-1, 0, 1f))

        val footer = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), 0, dp(6), 0)
        }
        footer.addView(text("Glisse pour explorer\nPince pour zoomer", 11f), LinearLayout.LayoutParams(0, -2, 1f))
        footer.addView(button("−") {
            scene.camera.zoomAt(1 / 1.15f, scene.width / 2f, scene.height / 2f)
            scene.manualNavigation()
        }.apply { contentDescription = "Réduire le zoom" })
        zoomLabel = text("100 %", 12f)
        footer.addView(zoomLabel)
        footer.addView(button("+") {
            scene.camera.zoomAt(1.15f, scene.width / 2f, scene.height / 2f)
            scene.manualNavigation()
        }.apply { contentDescription = "Augmenter le zoom" })
        root.addView(footer)
        setContentView(root)
        root.requestApplyInsets()
    }

    private fun text(value: String, size: Float) = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(Color.WHITE)
    }

    private fun button(value: String, action: (View) -> Unit) = Button(this).apply {
        text = value
        textSize = 12f
        isAllCaps = false
        minWidth = dp(48)
        minimumWidth = dp(48)
        minHeight = dp(48)
        setTextColor(Color.rgb(18, 59, 66))
        setOnClickListener { if (!busy) action(it) }
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun updateLabels() {
        if (!::zoomLabel.isInitialized) return
        zoomLabel.text = getString(R.string.zoom_value, (scene.camera.zoom * 100).toInt())
        pauseButton.text = if (scene.playing) "Pause" else "Reprendre"
    }

    private fun bundledIndex(): JSONObject = try {
        JSONObject(assets.open("worlds/index.json").bufferedReader().use { it.readText() })
    } catch (_: java.io.IOException) {
        JSONObject()
    }

    private fun catalog(): List<Entry> {
        val result = mutableListOf<Entry>()
        val bundled = bundledIndex().optJSONArray("worlds") ?: JSONArray()
        for (i in 0 until bundled.length()) {
            val item = bundled.getJSONObject(i)
            result += Entry(item.getString("file"), item.getString("name"))
        }
        val imported = JSONArray(prefs.getString("imports", "[]"))
        for (i in 0 until imported.length()) {
            val item = imported.getJSONObject(i)
            val id = item.getString("id")
            if (File(filesDir, "worlds/$id").isFile) result += Entry(id, item.getString("name"))
        }
        return result
    }

    private fun showLibrary() {
        val entries = catalog()
        AlertDialog.Builder(this)
            .setTitle("Mes mondes")
            .setItems(entries.mapIndexed { i, entry ->
                "${if (entry.id == currentId) "● " else ""}${i + 1}. ${entry.name}"
            }.toTypedArray()) { _, index -> load(entries[index]) }
            .setPositiveButton("Importer un ZIP") { _, _ ->
                val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                }
                @Suppress("DEPRECATION")
                startActivityForResult(intent, IMPORT_WORLD)
            }
            .setNeutralButton("Nouveau monde") { _, _ -> showNewWorld() }
            .setNegativeButton("Fermer", null)
            .show()
    }

    private fun showNewWorld() {
        val name = EditText(this).apply {
            setSingleLine(true)
            hint = "Nom du monde"
            setText("Nouveau monde")
            selectAll()
            filters = arrayOf(android.text.InputFilter.LengthFilter(40))
        }
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(8), dp(24), 0)
            addView(TextView(this@MainActivity).apply {
                text = "Un monde vide avec la mer, la plage et la prairie."
            })
            addView(name)
        }
        AlertDialog.Builder(this).setTitle("Créer un nouveau monde")
            .setView(form)
            .setPositiveButton("Créer") { _, _ -> createWorld(name.text.toString()) }
            .setNegativeButton("Annuler", null).show()
    }

    @Suppress("DEPRECATION")
    private fun scanAnimal() {
        if (scene.world == null) { showNewWorld(); return }
        saveView()
        startActivityForResult(Intent(this, ScanActivity::class.java)
            .putExtra("worldId", currentId)
            .putExtra("worldX", scene.camera.x + scene.camera.visibleWidth / 2)
            .putExtra("initialSpecies", if (scene.camera.y + scene.camera.visibleHeight / 2 >= 800) "chat" else "poisson"), SCAN_ANIMAL)
    }

    private fun createWorld(name: String) {
        if (busy) return
        saveView()
        setBusy(true)
        loader.execute {
            val directory = File(filesDir, "worlds").apply { mkdirs() }
            val id = "local-${UUID.randomUUID()}.zip"
            val temporary = File(directory, "$id.tmp")
            var world: AnimalWorld? = null
            try {
                temporary.outputStream().use { WorldArchive.createEmpty(it, name) }
                val loaded = temporary.inputStream().use { WorldArchive.read(it) }
                world = loaded
                check(temporary.renameTo(File(directory, id))) { "Impossible d’enregistrer ce monde." }
                registerLocalWorld(id, loaded.name)
                runOnUiThread { acceptWorld(id, loaded) }
            } catch (e: Exception) {
                world?.animals?.forEach { it.image.recycle() }
                runOnUiThread { loadFailed(e) }
            } finally {
                temporary.delete()
            }
        }
    }

    private fun registerLocalWorld(id: String, name: String) {
        val imports = JSONArray(prefs.getString("imports", "[]"))
        imports.put(JSONObject().put("id", id).put("name", name))
        prefs.edit().putString("imports", imports.toString()).apply()
    }

    private fun showOptions(anchor: View) {
        PopupMenu(this, anchor).apply {
            menu.add("Balayage horizontal").apply { isCheckable = true; isChecked = scene.autoScroll }
            menu.add("Balayage vertical").apply { isCheckable = true; isChecked = scene.verticalAutoScroll }
            menu.add("Aller à gauche")
            menu.add("Aller à droite")
            menu.add("À propos de cette version")
            setOnMenuItemClickListener { item ->
                when (item.title.toString()) {
                    "Balayage horizontal" -> scene.autoScroll = !scene.autoScroll
                    "Balayage vertical" -> scene.verticalAutoScroll = !scene.verticalAutoScroll
                    "Aller à gauche" -> scene.camera.drag(scene.width / 3f, 0f)
                    "Aller à droite" -> scene.camera.drag(-scene.width / 3f, 0f)
                    else -> AlertDialog.Builder(this@MainActivity)
                        .setTitle("Version Android · 0.2")
                        .setMessage("Explore tes mondes Python et leurs dessins sur Android.\n\n" +
                            "Photographie ou importe un dessin, recadre-le et ajoute-le à ton monde. Les ajouts sont sauvegardés automatiquement.\n\n" +
                            "Les animations articulées, les interactions et la modification des animaux sont encore à porter.\n\n" +
                            "La vue est mémorisée sur cet appareil. Les archives importées sont copiées dans l’application. " +
                            "Aucune donnée n’est envoyée sur Internet.")
                        .setPositiveButton("Compris", null).show()
                }
                scene.manualNavigation()
                true
            }
            show()
        }
    }

    private fun saveView() {
        if (currentId.isEmpty() || scene.world == null) return
        prefs.edit().putString("current", currentId)
            .putFloat("$currentId.x", scene.camera.x)
            .putFloat("$currentId.y", scene.camera.y)
            .putFloat("$currentId.zoom", scene.camera.zoom)
            .putBoolean("$currentId.auto", scene.autoScroll)
            .putBoolean("$currentId.verticalAuto", scene.verticalAutoScroll)
            .putBoolean("$currentId.playing", scene.playing).apply()
    }

    private fun load(entry: Entry) {
        if (busy) return
        saveView()
        setBusy(true)
        loader.execute {
            try {
                val world = WorldRepository.open(applicationContext, entry.id).use { WorldArchive.read(it) }
                runOnUiThread { acceptWorld(entry.id, world) }
            } catch (e: Exception) {
                runOnUiThread { loadFailed(e) }
            }
        }
    }

    private fun acceptWorld(id: String, world: AnimalWorld) {
        if (isDestroyed) {
            world.animals.forEach { it.image.recycle() }
            return
        }
        if (reloadAfterScan) {
            world.animals.forEach { it.image.recycle() }
            reloadAfterScan = false
            setBusy(false)
            load(Entry(pendingScanId ?: id, world.name))
            return
        }
        currentId = id
        scene.showWorld(world)
        scene.camera.x = prefs.getFloat("$id.x", world.cameraX)
        scene.camera.y = prefs.getFloat("$id.y", world.cameraY)
        scene.camera.zoom = prefs.getFloat("$id.zoom", world.zoom)
        scene.camera.clamp()
        scene.autoScroll = prefs.getBoolean("$id.auto", world.horizontalAuto)
        scene.verticalAutoScroll = prefs.getBoolean("$id.verticalAuto", world.verticalAuto)
        scene.playing = prefs.getBoolean("$id.playing", true)
        if (pendingScanId == id) {
            scene.camera.centerOn(if (pendingScanHabitat == "prairie") 1200f else 350f)
            scene.manualNavigation()
            pendingScanId = null
            pendingScanHabitat = null
            Toast.makeText(this, "Animal ajouté et sauvegardé", Toast.LENGTH_SHORT).show()
        }
        title.text = world.name
        val seaCount = world.animals.count { it.habitat == "mer" }
        detail.text = getString(R.string.population, seaCount, world.animals.size - seaCount)
        setBusy(false)
        updateLabels()
        saveView()
    }

    private fun setBusy(value: Boolean) {
        busy = value
        progress.visibility = if (value) View.VISIBLE else View.GONE
        scene.setActive(resumed && !value)
    }

    private fun loadFailed(error: Exception) {
        if (isDestroyed) return
        setBusy(false)
        if (scene.world == null) detail.setText(R.string.load_failed_hint)
        AlertDialog.Builder(this).setTitle("Impossible d’ouvrir ce monde")
            .setMessage(error.localizedMessage ?: "L’archive est illisible.")
            .setPositiveButton("Fermer", null).show()
    }

    @Deprecated("Platform result API retained for this dependency-light activity")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == SCAN_ANIMAL) {
            if (resultCode == RESULT_OK) {
                pendingScanId = data?.getStringExtra("worldId") ?: currentId
                pendingScanHabitat = data?.getStringExtra("habitat")
                if (busy) reloadAfterScan = true
                else load(Entry(pendingScanId!!, "Mon monde"))
            }
            return
        }
        if (requestCode != IMPORT_WORLD || resultCode != RESULT_OK || busy) return
        val uri = data?.data ?: return
        saveView()
        setBusy(true)
        loader.execute {
            val directory = File(filesDir, "worlds").apply { mkdirs() }
            val id = "import-${UUID.randomUUID()}.zip"
            val temporary = File(directory, "$id.tmp")
            var world: AnimalWorld? = null
            try {
                requireNotNull(contentResolver.openInputStream(uri)) { "Fichier inaccessible." }.use { source ->
                    FileOutputStream(temporary).use { output ->
                        val buffer = ByteArray(8192)
                        var total = 0L
                        while (true) {
                            val count = source.read(buffer)
                            if (count < 0) break
                            total += count
                            require(total <= WorldArchive.MAX_ARCHIVE_BYTES) { "L’archive dépasse 32 Mo." }
                            output.write(buffer, 0, count)
                        }
                        output.fd.sync()
                    }
                }
                val loaded = temporary.inputStream().use { WorldArchive.read(it) }
                world = loaded
                check(temporary.renameTo(File(directory, id))) { "Impossible d’enregistrer cette archive." }
                // Register even if this activity was rotated during import.
                registerLocalWorld(id, loaded.name)
                runOnUiThread { acceptWorld(id, loaded) }
            } catch (e: Exception) {
                world?.animals?.forEach { it.image.recycle() }
                runOnUiThread { loadFailed(e) }
            } finally {
                temporary.delete()
            }
        }
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        scene.setActive(!busy)
    }

    override fun onPause() {
        resumed = false
        scene.setActive(false)
        saveView()
        super.onPause()
    }

    override fun onDestroy() {
        scene.setActive(false)
        loader.shutdown()
        super.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("pendingScanId", pendingScanId)
        outState.putString("pendingScanHabitat", pendingScanHabitat)
        super.onSaveInstanceState(outState)
    }

    companion object { private const val IMPORT_WORLD = 1; private const val SCAN_ANIMAL = 2 }
}
