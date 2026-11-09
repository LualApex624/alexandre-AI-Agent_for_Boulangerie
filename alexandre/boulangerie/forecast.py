"""Prévision de production : moyenne du même jour de la semaine × coefficient.

Calcul volontairement simple et explicable à Madeleine. Avec ~2 semaines de
données, chaque jour de la semaine n'a que 1 ou 2 observations : le nombre
d'observations est donc renvoyé pour que l'agent puisse nuancer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from boulangerie.notion_repo import Vente

COEFFICIENT = 1.1
OBSERVATIONS_MINIMALES = 3


@dataclass(frozen=True)
class LignePrevision:
    produit: str
    observations: int
    moyenne: float
    recommandation: int


def arrondi_commercial(valeur: float) -> int:
    """115,5 → 116 (et non l'arrondi bancaire de Python qui donnerait parfois le pair inférieur)."""
    return int(Decimal(str(round(valeur, 6))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def fenetre(date_cible: date, jours: int) -> tuple[date, date]:
    return date_cible - timedelta(days=jours), date_cible - timedelta(days=1)


def prevoir(ventes: list[Vente], date_cible: date, fenetre_jours: int) -> list[LignePrevision]:
    debut, fin = fenetre(date_cible, fenetre_jours)
    lignes = [
        {"produit": v.produit, "quantite": v.quantite, "jour": v.jour}
        for v in ventes
        if debut <= v.jour <= fin and v.jour.weekday() == date_cible.weekday()
    ]
    if not lignes:
        return []
    # Une ligne de vente = un produit pour une date : on cumule d'abord par date
    # (au cas où une journée serait saisie en plusieurs lignes), puis on moyenne.
    par_jour = pd.DataFrame(lignes).groupby(["produit", "jour"], as_index=False)["quantite"].sum()
    stats = par_jour.groupby("produit")["quantite"].agg(["mean", "count"]).reset_index()
    resultat = [
        LignePrevision(
            produit=str(row["produit"]),
            observations=int(row["count"]),
            moyenne=float(row["mean"]),
            recommandation=arrondi_commercial(float(row["mean"]) * COEFFICIENT),
        )
        for _, row in stats.iterrows()
    ]
    return sorted(resultat, key=lambda l: (-l.recommandation, l.produit))
