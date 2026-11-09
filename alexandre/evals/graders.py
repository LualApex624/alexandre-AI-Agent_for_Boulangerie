"""Correcteurs déterministes des évaluations (aucun LLM juge)."""

from __future__ import annotations

import re
from itertools import combinations_with_replacement

from boulangerie.tools import normaliser

# Nombre français : « 1 142 », « 7,50 », « 65.6 » ; pas les chiffres collés à une lettre (« T65 »).
_NOMBRE = re.compile(r"(?<![\w])(\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)")
_ENUMERATION = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
TOLERANCE = 0.005

JARGON = (
    "api",
    "base de données",
    "consulter_boulangerie",
    "json",
    "notion",
    "outil",
    "passer_commande",
    "prevoir_production",
    "tool",
)


def chiffres(texte: str) -> list[float]:
    """Nombres d'un texte, sans les numéros de liste en début de ligne."""
    sans_listes = _ENUMERATION.sub("", texte)
    return [float(m.replace(" ", "").replace(" ", "").replace(",", ".")) for m in _NOMBRE.findall(sans_listes)]


def _valeurs_autorisees(sources_outils: list[str], contexte: list[str]) -> set[float]:
    lues = {round(n, 2) for source in sources_outils for n in chiffres(source)}
    autorisees = set(lues) | {round(n, 2) for texte in contexte for n in chiffres(texte)}
    for valeur in lues:
        autorisees.update({round(valeur), round(valeur, 1)})
    # Opérations simples uniquement sur des valeurs lues dans les outils.
    for a, b in combinations_with_replacement(sorted(lues), 2):
        autorisees.update({round(a + b, 2), round(abs(a - b), 2), round(a * b, 2)})
    return autorisees


def chiffres_inventes(reponse: str, sources_outils: list[str], contexte: list[str] | None = None) -> list[float]:
    """Nombres de la réponse absents des résultats d'outils (même après une opération simple)
    et du contexte (question de Madeleine, prompt système), pris tels quels."""
    autorisees = _valeurs_autorisees(sources_outils, contexte or [])
    return [n for n in chiffres(reponse) if not any(abs(n - v) < TOLERANCE for v in autorisees)]


def contient_jargon(reponse: str) -> list[str]:
    texte = normaliser(reponse)
    return sorted(terme for terme in JARGON if re.search(rf"\b{re.escape(normaliser(terme))}\b", texte))


def lignes_non_vides(reponse: str) -> int:
    return sum(1 for ligne in reponse.splitlines() if ligne.strip())
