"""Une conversation avec Alexandre, indépendante de l'interface.

Expose deux opérations : `envoyer` un message et `valider` (ou refuser) une
commande en attente. Toute erreur inattendue devient un message clair pour
Madeleine ; le détail technique reste dans les logs.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from boulangerie.notion_repo import NotionIndisponible, NotionRepository
from boulangerie.tools import CLE_VALIDATION, annuaire_fournisseurs, normaliser

log = logging.getLogger(__name__)

MESSAGE_ERREUR = (
    "Oups, je n'arrive pas à réfléchir pour l'instant 🥖 "
    "Réessaie dans une minute ; si ça continue, préviens Théo."
)
_IMAGE_MD = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LIEN_MD = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def securiser_markdown(texte: str) -> str:
    """Retire images et liens markdown (on garde leur texte) : une image chargée par le
    navigateur pourrait envoyer des données à un site tiers, un lien pourrait tromper Madeleine."""
    return _LIEN_MD.sub(r"\1", _IMAGE_MD.sub(r"\1", texte))


def securiser_apercu(texte: str) -> str:
    """Même chose, et empêche de sortir du bloc de code qui encadre le brouillon."""
    return securiser_markdown(texte).replace("```", "ʼʼʼ")


MESSAGE_REFUS = "Madeleine a refusé l'envoi : rien n'a été envoyé ni enregistré."


@dataclass(frozen=True)
class DemandeValidation:
    fournisseur: str
    destinataire: str | None
    produits: str
    objet: str
    corps: str
    montant_estime: float | None


@dataclass(frozen=True)
class Reponse:
    texte: str | None
    validation: DemandeValidation | None = None


class Conversation:
    def __init__(self, agent: Any, thread_id: str, repo: NotionRepository | None = None):
        self._agent = agent
        self._repo = repo
        self._config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    async def envoyer(self, message: str, callbacks: list | None = None) -> Reponse:
        return await self._executer({"messages": [HumanMessage(content=message)]}, callbacks)

    async def valider(self, approuve: bool, callbacks: list | None = None) -> Reponse:
        decision = {"type": "approve"} if approuve else {"type": "reject", "message": MESSAGE_REFUS}
        return await self._executer(Command(resume={"decisions": [decision]}), callbacks, validee=approuve)

    async def _executer(self, entree: Any, callbacks: list | None, validee: bool = False) -> Reponse:
        configurable = {**self._config["configurable"], CLE_VALIDATION: validee}
        config = {"configurable": configurable, "callbacks": callbacks or []}
        try:
            etat = await self._agent.ainvoke(entree, config=config)
        except Exception:  # noqa: BLE001 — jamais de stacktrace côté Madeleine
            log.exception("Échec d'un tour de conversation")
            return Reponse(texte=MESSAGE_ERREUR)

        interruptions = etat.get("__interrupt__") or []
        if interruptions:
            return Reponse(texte=None, validation=await self._apercu(interruptions[0].value))
        return Reponse(texte=self._dernier_texte(etat))

    async def _apercu(self, demande: dict) -> DemandeValidation:
        args = demande["action_requests"][0]["args"]
        fournisseur = str(args.get("fournisseur", ""))
        return DemandeValidation(
            fournisseur=securiser_apercu(fournisseur),
            destinataire=await self._destinataire(fournisseur),
            produits=securiser_apercu(str(args.get("produits", ""))),
            objet=securiser_apercu(str(args.get("objet", ""))),
            corps=securiser_apercu(str(args.get("corps", ""))),
            montant_estime=args.get("montant_estime"),
        )

    async def _destinataire(self, fournisseur: str) -> str | None:
        if self._repo is None:
            return None
        try:
            trouve = annuaire_fournisseurs(await self._repo.lister_stock()).get(normaliser(fournisseur))
        except NotionIndisponible:
            return None
        return trouve[1] if trouve else None

    @staticmethod
    def _dernier_texte(etat: dict) -> str:
        for message in reversed(etat.get("messages", [])):
            if isinstance(message, AIMessage) and message.text.strip():
                return securiser_markdown(message.text)
        return MESSAGE_ERREUR
