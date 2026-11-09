"""Cartes de l'interface : construites uniquement à partir des résultats d'outils."""

from langchain_core.messages import AIMessage

from boulangerie.agent import build_agent
from boulangerie.cartes import ResultatOutil, cartes_depuis
from boulangerie.conversation import Conversation
from boulangerie.tools import build_tools
from tests.conftest import DATE_REFERENCE
from tests.fakes import ScriptedChatModel, appel_outil


async def _carte(appeler, outil: str, **arguments) -> list[dict]:
    return cartes_depuis([ResultatOutil(outil, await appeler(outil, **arguments))])


async def test_carte_stock_avec_action_de_commande_pour_un_ingredient_sous_le_seuil(appeler):
    (carte,) = await _carte(appeler, "consulter_boulangerie", table="stock", recherche="beurre")

    assert carte["type"] == "stock"
    assert carte["titre"] == "Stock · Beurre AOP"
    assert carte["items"] == [
        {"ingredient": "Beurre AOP", "quantite": 8, "unite": "kg", "seuil_alerte": 10,
         "sous_seuil": True, "fournisseur": "Laiterie du Midi", "niveau": 0.8}
    ]
    assert carte["action"] == {
        "libelle": "Préparer la commande",
        "message": "Prépare une commande de Beurre AOP chez Laiterie du Midi",
    }


async def test_carte_stock_sans_alerte_n_a_pas_d_action(appeler):
    (carte,) = await _carte(appeler, "consulter_boulangerie", table="stock", recherche="farine")

    assert carte["items"][0]["niveau"] == 1.0  # 120 kg pour un seuil de 50 : jauge pleine
    assert "action" not in carte


async def test_carte_ventes_avec_totaux_et_parts_relatives(appeler):
    (carte,) = await _carte(
        appeler, "consulter_boulangerie", table="ventes", date_debut="2026-02-09", date_fin="2026-02-15"
    )

    assert carte["type"] == "ventes"
    assert carte["titre"] == "Ventes du 09/02 au 15/02"
    assert (carte["total_quantite"], carte["total_ca"]) == (820, 1142)
    assert carte["barres"] == [
        {"libelle": "Croissant pur beurre", "valeur": 430, "part": 1.0},
        {"libelle": "Baguette tradition", "valeur": 350, "part": 0.81},
        {"libelle": "Éclair au chocolat", "valeur": 40, "part": 0.09},
    ]


async def test_carte_marge_depuis_le_catalogue(appeler):
    (carte,) = await _carte(appeler, "consulter_boulangerie", table="catalogue", recherche="éclair")

    assert carte == {
        "type": "marge",
        "titre": "Marge · Éclair au chocolat",
        "items": [{"produit": "Éclair au chocolat", "prix_vente_ttc": 3.2, "cout_revient": 1.1,
                   "marge_unitaire": 2.1, "marge_pct": 65.6}],
    }


async def test_carte_prevision_met_en_avant_le_premier_produit_et_signale_la_fragilite(appeler):
    (carte,) = await _carte(appeler, "prevoir_production", date_cible="2026-02-17")

    assert carte["type"] == "prevision"
    assert carte["titre"] == "Prévision · mardi 17/02"
    assert carte["principal"] == {"produit": "Baguette tradition", "recommandation": 209, "observations": 2}
    assert carte["barres"] == [
        {"libelle": "Baguette tradition", "valeur": 209, "part": 1.0},
        {"libelle": "Croissant pur beurre", "valeur": 116, "part": 0.56},
    ]
    assert carte["fragile"] is True


async def test_carte_commande_envoyee(appeler):
    resultat = await appeler(
        "passer_commande", fournisseur="Minoterie Dupont", produits="50 kg de Farine T65",
        objet="Commande", corps="Madame, Monsieur,\nMerci.", montant_estime=47.5,
    )

    (carte,) = cartes_depuis([ResultatOutil("passer_commande", resultat)])

    assert carte["type"] == "commande"
    assert carte["reference"] == resultat["artifacts"]["reference"]
    assert carte["fournisseur"] == "Minoterie Dupont"
    assert carte["partielle"] is False


async def test_aucune_carte_pour_une_erreur_ou_un_resultat_vide(appeler):
    erreur = await appeler("consulter_boulangerie", table="ventes")  # période manquante
    vide = await appeler("consulter_boulangerie", table="stock", recherche="pistache")

    assert cartes_depuis([ResultatOutil("consulter_boulangerie", erreur),
                          ResultatOutil("consulter_boulangerie", vide)]) == []


async def test_la_conversation_expose_les_resultats_d_outils_du_tour_courant_seulement(deps):
    modele = ScriptedChatModel(reponses=[
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}),
        AIMessage(content="Il te reste 8 kg."),
        AIMessage(content="Avec plaisir."),
    ])
    conversation = Conversation(build_agent(modele, build_tools(deps), DATE_REFERENCE, max_retries=0), "t")

    premier = await conversation.envoyer("Combien de beurre ?")
    second = await conversation.envoyer("Merci")

    assert [(r.outil, r.enveloppe["status"]) for r in premier.resultats] == [("consulter_boulangerie", "success")]
    assert second.resultats == ()
