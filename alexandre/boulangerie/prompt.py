"""Rendu du prompt système à partir de la date de référence configurée."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")


def jour_fr(jour: date) -> str:
    return JOURS[jour.weekday()]


def libelle(jour: date) -> str:
    return f"{jour_fr(jour)} {jour:%d/%m/%Y}"


def render_system_prompt(date_reference: date) -> str:
    lundi_courant = date_reference - timedelta(days=date_reference.weekday())
    debut_semaine_derniere = lundi_courant - timedelta(days=7)
    fin_semaine_derniere = lundi_courant - timedelta(days=1)
    demain = date_reference + timedelta(days=1)
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(
        aujourdhui=libelle(date_reference),
        aujourdhui_iso=date_reference.isoformat(),
        hier=libelle(date_reference - timedelta(days=1)),
        demain=libelle(demain),
        demain_iso=demain.isoformat(),
        semaine_derniere=(
            f"du {libelle(debut_semaine_derniere)} au {libelle(fin_semaine_derniere)}"
        ),
        semaine_derniere_debut_iso=debut_semaine_derniere.isoformat(),
        semaine_derniere_fin_iso=fin_semaine_derniere.isoformat(),
    )
