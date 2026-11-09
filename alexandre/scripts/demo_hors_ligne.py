"""Démo hors ligne de l'interface, pour le développement uniquement.

Ni Gemini, ni Notion, ni SMTP : le serveur web réel tourne sur le jeu de
données de test (tests/fakes.py) avec un modèle « par mots-clés » qui appelle
les vrais outils et répond par le résumé renvoyé par l'outil. Sert à revoir
l'interface quand le quota du LLM est épuisé. Ce n'est pas l'agent réel.

    cd alexandre && .venv/bin/python -m scripts.demo_hors_ligne
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from boulangerie.agent import build_agent
from boulangerie.conversation import Conversation
from boulangerie.notion_repo import NotionIds, NotionRepository
from boulangerie.serveur import Runtime, creer_alerte, creer_app
from boulangerie.tools import Deps, build_tools, normaliser
from tests.fakes import DB_CATALOGUE, DB_COMMANDES, DB_STOCK, DB_VENTES, FakeMailer, FakeNotionClient

DATE_REFERENCE = date(2026, 2, 16)
COMMANDE = {
    "fournisseur": "Minoterie Dupont",
    "produits": "50 kg de Farine T65",
    "objet": "Commande de farine T65 — Chez Madeleine",
    "corps": (
        "Madame, Monsieur,\n\nJe souhaite vous commander 50 kg de farine T65, à livrer à l'adresse habituelle.\n\n"
        "Cordialement,\nMadeleine Croûton — Chez Madeleine, Saint-Germain-des-Croissants"
    ),
    "montant_estime": 47.5,
}


def _veut_commander(texte: str) -> bool:
    return "command" in texte and ("prepare" in texte or "mail" in texte)


def _commande_depuis(texte_brut: str) -> dict:
    """Reprend « … de <produit> chez <fournisseur> » si la phrase le permet."""
    trouve = re.search(r"(?:commander|commande de)\s+(.+?)\s+chez\s+(.+?)[.!?]*$", texte_brut, re.IGNORECASE)
    if not trouve:
        return COMMANDE
    produits, fournisseur = trouve.group(1).strip(), trouve.group(2).strip()
    return {
        **COMMANDE,
        "fournisseur": fournisseur,
        "produits": produits,
        "objet": f"Commande — Chez Madeleine",
        "corps": f"Madame, Monsieur,\n\nJe souhaite vous commander : {produits}, à livrer à l'adresse habituelle.\n\n"
        "Cordialement,\nMadeleine Croûton — Chez Madeleine, Saint-Germain-des-Croissants",
        "montant_estime": None,
    }


def _appel(nom: str, args: dict, n: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nom, "args": args, "id": f"demo-{n}"}])


class ModeleDemo(BaseChatModel):
    """Choisit un outil d'après des mots-clés, puis répond avec le résumé de l'outil."""

    @property
    def _llm_type(self) -> str:
        return "demo"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ModeleDemo":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        dernier = messages[-1]
        n = len(messages)
        if isinstance(dernier, ToolMessage):
            enveloppe = json.loads(dernier.content)
            humain = next(m for m in reversed(messages) if isinstance(m, HumanMessage))
            if dernier.name == "consulter_boulangerie" and self._demande_commande(messages):
                reponse = _appel("passer_commande", _commande_depuis(humain.content), n)
            else:
                reponse = AIMessage(content=enveloppe.get("summary", ""))
        else:
            reponse = self._choisir(normaliser(dernier.content if isinstance(dernier, HumanMessage) else ""), n)
        return ChatResult(generations=[ChatGeneration(message=reponse)])

    @staticmethod
    def _demande_commande(messages) -> bool:
        humain = next(m for m in reversed(messages) if isinstance(m, HumanMessage))
        texte = normaliser(humain.content)
        return _veut_commander(texte) and not any(
            isinstance(m, ToolMessage) and m.name == "passer_commande" for m in messages
        )

    @staticmethod
    def _choisir(texte: str, n: int) -> AIMessage:
        if _veut_commander(texte):
            return _appel("consulter_boulangerie", {"table": "stock"}, n)
        if "urgen" in texte:
            return _appel("consulter_boulangerie", {"table": "stock", "sous_seuil_uniquement": True}, n)
        if "beurre" in texte:
            return _appel("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}, n)
        if "baguette" in texte or "demain" in texte or "petrir" in texte:
            return _appel("prevoir_production", {"date_cible": "2026-02-17"}, n)
        if "vendu" in texte or "vente" in texte:
            return _appel("consulter_boulangerie", {"table": "ventes", "date_debut": "2026-02-09", "date_fin": "2026-02-15"}, n)
        if "marge" in texte:
            return _appel("consulter_boulangerie", {"table": "catalogue", "recherche": "eclair"}, n)
        return AIMessage(content="Mode démo : essaie « beurre », « urgences », « baguettes demain », « ventes », « marge » ou « commande ».")


def runtime_demo() -> Runtime:
    deps = Deps(
        repo=NotionRepository(FakeNotionClient(page_size=100), NotionIds(DB_STOCK, DB_VENTES, DB_CATALOGUE, DB_COMMANDES)),
        mailer=FakeMailer(),
        trace_dir=Path(tempfile.mkdtemp(prefix="alexandre-demo-")),
    )
    outils = build_tools(deps)
    agent = build_agent(ModeleDemo(), outils, DATE_REFERENCE, max_retries=0)
    return Runtime(
        creer_conversation=lambda fil: Conversation(agent, thread_id=fil, repo=deps.repo),
        alerte=creer_alerte(outils),
        date_reference=DATE_REFERENCE,
        origines=frozenset({"http://localhost:8001", "http://127.0.0.1:8001"}),
    )


if __name__ == "__main__":
    import uvicorn

    print("\n  Démo hors ligne (données de test, pas de LLM) : http://localhost:8001\n", flush=True)
    uvicorn.run(creer_app(runtime_demo()), host="127.0.0.1", port=8001, log_level="warning")
