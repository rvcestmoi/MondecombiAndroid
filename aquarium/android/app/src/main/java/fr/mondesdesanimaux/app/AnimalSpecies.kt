package fr.mondesdesanimaux.app

data class AnimalSpecies(val id: String, val label: String, val habitat: String) {
    companion object {
        val all = listOf(
            AnimalSpecies("poisson", "Poisson", "mer"),
            AnimalSpecies("meduse", "Méduse", "mer"),
            AnimalSpecies("crabe", "Crabe", "mer"),
            AnimalSpecies("etoile", "Étoile de mer", "mer"),
            AnimalSpecies("tortue", "Tortue", "mer"),
            AnimalSpecies("chat", "Chat", "prairie"),
            AnimalSpecies("chien", "Chien", "prairie"),
            AnimalSpecies("lapin", "Lapin", "prairie"),
            AnimalSpecies("vache", "Vache", "prairie"),
            AnimalSpecies("cochon", "Cochon", "prairie"),
            AnimalSpecies("mouton", "Mouton", "prairie"),
            AnimalSpecies("poule", "Poule", "prairie"),
            AnimalSpecies("cheval", "Cheval", "prairie"),
            AnimalSpecies("lion", "Lion", "prairie"),
            AnimalSpecies("elephant", "Éléphant", "prairie"),
            AnimalSpecies("girafe", "Girafe", "prairie"),
            AnimalSpecies("zebre", "Zèbre", "prairie"),
            AnimalSpecies("rhinoceros", "Rhinocéros", "prairie"),
            AnimalSpecies("perroquet", "Perroquet", "prairie"),
            AnimalSpecies("pigeon", "Pigeon", "prairie"),
            AnimalSpecies("moineau", "Moineau", "prairie"),
            AnimalSpecies("aigle", "Aigle", "prairie"),
        )
        fun find(id: String) = requireNotNull(all.find { it.id == id }) { "Espèce inconnue." }
    }
}
