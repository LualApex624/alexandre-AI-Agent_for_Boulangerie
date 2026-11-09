"""Serveur web d'Alexandre : page statique + WebSocket vers l'agent.

Protocole (JSON, un objet par trame) :

  navigateur → serveur
    {"type": "message", "texte": "..."}                  question de Madeleine (1 à 2 000 caractères)
    {"type": "validation", "decisions": [true, false]}   une décision par commande en attente

  serveur → navigateur
    {"type": "bienvenue", "date": "...", "alerte": carte|null}
    {"type": "humeur", "valeur": "petrit"}                Alexandre travaille
    {"type": "outil", "nom": "...", "etat": "debut|fin|erreur"}
    {"type": "validation", "demandes": [...]}             brouillons à valider
    {"type": "reponse", "texte": "...", "cartes": [...]}
    {"type": "erreur", "texte": "..."}

Sécurité : origine vérifiée avant d'accepter la connexion, en-têtes CSP stricts,
écoute sur 127.0.0.1, taille des trames bornée, aucune trace technique envoyée.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.callbacks import AsyncCallbackHandler

from boulangerie.cartes import ResultatOutil, cartes_depuis
from boulangerie.conversation import Conversation, Reponse
from boulangerie.prompt import libelle

log = logging.getLogger(__name__)

DOSSIER_WEB = Path(__file__).resolve().parent.parent / "web"
TEXTE_MAX = 2000
TRAME_MAX = 8000
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    ]
)
MESSAGE_INCOMPRIS = "Je n'ai pas compris ce message. Réessaie."
MESSAGE_TROP_LONG = f"Ton message est trop long ({TEXTE_MAX} caractères au plus)."
MESSAGE_RIEN_A_VALIDER = "Il n'y a pas de commande en attente de validation."


@dataclass(frozen=True)
class Runtime:
    creer_conversation: Callable[[str], Conversation]
    alerte: Callable[[], Awaitable[dict | None]]
    date_reference: date
    origines: frozenset[str]


def creer_alerte(outils: list) -> Callable[[], Awaitable[dict | None]]:
    """Alerte proactive : lit directement le stock sous seuil, sans passer par le modèle."""
    consulter = next(t for t in outils if t.name == "consulter_boulangerie")

    async def alerte() -> dict | None:
        try:
            enveloppe = json.loads(await consulter.ainvoke({"table": "stock", "sous_seuil_uniquement": True}))
        except Exception as exc:  # noqa: BLE001 — l'alerte est un bonus, jamais bloquante
            log.warning("Alerte stock indisponible : %s", type(exc).__name__)
            return None
        cartes = cartes_depuis([ResultatOutil("consulter_boulangerie", enveloppe)])
        return cartes[0] if cartes else None

    return alerte


class _EmetteurOutils(AsyncCallbackHandler):
    """Rend les appels d'outils visibles dans l'interface, en direct."""

    def __init__(self, envoyer: Callable[[dict], Awaitable[None]]):
        self._envoyer = envoyer
        self._noms: dict[uuid.UUID, str] = {}

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: uuid.UUID, **kwargs: Any):
        nom = (serialized or {}).get("name") or kwargs.get("name") or "outil"
        self._noms[run_id] = nom
        await self._envoyer({"type": "outil", "nom": nom, "etat": "debut"})

    async def on_tool_end(self, output: Any, *, run_id: uuid.UUID, **kwargs: Any):
        await self._envoyer({"type": "outil", "nom": self._noms.pop(run_id, "outil"), "etat": "fin"})

    async def on_tool_error(self, error: BaseException, *, run_id: uuid.UUID, **kwargs: Any):
        await self._envoyer({"type": "outil", "nom": self._noms.pop(run_id, "outil"), "etat": "erreur"})


def _lire_trame(brut: str) -> tuple[str, Any] | None:
    """Valide une trame du navigateur ; renvoie (type, valeur) ou None."""
    try:
        trame = json.loads(brut)
    except ValueError:
        return None
    if not isinstance(trame, dict):
        return None
    if trame.get("type") == "message" and isinstance(trame.get("texte"), str):
        return "message", trame["texte"].strip()
    decisions = trame.get("decisions")
    if (
        trame.get("type") == "validation"
        and isinstance(decisions, list)
        and decisions
        and all(isinstance(d, bool) for d in decisions)
    ):
        return "validation", decisions
    return None


def _evenement(reponse: Reponse) -> dict:
    if reponse.validations:
        return {"type": "validation", "demandes": [asdict(d) for d in reponse.validations]}
    return {"type": "reponse", "texte": reponse.texte or "", "cartes": cartes_depuis(list(reponse.resultats))}


def creer_app(runtime: Runtime) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def entetes_de_securite(request: Request, call_next):
        reponse = await call_next(request)
        reponse.headers["Content-Security-Policy"] = CSP
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["Referrer-Policy"] = "no-referrer"
        reponse.headers["X-Frame-Options"] = "DENY"
        return reponse

    app.mount("/static", StaticFiles(directory=DOSSIER_WEB), name="static")

    @app.get("/")
    async def accueil() -> FileResponse:
        return FileResponse(DOSSIER_WEB / "index.html")

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        # Protection contre le détournement de WebSocket depuis un autre site (CSWSH).
        if websocket.headers.get("origin") not in runtime.origines:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        conversation = runtime.creer_conversation(f"web-{uuid.uuid4()}")
        emetteur = _EmetteurOutils(websocket.send_json)
        await websocket.send_json(
            {"type": "bienvenue", "date": libelle(runtime.date_reference), "alerte": await runtime.alerte()}
        )
        try:
            while True:
                brut = await websocket.receive_text()
                if len(brut) > TRAME_MAX:
                    await websocket.send_json({"type": "erreur", "texte": MESSAGE_TROP_LONG})
                    continue
                trame = _lire_trame(brut)
                if trame is None or (trame[0] == "message" and not trame[1]):
                    await websocket.send_json({"type": "erreur", "texte": MESSAGE_INCOMPRIS})
                    continue
                genre, valeur = trame
                if genre == "message" and len(valeur) > TEXTE_MAX:
                    await websocket.send_json({"type": "erreur", "texte": MESSAGE_TROP_LONG})
                    continue
                if genre == "validation" and len(valeur) != conversation.en_attente:
                    await websocket.send_json({"type": "erreur", "texte": MESSAGE_RIEN_A_VALIDER})
                    continue
                await websocket.send_json({"type": "humeur", "valeur": "petrit"})
                if genre == "message":
                    reponse = await conversation.envoyer(valeur, callbacks=[emetteur])
                else:
                    reponse = await conversation.valider(valeur, callbacks=[emetteur])
                await websocket.send_json(_evenement(reponse))
        except WebSocketDisconnect:
            return

    return app


def construire_runtime():
    """Câblage réel : configuration, Notion, SMTP, Gemini."""
    from notion_client import AsyncClient

    from boulangerie.agent import build_agent, build_chat_models
    from boulangerie.config import load_settings
    from boulangerie.mailer import SmtpMailer
    from boulangerie.notion_repo import NotionIds, NotionRepository
    from boulangerie.tools import Deps, build_tools

    settings = load_settings()
    repo = NotionRepository(
        AsyncClient(auth=settings.notion_token),
        NotionIds(settings.stock_db_id, settings.ventes_db_id, settings.catalogue_db_id, settings.commandes_db_id),
    )
    deps = Deps(repo=repo, mailer=SmtpMailer(settings.smtp) if settings.smtp else None, trace_dir=settings.trace_dir)
    outils = build_tools(deps)
    principal, secours = build_chat_models(settings)
    agent = build_agent(principal, outils, settings.date_reference, fallback=secours)
    log.info("Alexandre prêt (modèle %s, envoi d'emails %s)", settings.llm_model, "actif" if settings.smtp else "désactivé")
    return settings, Runtime(
        creer_conversation=lambda fil: Conversation(agent, thread_id=fil, repo=repo),
        alerte=creer_alerte(outils),
        date_reference=settings.date_reference,
        origines=frozenset({f"http://localhost:{settings.port}", f"http://127.0.0.1:{settings.port}"}),
    )


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    settings, runtime = construire_runtime()
    print(f"\n  Alexandre est prêt : http://localhost:{settings.port}\n", flush=True)
    uvicorn.run(creer_app(runtime), host="127.0.0.1", port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
