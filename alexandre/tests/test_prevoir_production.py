"""Point d'entrée A — outil 3 `prevoir_production` (S5)."""

from notion_client.errors import RequestTimeoutError

from tests.fakes import DB_VENTES, page_vente


async def test_prevision_pour_un_mardi_moyenne_des_mardis_plus_dix_pour_cent(appeler):
    resultat = await appeler("prevoir_production", date_cible="2026-02-17")

    data = resultat["data"]
    assert data["date_cible"] == "2026-02-17"
    assert data["jour"] == "mardi"
    assert data["coefficient"] == 1.1
    assert data["fenetre"] == {"debut": "2026-01-20", "fin": "2026-02-16"}
    # Mardis 03/02 et 10/02 : baguette (180 + 200) / 2 = 190 → 209 ; croissant (100 + 110) / 2 = 105 → 115,5 → 116.
    assert data["produits"] == [
        {"produit": "Baguette tradition", "observations": 2, "moyenne": 190, "recommandation": 209},
        {"produit": "Croissant pur beurre", "observations": 2, "moyenne": 105, "recommandation": 116},
    ]


async def test_moins_de_trois_observations_donne_un_avertissement_d_estimation_fragile(appeler):
    resultat = await appeler("prevoir_production", date_cible="2026-02-17")

    assert resultat["status"] == "warning"
    assert "fragile" in resultat["summary"]


async def test_trois_observations_ou_plus_donnent_une_prevision_sans_avertissement(appeler, notion):
    notion.tables[DB_VENTES] = [
        page_vente("Baguette tradition", 90, 117.0, "2026-01-27"),
        page_vente("Baguette tradition", 100, 130.0, "2026-02-03"),
        page_vente("Baguette tradition", 110, 143.0, "2026-02-10"),
    ]

    resultat = await appeler("prevoir_production", date_cible="2026-02-17")

    assert resultat["status"] == "success"
    assert resultat["data"]["produits"] == [
        {"produit": "Baguette tradition", "observations": 3, "moyenne": 100, "recommandation": 110}
    ]


async def test_le_filtre_produit_ne_garde_que_le_produit_demande(appeler):
    resultat = await appeler("prevoir_production", date_cible="2026-02-17", produit="baguettes")

    assert [p["produit"] for p in resultat["data"]["produits"]] == ["Baguette tradition"]


async def test_la_prevision_n_utilise_pas_les_ventes_du_jour_cible_ni_posterieures(appeler):
    resultat = await appeler("prevoir_production", date_cible="2026-02-10")

    # Seul le mardi 03/02 précède le 10/02 : 180 → 198 et 100 → 110.
    assert resultat["data"]["produits"] == [
        {"produit": "Baguette tradition", "observations": 1, "moyenne": 180, "recommandation": 198},
        {"produit": "Croissant pur beurre", "observations": 1, "moyenne": 100, "recommandation": 110},
    ]


async def test_un_jour_sans_historique_ne_donne_aucune_quantite(appeler):
    resultat = await appeler("prevoir_production", date_cible="2026-02-22")  # dimanche

    assert resultat["status"] == "warning"
    assert resultat["data"]["produits"] == []
    assert resultat["next_actions"]


async def test_notion_indisponible_pendant_la_prevision(appeler, notion):
    notion.query_error = RequestTimeoutError()

    resultat = await appeler("prevoir_production", date_cible="2026-02-17")

    assert resultat["error"]["code"] == "NOTION_INDISPONIBLE"
