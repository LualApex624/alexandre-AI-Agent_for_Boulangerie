"""Enveloppe de résultat commune aux trois outils (voir docs/tools.md)."""

from __future__ import annotations

import json
from typing import Any

RETRY_NOTION = "Réessaie une seule fois dans quelques secondes."
STOP_NOTION = "Si ça échoue encore, dis à Madeleine que ses données sont inaccessibles pour l'instant."


def _enveloppe(status: str, summary: str, data: Any, next_actions, artifacts, error) -> str:
    resultat: dict[str, Any] = {
        "status": status,
        "summary": summary,
        "data": data if data is not None else {},
        "next_actions": list(next_actions or []),
    }
    if artifacts:
        resultat["artifacts"] = artifacts
    if error:
        resultat["error"] = error
    return json.dumps(resultat, ensure_ascii=False)


def succes(summary: str, data: Any = None, next_actions=None, artifacts=None) -> str:
    return _enveloppe("success", summary, data, next_actions, artifacts, None)


def avertissement(summary: str, data: Any = None, next_actions=None, artifacts=None) -> str:
    return _enveloppe("warning", summary, data, next_actions, artifacts, None)


def erreur(
    code: str,
    summary: str,
    *,
    cause: str,
    retry: str,
    stop: str,
    data: Any = None,
    next_actions=None,
    artifacts=None,
) -> str:
    return _enveloppe(
        "error",
        summary,
        data,
        next_actions,
        artifacts,
        {"code": code, "cause": cause, "retry": retry, "stop": stop},
    )


def notion_indisponible() -> str:
    return erreur(
        "NOTION_INDISPONIBLE",
        "Les données de la boulangerie sont inaccessibles pour le moment.",
        cause="Le service qui stocke les données n'a pas répondu.",
        retry=RETRY_NOTION,
        stop=STOP_NOTION,
    )


def arrondi(valeur: float | None) -> float | int | None:
    """Montants et quantités à 2 décimales ; un entier reste un entier."""
    if valeur is None:
        return None
    valeur = round(float(valeur), 2)
    return int(valeur) if valeur.is_integer() else valeur
