"""Point d'entrée A — outil 1 `consulter_boulangerie` (lecture Notion)."""

from notion_client.errors import RequestTimeoutError

from tests.fakes import DB_STOCK, page_stock


# --- Stock (S1) -----------------------------------------------------------------

async def test_stock_renvoie_la_quantite_le_seuil_et_signale_un_ingredient_sous_le_seuil(appeler):
    resultat = await appeler("consulter_boulangerie", table="stock", recherche="beurre")

    assert resultat["status"] == "success"
    assert resultat["data"]["nb_resultats"] == 1
    beurre = resultat["data"]["items"][0]
    assert beurre == {
        "ingredient": "Beurre AOP",
        "quantite": 8,
        "unite": "kg",
        "seuil_alerte": 10,
        "sous_seuil": True,
        "fournisseur": "Laiterie du Midi",
        "email_fournisseur": "contact@laiterie-du-midi.fr",
        "prix_unitaire": 6.6,
        "derniere_livraison": "2026-02-10",
    }


async def test_la_recherche_ignore_la_casse_les_accents_et_le_pluriel(appeler):
    resultat = await appeler("consulter_boulangerie", table="stock", recherche="AMANDE")

    assert [i["ingredient"] for i in resultat["data"]["items"]] == ["Amandes en poudre"]


async def test_lit_toutes_les_pages_notion_et_ne_resout_la_base_qu_une_fois(appeler, notion):
    # Le faux client pagine par 2 : les 4 ingrédients tiennent sur 2 pages.
    premier = await appeler("consulter_boulangerie", table="stock")
    await appeler("consulter_boulangerie", table="stock")

    assert premier["data"]["nb_resultats"] == 4
    assert notion.query_calls == 4  # 2 pages × 2 appels
    assert notion.retrieve_calls == 1  # data_source_id mis en cache


async def test_alerte_proactive_liste_les_ingredients_sous_le_seuil_du_plus_urgent_au_moins_urgent(appeler):
    resultat = await appeler("consulter_boulangerie", table="stock", sous_seuil_uniquement=True)

    # Amandes 2/3 (67 %), Beurre 8/10 (80 %), Levure 5/5 (100 %, égal au seuil) ; Farine exclue.
    assert [i["ingredient"] for i in resultat["data"]["items"]] == [
        "Amandes en poudre",
        "Beurre AOP",
        "Levure fraîche",
    ]


async def test_aucune_correspondance_est_un_avertissement_avec_une_consigne_de_reprise(appeler):
    resultat = await appeler("consulter_boulangerie", table="stock", recherche="pistache")

    assert resultat["status"] == "warning"
    assert resultat["data"]["items"] == []
    assert resultat["next_actions"]


async def test_une_ligne_notion_incomplete_est_ignoree_sans_faire_echouer_la_lecture(appeler, notion):
    notion.tables[DB_STOCK].append(page_stock(None, 3, "kg", 1, None, None, None))

    resultat = await appeler("consulter_boulangerie", table="stock")

    assert resultat["status"] == "success"
    assert resultat["data"]["nb_resultats"] == 4


async def test_notion_indisponible_renvoie_une_erreur_lisible_et_non_une_exception(appeler, notion):
    notion.query_error = RequestTimeoutError()

    resultat = await appeler("consulter_boulangerie", table="stock", recherche="beurre")

    assert resultat["status"] == "error"
    assert resultat["error"]["code"] == "NOTION_INDISPONIBLE"
    assert resultat["error"]["retry"] and resultat["error"]["stop"]


async def test_sous_seuil_uniquement_hors_du_stock_est_un_parametre_invalide(appeler):
    resultat = await appeler("consulter_boulangerie", table="catalogue", sous_seuil_uniquement=True)

    assert resultat["status"] == "error"
    assert resultat["error"]["code"] == "PARAMETRE_INVALIDE"


# --- Ventes (S2) ---------------------------------------------------------------

async def test_ventes_agrege_un_produit_sur_la_semaine_derniere(appeler):
    resultat = await appeler(
        "consulter_boulangerie", table="ventes", recherche="croissant",
        date_debut="2026-02-09", date_fin="2026-02-15",
    )

    assert resultat["status"] == "success"
    # 09/02 : 120 (156 €), 10/02 : 110 (143 €), 14/02 : 200 (260 €) ; le 03/02 est hors période.
    assert resultat["data"]["par_produit"] == [{"produit": "Croissant pur beurre", "quantite": 430, "ca": 559}]
    assert resultat["data"]["total_quantite"] == 430
    assert resultat["data"]["total_ca"] == 559
    assert resultat["data"]["nb_lignes"] == 3


async def test_ventes_sans_produit_donne_le_detail_par_produit_et_le_total(appeler):
    resultat = await appeler(
        "consulter_boulangerie", table="ventes", date_debut="2026-02-09", date_fin="2026-02-15"
    )

    assert resultat["data"]["par_produit"] == [
        {"produit": "Croissant pur beurre", "quantite": 430, "ca": 559},
        {"produit": "Baguette tradition", "quantite": 350, "ca": 455},
        {"produit": "Éclair au chocolat", "quantite": 40, "ca": 128},
    ]
    assert resultat["data"]["total_quantite"] == 820
    assert resultat["data"]["total_ca"] == 1142
    assert resultat["data"]["donnees_disponibles"] == {"debut": "2026-02-03", "fin": "2026-02-14"}


async def test_ventes_sans_periode_demande_de_ne_pas_inventer_de_dates(appeler):
    resultat = await appeler("consulter_boulangerie", table="ventes", recherche="croissant")

    assert resultat["status"] == "error"
    assert resultat["error"]["code"] == "PERIODE_MANQUANTE"


async def test_ventes_avec_une_periode_inversee_est_un_parametre_invalide(appeler):
    resultat = await appeler(
        "consulter_boulangerie", table="ventes", date_debut="2026-02-15", date_fin="2026-02-09"
    )

    assert resultat["error"]["code"] == "PARAMETRE_INVALIDE"


async def test_ventes_hors_des_donnees_disponibles_donne_la_plage_couverte(appeler):
    resultat = await appeler(
        "consulter_boulangerie", table="ventes", date_debut="2026-03-01", date_fin="2026-03-07"
    )

    assert resultat["status"] == "warning"
    assert resultat["data"]["total_quantite"] == 0
    assert resultat["data"]["donnees_disponibles"] == {"debut": "2026-02-03", "fin": "2026-02-14"}


# --- Catalogue (S3) ------------------------------------------------------------

async def test_catalogue_donne_la_marge_unitaire_calculee_et_le_pourcentage_notion(appeler):
    resultat = await appeler("consulter_boulangerie", table="catalogue", recherche="eclairs")

    assert resultat["status"] == "success"
    assert resultat["data"]["items"] == [
        {
            "produit": "Éclair au chocolat",
            "categorie": "Pâtisserie",
            "prix_vente_ttc": 3.2,
            "cout_revient": 1.1,
            "marge_unitaire": 2.1,
            "marge_pct": 65.6,
            "ingredients": "Pâte à choux, crème pâtissière chocolat",
            "temps_preparation_min": 45,
            "disponible": True,
        }
    ]
