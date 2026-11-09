"""Interface Chainlit d'Alexandre. Lancer depuis ce dossier : `chainlit run app.py`."""

from __future__ import annotations

import logging
from functools import lru_cache

import chainlit as cl
from notion_client import AsyncClient

from boulangerie.agent import build_agent, build_chat_models
from boulangerie.config import ConfigError, Settings, load_settings
from boulangerie.conversation import Conversation, DemandeValidation, Reponse
from boulangerie.mailer import SmtpMailer
from boulangerie.notion_repo import NotionIds, NotionRepository
from boulangerie.tools import Deps, build_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("alexandre")

AUTEUR = "Alexandre"


@lru_cache(maxsize=1)
def _runtime() -> tuple[Settings, NotionRepository, object]:
    """Construit une seule fois : configuration, accès Notion, outils et agent partagés.

    L'agent est partagé ; chaque session Chainlit a son propre fil (thread_id),
    donc son propre historique dans le checkpointer.
    """
    settings = load_settings()
    repo = NotionRepository(
        AsyncClient(auth=settings.notion_token),
        NotionIds(
            stock=settings.stock_db_id,
            ventes=settings.ventes_db_id,
            catalogue=settings.catalogue_db_id,
            commandes=settings.commandes_db_id,
        ),
    )
    deps = Deps(
        repo=repo,
        mailer=SmtpMailer(settings.smtp) if settings.smtp else None,
        date_reference=settings.date_reference,
        trace_dir=settings.trace_dir,
    )
    principal, secours = build_chat_models(settings)
    agent = build_agent(principal, build_tools(deps), settings.date_reference, fallback=secours)
    log.info("Alexandre prêt (modèle %s, envoi d'emails %s)", settings.llm_model, "actif" if settings.smtp else "désactivé")
    return settings, repo, agent


@cl.set_starters
async def starters() -> list[cl.Starter]:
    return [
        cl.Starter(label="🧈 Combien de beurre ?", message="Il me reste combien de beurre ? Faut que je commande ?"),
        cl.Starter(label="🚨 Urgences", message="Y a-t-il des trucs à commander en urgence ?"),
        cl.Starter(label="🥖 Baguettes demain", message="Combien de baguettes je dois pétrir demain matin ?"),
        cl.Starter(
            label="📦 Commander de la farine",
            message="Prépare-moi un mail pour commander 50 kg de farine T65 chez Minoterie Dupont",
        ),
    ]


@cl.on_chat_start
async def demarrer() -> None:
    try:
        _settings, repo, agent = _runtime()
    except ConfigError as exc:
        log.error("%s", exc)
        await cl.Message(
            author=AUTEUR,
            content="Je ne suis pas encore bien installé : il manque des réglages. "
            "Demande à Théo de vérifier le fichier `.env` (détails dans le terminal).",
        ).send()
        return
    cl.user_session.set("conversation", Conversation(agent, thread_id=cl.context.session.id, repo=repo))


def _apercu(demande: DemandeValidation) -> str:
    destinataire = demande.destinataire or "⚠️ adresse introuvable dans tes fiches"
    montant = f"\n**Montant estimé :** {demande.montant_estime} €" if demande.montant_estime is not None else ""
    return (
        "Voici le mail que je m'apprête à envoyer. **Je l'envoie ?**\n\n"
        f"**À :** {demande.fournisseur} ({destinataire})\n"
        f"**Objet :** {demande.objet}\n"
        f"**Commande :** {demande.produits}{montant}\n\n"
        f"```text\n{demande.corps}\n```\n"
        "_Si tu valides, le mail part et la commande est notée dans tes commandes._"
    )


async def _demander_validation(demande: DemandeValidation) -> bool:
    choix = await cl.AskActionMessage(
        author=AUTEUR,
        content=_apercu(demande),
        actions=[
            cl.Action(name="valider", payload={"decision": "valider"}, label="✅ Envoyer"),
            cl.Action(name="refuser", payload={"decision": "refuser"}, label="✋ Ne pas envoyer"),
        ],
        timeout=900,
    ).send()
    return bool(choix) and choix.get("payload", {}).get("decision") == "valider"


@cl.on_message
async def repondre(message: cl.Message) -> None:
    conversation: Conversation | None = cl.user_session.get("conversation")
    if conversation is None:
        await cl.Message(author=AUTEUR, content="Je ne suis pas disponible pour l'instant (réglages manquants).").send()
        return

    reponse: Reponse = await conversation.envoyer(message.content, callbacks=[cl.LangchainCallbackHandler()])
    # Tant que l'agent demande une validation, on la soumet à Madeleine.
    while reponse.validation is not None:
        approuve = await _demander_validation(reponse.validation)
        reponse = await conversation.valider(approuve, callbacks=[cl.LangchainCallbackHandler()])
    await cl.Message(author=AUTEUR, content=reponse.texte or "").send()
