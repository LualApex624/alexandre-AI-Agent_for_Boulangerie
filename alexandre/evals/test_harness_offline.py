"""Hors ligne : le harnais valide un comportement idéal et rejette les écarts.

Le modèle est scripté : ces tests prouvent que les correcteurs et le câblage
fonctionnent, pas que Gemini se comporte bien (c'est le rôle des évals live).
"""

import pytest
from langchain_core.messages import AIMessage

from evals.harness import jouer
from evals.scenarios import SCENARIOS
from tests.fakes import ScriptedChatModel, appel_outil

COMMANDE = {
    "fournisseur": "Minoterie Dupont",
    "produits": "50 kg de Farine T65",
    "objet": "Commande de farine T65",
    "corps": "Madame, Monsieur,\n\nJe souhaite commander 50 kg de farine T65.\n\nCordialement,\nMadeleine Croûton",
    "montant_estime": 47.5,
}

SCRIPTS_IDEAUX = {
    "S1": [
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}),
        AIMessage("Il te reste **8 kg** de beurre, sous ton seuil de 10 kg. Je te prépare une commande ?"),
    ],
    "S2": [
        appel_outil("consulter_boulangerie", {"table": "ventes", "recherche": "croissant",
                                              "date_debut": "2026-02-09", "date_fin": "2026-02-15"}),
        AIMessage("La semaine dernière, tu as vendu **430 croissants**, pour **559 €**."),
    ],
    "S3": [
        appel_outil("consulter_boulangerie", {"table": "catalogue", "recherche": "éclair"}),
        AIMessage("Sur un éclair au chocolat, tu gagnes **2,10 €**, soit **65,6 %** de marge."),
    ],
    "S4": [
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "farine"}, "appel-1"),
        appel_outil("passer_commande", COMMANDE, "appel-2"),
        AIMessage("C'est parti chez Minoterie Dupont, et la commande est notée."),
    ],
    "S5": [
        appel_outil("prevoir_production", {"date_cible": "2026-02-17", "produit": "baguette"}),
        AIMessage("Pour demain mardi, prévois environ **209 baguettes**. Estimation fragile : peu de mardis en mémoire."),
    ],
    "S6": [
        appel_outil("consulter_boulangerie", {"table": "stock", "sous_seuil_uniquement": True}),
        AIMessage("À commander en priorité : les **amandes en poudre** (2 kg), le **beurre AOP** (8 kg) "
                  "et la **levure fraîche** (5 kg)."),
    ],
}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
async def test_un_comportement_ideal_passe_tous_les_correcteurs(scenario):
    resultat = await jouer(scenario, ScriptedChatModel(reponses=list(SCRIPTS_IDEAUX[scenario.id])), max_retries=0)

    assert resultat.ok, resultat.echecs()


async def test_un_chiffre_invente_est_detecte():
    s1 = SCENARIOS[0]
    script = [
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}),
        AIMessage("Il te reste **8 kg** de beurre ; pense à en commander **25 kg**, c'est ce que tu prends d'habitude."),
    ]

    resultat = await jouer(s1, ScriptedChatModel(reponses=script), max_retries=0)

    assert resultat.echecs().keys() == {"aucun_chiffre_invente"}
    assert "25.0" in resultat.echecs()["aucun_chiffre_invente"]


async def test_une_reponse_sans_appel_d_outil_est_rejetee():
    s2 = SCENARIOS[1]
    script = [AIMessage("Tu as vendu environ 400 croissants la semaine dernière.")]

    resultat = await jouer(s2, ScriptedChatModel(reponses=script), max_retries=0)

    assert {"outil", "reponse", "aucun_chiffre_invente"} <= resultat.echecs().keys()


async def test_une_commande_annoncee_sans_passer_par_la_validation_est_rejetee():
    s4 = next(s for s in SCENARIOS if s.id == "S4")
    script = [
        AIMessage("Voici ton mail. Tu veux que je l'envoie ?"),
        AIMessage("C'est envoyé !"),  # après la relance, sans appeler passer_commande
    ]

    resultat = await jouer(s4, ScriptedChatModel(reponses=script), max_retries=0)

    assert {"arret_avant_envoi", "envoi_apres_validation", "outil"} <= resultat.echecs().keys()


async def test_le_jargon_technique_est_detecte():
    s1 = SCENARIOS[0]
    script = [
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}),
        AIMessage("D'après ta base Notion, il te reste 8 kg de beurre. Commande conseillée."),
    ]

    resultat = await jouer(s1, ScriptedChatModel(reponses=script), max_retries=0)

    assert resultat.echecs().keys() == {"pas_de_jargon"}
