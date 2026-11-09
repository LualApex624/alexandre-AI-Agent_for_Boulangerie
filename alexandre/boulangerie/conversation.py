"""Une conversation avec Alexandre, indépendante de l'interface.

Expose deux opérations : `envoyer` un message et `valider` (ou refuser) les
commandes en attente, une décision par commande. Toute erreur inattendue devient un message clair pour
Madeleine ; le détail technique reste dans les logs.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from boulangerie.cartes import ResultatOutil
from boulangerie.notion_repo import NotionIndisponible, NotionRepository
from boulangerie.tools import CLE_VALIDATION, trouver_fournisseur

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
    validations: tuple[DemandeValidation, ...] = ()  # commandes en attente de Madeleine, dans l'ordre
    resultats: tuple[ResultatOutil, ...] = ()  # résultats d'outils depuis le dernier message de Madeleine


class Conversation:
    def __init__(self, agent: Any, thread_id: str, repo: NotionRepository | None = None):
        self._agent = agent
        self._repo = repo
        self._config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        self._en_attente = 0

    async def envoyer(self, message: str, callbacks: list | None = None) -> Reponse:
        return await self._executer({"messages": [HumanMessage(content=message)]}, callbacks)

    async def valider(self, approbations: bool | list[bool], callbacks: list | None = None) -> Reponse:
        """Une décision par commande en attente ; un booléen seul s'applique à toutes."""
        if isinstance(approbations, bool):
            approbations = [approbations] * self._en_attente
        decisions = [
            {"type": "approve"} if ok else {"type": "reject", "message": MESSAGE_REFUS} for ok in approbations
        ]
        return await self._executer(Command(resume={"decisions": decisions}), callbacks, validee=any(approbations))

    async def _executer(self, entree: Any, callbacks: list | None, validee: bool = False) -> Reponse:
        configurable = {**self._config["configurable"], CLE_VALIDATION: validee}
        config = {"configurable": configurable, "callbacks": callbacks or []}
        try:
            etat = await self._agent.ainvoke(entree, config=config)
        except Exception as exc:  # noqa: BLE001 — jamais de stacktrace côté Madeleine
            # Type seulement : le message d'une erreur réseau ou LLM peut contenir des données sensibles.
            log.error("Échec d'un tour de conversation : %s", type(exc).__name__)
            log.debug("Détail de l'échec", exc_info=True)
            return Reponse(texte=MESSAGE_ERREUR)

        interruptions = etat.get("__interrupt__") or []
        if interruptions:
            demandes = interruptions[0].value["action_requests"]
            self._en_attente = len(demandes)
            return Reponse(texte=None, validations=tuple([await self._apercu(d["args"]) for d in demandes]))
        self._en_attente = 0
        return Reponse(texte=self._dernier_texte(etat), resultats=self._resultats_du_tour(etat))

    async def _apercu(self, args: dict) -> DemandeValidation:
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
            trouve = trouver_fournisseur(await self._repo.lister_stock(), fournisseur)
        except NotionIndisponible:
            return None
        return trouve.email if trouve else None

    @staticmethod
    def _resultats_du_tour(etat: dict) -> tuple[ResultatOutil, ...]:
        resultats: list[ResultatOutil] = []
        for message in reversed(etat.get("messages", [])):
            if isinstance(message, HumanMessage):
                break
            if isinstance(message, ToolMessage):
                try:
                    enveloppe = json.loads(message.content)
                except (TypeError, ValueError):
                    continue
                if isinstance(enveloppe, dict):
                    resultats.append(ResultatOutil(message.name or "", enveloppe))
        return tuple(reversed(resultats))

    @staticmethod
    def _dernier_texte(etat: dict) -> str:
        for message in reversed(etat.get("messages", [])):
            if isinstance(message, AIMessage) and message.text.strip():
                return securiser_markdown(message.text)
        return MESSAGE_ERREUR
