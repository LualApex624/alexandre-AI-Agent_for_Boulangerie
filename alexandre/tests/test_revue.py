"""Constats de la revue de code (axes Standards et Spec)."""

import logging

from langchain_core.messages import AIMessage

from boulangerie.agent import build_agent
from boulangerie.conversation import MESSAGE_ERREUR, Conversation
from boulangerie.tools import build_tools
from tests.conftest import DATE_REFERENCE
from tests.fakes import DB_STOCK, ScriptedChatModel, page_stock
from tests.test_passer_commande import COMMANDE


async def test_recherche_sans_correspondance_avec_filtre_sous_seuil_est_un_avertissement(appeler):
    resultat = await appeler("consulter_boulangerie", table="stock", recherche="pistache", sous_seuil_uniquement=True)

    assert resultat["status"] == "warning"


async def test_recherche_trouvee_mais_au_dessus_du_seuil_reste_un_succes(appeler):
    resultat = await appeler("consulter_boulangerie", table="stock", recherche="farine", sous_seuil_uniquement=True)

    assert resultat["status"] == "success"
    assert resultat["data"]["items"] == []


async def test_un_argument_hors_schema_renvoie_une_enveloppe_et_non_une_exception(appeler):
    fenetre = await appeler("prevoir_production", date_cible="2026-02-17", fenetre_jours=3)
    table = await appeler("consulter_boulangerie", table="fournisseurs")

    assert fenetre["error"]["code"] == "PARAMETRE_INVALIDE"
    assert table["error"]["code"] == "PARAMETRE_INVALIDE"


async def test_une_date_notion_avec_heure_est_ramenee_au_format_jour(appeler, notion):
    notion.tables[DB_STOCK] = [
        page_stock("Beurre AOP", 8, "kg", 10, "Laiterie", "l@l.fr", 6.6, "2026-02-10T08:30:00.000+01:00")
    ]

    resultat = await appeler("consulter_boulangerie", table="stock")

    assert resultat["data"]["items"][0]["derniere_livraison"] == "2026-02-10"


async def test_une_panne_du_modele_n_ecrit_pas_le_message_d_erreur_dans_les_logs(deps, caplog):
    sentinelle = "cle-SENTINELLE-0123456789"
    modele = ScriptedChatModel(reponses=[RuntimeError(f"401 invalid key {sentinelle}")])
    conversation = Conversation(build_agent(modele, build_tools(deps), DATE_REFERENCE, max_retries=0), "t")

    with caplog.at_level(logging.INFO):
        reponse = await conversation.envoyer("Bonjour")

    assert reponse.texte == MESSAGE_ERREUR
    assert sentinelle not in caplog.text
    assert "RuntimeError" in caplog.text


async def test_deux_commandes_dans_le_meme_message_sont_validees_une_par_une(deps, mailer, notion):
    deux_commandes = AIMessage(content="", tool_calls=[
        {"name": "passer_commande", "args": COMMANDE, "id": "c1"},
        {"name": "passer_commande", "args": {**COMMANDE, "fournisseur": "Laiterie du Midi",
                                              "produits": "10 kg de Beurre AOP"}, "id": "c2"},
    ])
    modele = ScriptedChatModel(reponses=[deux_commandes, AIMessage(content="La farine est partie, pas le beurre.")])
    conversation = Conversation(build_agent(modele, build_tools(deps), DATE_REFERENCE, max_retries=0), "t",
                                repo=deps.repo)

    reponse = await conversation.envoyer("Commande la farine et le beurre")
    assert [v.fournisseur for v in reponse.validations] == ["minoterie dupont", "Laiterie du Midi"]

    reponse = await conversation.valider([True, False])

    assert reponse.texte == "La farine est partie, pas le beurre."
    assert [m["destinataire"] for m in mailer.sent] == ["commandes@minoterie-dupont.fr"]
    assert len(notion.created) == 1
