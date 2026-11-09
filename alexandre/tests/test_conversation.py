"""Point d'entrée B — graphe de l'agent : validation humaine, historique complet, erreurs."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from boulangerie.agent import build_agent
from boulangerie.conversation import MESSAGE_ERREUR, Conversation
from boulangerie.tools import build_tools
from tests.fakes import ScriptedChatModel, appel_outil

COMMANDE = {
    "fournisseur": "Minoterie Dupont",
    "produits": "50 kg de Farine T65",
    "objet": "Commande de farine T65",
    "corps": "Madame, Monsieur,\n\nJe souhaite commander 50 kg de farine T65.\n\nCordialement,\nMadeleine",
    "montant_estime": 47.5,
}


def nouvelle_conversation(deps, *reponses) -> tuple[Conversation, ScriptedChatModel]:
    modele = ScriptedChatModel(reponses=list(reponses))
    agent = build_agent(modele, build_tools(deps), deps.date_reference, max_retries=0)
    return Conversation(agent, thread_id="madeleine", repo=deps.repo), modele


async def test_une_question_appelle_l_outil_et_renvoie_la_reponse_du_modele(deps):
    conversation, modele = nouvelle_conversation(
        deps,
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}),
        AIMessage(content="Il te reste **8 kg** de beurre."),
    )

    reponse = await conversation.envoyer("Il me reste combien de beurre ?")

    assert reponse.texte == "Il te reste **8 kg** de beurre."
    assert reponse.validation is None
    premier_appel, second_appel = modele.appels
    assert isinstance(premier_appel[0], SystemMessage) and "lundi 16/02/2026" in premier_appel[0].content
    resultat_outil = next(m for m in second_appel if isinstance(m, ToolMessage))
    assert "Beurre AOP" in resultat_outil.content


async def test_l_historique_conserve_les_resultats_d_outils_d_un_tour_a_l_autre(deps):
    conversation, modele = nouvelle_conversation(
        deps,
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}),
        AIMessage(content="Il te reste 8 kg de beurre."),
        AIMessage(content="Oui, il est sous le seuil."),
    )

    await conversation.envoyer("Il me reste combien de beurre ?")
    await conversation.envoyer("Et je dois commander ?")

    dernier_appel = modele.appels[-1]
    assert [m.content for m in dernier_appel if isinstance(m, HumanMessage)] == [
        "Il me reste combien de beurre ?",
        "Et je dois commander ?",
    ]
    assert any(isinstance(m, ToolMessage) and "Beurre AOP" in m.content for m in dernier_appel)


async def test_le_graphe_s_arrete_avant_passer_commande_et_n_envoie_rien(deps, mailer, notion):
    conversation, _ = nouvelle_conversation(deps, appel_outil("passer_commande", COMMANDE))

    reponse = await conversation.envoyer("Commande 50 kg de farine T65 chez Minoterie Dupont")

    assert reponse.validation is not None
    assert reponse.validation.fournisseur == "Minoterie Dupont"
    assert reponse.validation.destinataire == "commandes@minoterie-dupont.fr"
    assert reponse.validation.objet == COMMANDE["objet"]
    assert reponse.validation.corps == COMMANDE["corps"]
    assert mailer.sent == [] and notion.created == []


async def test_apres_validation_l_email_part_et_la_commande_est_enregistree_une_seule_fois(deps, mailer, notion):
    conversation, _ = nouvelle_conversation(
        deps,
        appel_outil("passer_commande", COMMANDE),
        AIMessage(content="C'est parti, la commande est notée."),
    )
    await conversation.envoyer("Commande 50 kg de farine T65 chez Minoterie Dupont")

    reponse = await conversation.valider(approuve=True)

    assert reponse.texte == "C'est parti, la commande est notée."
    assert len(mailer.sent) == 1
    assert len(notion.created) == 1


async def test_un_refus_de_madeleine_n_envoie_rien_et_le_modele_en_est_informe(deps, mailer, notion):
    conversation, modele = nouvelle_conversation(
        deps,
        appel_outil("passer_commande", COMMANDE),
        AIMessage(content="D'accord, rien n'est parti."),
    )
    await conversation.envoyer("Commande 50 kg de farine T65 chez Minoterie Dupont")

    reponse = await conversation.valider(approuve=False)

    assert reponse.texte == "D'accord, rien n'est parti."
    assert mailer.sent == [] and notion.created == []
    refus = next(m for m in modele.appels[-1] if isinstance(m, ToolMessage))
    assert "refus" in refus.content.lower()


async def test_une_panne_du_modele_donne_un_message_clair_sans_trace_technique(deps):
    conversation, _ = nouvelle_conversation(deps, RuntimeError("429 RESOURCE_EXHAUSTED quota"))

    reponse = await conversation.envoyer("Bonjour")

    assert reponse.texte == MESSAGE_ERREUR
    assert "429" not in reponse.texte
