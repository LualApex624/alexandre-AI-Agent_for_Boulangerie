"""Les trois outils d'Alexandre. Contrat détaillé : docs/tools.md."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from boulangerie.envelope import arrondi, avertissement, erreur, notion_indisponible, succes
from boulangerie.forecast import COEFFICIENT, OBSERVATIONS_MINIMALES, fenetre, prevoir
from boulangerie.notion_repo import NotionIndisponible, NotionRepository
from boulangerie.prompt import jour_fr


class Mailer(Protocol):
    async def envoyer(self, destinataire: str, objet: str, corps: str) -> None: ...


@dataclass
class Deps:
    repo: NotionRepository
    mailer: Mailer | None
    date_reference: date
    trace_dir: Path
    clock: Callable[[], datetime] = field(default=datetime.now)


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in sans_accents if not unicodedata.combining(c)).casefold().strip()


def correspond(recherche: str | None, nom: str) -> bool:
    if not recherche:
        return True
    cible, mot = normaliser(nom), normaliser(recherche)
    singulier = mot[:-1] if len(mot) > 3 and mot.endswith("s") else mot
    return mot in cible or singulier in cible


# --- Outil 1 : consulter_boulangerie -------------------------------------------

class ConsulterArgs(BaseModel):
    table: Literal["stock", "ventes", "catalogue"] = Field(
        description="stock = ingrédients, seuils, fournisseurs ; ventes = quantités vendues et chiffre "
        "d'affaires ; catalogue = prix, coût, marge, ingrédients, temps de préparation des produits."
    )
    recherche: str | None = Field(
        default=None,
        description="Mot-clé court sur le nom de l'ingrédient ou du produit (ex. 'beurre', 'croissant'). "
        "Laisser vide pour tout lister.",
    )
    date_debut: date | None = Field(
        default=None, description="Début de période AAAA-MM-JJ. Obligatoire pour table='ventes'."
    )
    date_fin: date | None = Field(
        default=None, description="Fin de période AAAA-MM-JJ (incluse). Obligatoire pour table='ventes'."
    )
    sous_seuil_uniquement: bool = Field(
        default=False,
        description="table='stock' uniquement : ne garder que les ingrédients à commander "
        "(quantité inférieure ou égale au seuil d'alerte).",
    )


def _parametre_invalide(cause: str) -> str:
    return erreur(
        "PARAMETRE_INVALIDE",
        "La demande n'est pas valide.",
        cause=cause,
        retry="Corrige l'appel une seule fois.",
        stop="Si tu ne sais pas comment corriger, demande une précision à Madeleine.",
    )


async def _consulter_stock(deps: Deps, recherche: str | None, sous_seuil_uniquement: bool) -> str:
    ingredients = [i for i in await deps.repo.lister_stock() if correspond(recherche, i.nom)]
    if sous_seuil_uniquement:
        ingredients = sorted(
            (i for i in ingredients if i.sous_seuil),
            key=lambda i: (i.quantite / i.seuil) if i.seuil else 0,
        )
    items = [
        {
            "ingredient": i.nom,
            "quantite": arrondi(i.quantite),
            "unite": i.unite,
            "seuil_alerte": arrondi(i.seuil),
            "sous_seuil": i.sous_seuil,
            "fournisseur": i.fournisseur,
            "email_fournisseur": i.email,
            "prix_unitaire": arrondi(i.prix_unitaire),
            "derniere_livraison": i.derniere_livraison,
        }
        for i in ingredients
    ]
    data = {"items": items, "nb_resultats": len(items)}
    if not items:
        if sous_seuil_uniquement:
            return succes("Aucun ingrédient n'est sous son seuil d'alerte.", data)
        return avertissement(
            f"Aucun ingrédient ne correspond à « {recherche} ».",
            data,
            next_actions=[
                "Réessaie une fois avec un mot-clé plus court.",
                "Sinon, dis à Madeleine que tu ne trouves pas cet ingrédient.",
            ],
        )
    alertes = sum(1 for i in items if i["sous_seuil"])
    return succes(f"{len(items)} ingrédient(s) trouvé(s), dont {alertes} sous le seuil d'alerte.", data)


async def _consulter_ventes(deps: Deps, recherche: str | None, debut: date, fin: date) -> str:
    toutes = await deps.repo.lister_ventes()
    disponibles = (
        {"debut": min(v.jour for v in toutes).isoformat(), "fin": max(v.jour for v in toutes).isoformat()}
        if toutes
        else None
    )
    retenues = [v for v in toutes if debut <= v.jour <= fin and correspond(recherche, v.produit)]
    cumuls: dict[str, list[float]] = {}
    for v in retenues:
        cumul = cumuls.setdefault(v.produit, [0.0, 0.0])
        cumul[0] += v.quantite
        cumul[1] += v.ca
    par_produit = [
        {"produit": produit, "quantite": arrondi(q), "ca": arrondi(ca)}
        for produit, (q, ca) in sorted(cumuls.items(), key=lambda kv: -kv[1][0])
    ]
    data = {
        "periode": {"debut": debut.isoformat(), "fin": fin.isoformat()},
        "par_produit": par_produit,
        "total_quantite": arrondi(sum(v.quantite for v in retenues)) or 0,
        "total_ca": arrondi(sum(v.ca for v in retenues)) or 0,
        "nb_lignes": len(retenues),
        "donnees_disponibles": disponibles,
    }
    if not retenues:
        couverture = (
            f"Les ventes enregistrées vont du {disponibles['debut']} au {disponibles['fin']}."
            if disponibles
            else "Aucune vente n'est enregistrée."
        )
        return avertissement(
            f"Aucune vente trouvée du {debut} au {fin}. {couverture}",
            data,
            next_actions=["Dis à Madeleine qu'il n'y a pas de ventes enregistrées pour cette période."],
        )
    resume = f"{data['total_quantite']} article(s) vendu(s) pour {data['total_ca']} € du {debut} au {fin}."
    if disponibles and (debut.isoformat() < disponibles["debut"] or fin.isoformat() > disponibles["fin"]):
        resume += f" Attention : les données ne couvrent que du {disponibles['debut']} au {disponibles['fin']}."
    return succes(resume, data)


async def _consulter_catalogue(deps: Deps, recherche: str | None) -> str:
    produits = [p for p in await deps.repo.lister_catalogue() if correspond(recherche, p.nom)]
    items = [
        {
            "produit": p.nom,
            "categorie": p.categorie,
            "prix_vente_ttc": arrondi(p.prix),
            "cout_revient": arrondi(p.cout),
            "marge_unitaire": arrondi(p.prix - p.cout) if p.prix is not None and p.cout is not None else None,
            "marge_pct": arrondi(p.marge_pct),
            "ingredients": p.ingredients,
            "temps_preparation_min": arrondi(p.temps_preparation),
            "disponible": p.disponible,
        }
        for p in produits
    ]
    data = {"items": items, "nb_resultats": len(items)}
    if not items:
        return avertissement(
            f"Aucun produit ne correspond à « {recherche} ».",
            data,
            next_actions=[
                "Réessaie une fois avec un mot-clé plus court.",
                "Sinon, dis à Madeleine que tu ne trouves pas ce produit.",
            ],
        )
    return succes(f"{len(items)} produit(s) trouvé(s) dans le catalogue.", data)


# --- Outil 3 : prevoir_production ----------------------------------------------

class PrevoirArgs(BaseModel):
    date_cible: date = Field(
        description="Jour à préparer, AAAA-MM-JJ. Convertis « demain » avec le calendrier du prompt."
    )
    produit: str | None = Field(
        default=None, description="Mot-clé du produit (ex. 'baguette'). Laisser vide pour tous les produits."
    )
    fenetre_jours: int = Field(
        default=28, ge=7, le=90, description="Nombre de jours d'historique pris en compte avant la date cible."
    )


async def _prevoir_production(deps: Deps, date_cible: date, produit: str | None, fenetre_jours: int) -> str:
    ventes = [v for v in await deps.repo.lister_ventes() if correspond(produit, v.produit)]
    lignes = prevoir(ventes, date_cible, fenetre_jours)
    debut, fin = fenetre(date_cible, fenetre_jours)
    jour = jour_fr(date_cible)
    data = {
        "date_cible": date_cible.isoformat(),
        "jour": jour,
        "fenetre": {"debut": debut.isoformat(), "fin": fin.isoformat()},
        "coefficient": COEFFICIENT,
        "produits": [
            {
                "produit": l.produit,
                "observations": l.observations,
                "moyenne": arrondi(l.moyenne),
                "recommandation": l.recommandation,
            }
            for l in lignes
        ],
    }
    if not lignes:
        return avertissement(
            f"Aucune vente un {jour} entre le {debut} et le {fin} : pas de prévision possible.",
            data,
            next_actions=["Dis à Madeleine qu'il n'y a pas d'historique pour ce jour ; ne propose aucune quantité."],
        )
    if any(l.observations < OBSERVATIONS_MINIMALES for l in lignes):
        return avertissement(
            f"Prévision pour le {jour} {date_cible} calculée sur peu de {jour}s "
            f"(moins de {OBSERVATIONS_MINIMALES} observations) : estimation fragile.",
            data,
            next_actions=["Donne les recommandations en précisant que l'estimation est fragile."],
        )
    return succes(f"Prévision pour le {jour} {date_cible} : moyenne des {jour}s + 10 %.", data)


def build_tools(deps: Deps) -> list[BaseTool]:
    async def consulter_boulangerie(
        table: str,
        recherche: str | None = None,
        date_debut: date | None = None,
        date_fin: date | None = None,
        sous_seuil_uniquement: bool = False,
    ) -> str:
        if sous_seuil_uniquement and table != "stock":
            return _parametre_invalide("sous_seuil_uniquement ne s'applique qu'à table='stock'.")
        try:
            if table == "stock":
                return await _consulter_stock(deps, recherche, sous_seuil_uniquement)
            if table == "catalogue":
                return await _consulter_catalogue(deps, recherche)
            if table == "ventes":
                if date_debut is None or date_fin is None:
                    return erreur(
                        "PERIODE_MANQUANTE",
                        "Il faut une période (date de début et de fin) pour lire les ventes.",
                        cause="date_debut ou date_fin est absente.",
                        retry="Ne réessaie pas avec des dates inventées.",
                        stop="Demande à Madeleine de quelle période elle parle.",
                    )
                if date_debut > date_fin:
                    return _parametre_invalide("date_debut est après date_fin.")
                return await _consulter_ventes(deps, recherche, date_debut, date_fin)
            return _parametre_invalide(f"Table non prise en charge : {table}.")
        except NotionIndisponible:
            return notion_indisponible()

    async def prevoir_production(date_cible: date, produit: str | None = None, fenetre_jours: int = 28) -> str:
        try:
            return await _prevoir_production(deps, date_cible, produit, fenetre_jours)
        except NotionIndisponible:
            return notion_indisponible()

    return [
        StructuredTool.from_function(
            coroutine=consulter_boulangerie,
            name="consulter_boulangerie",
            description=(
                "Lit les données de la boulangerie : stock d'ingrédients (quantités, seuils d'alerte, "
                "fournisseurs), ventes sur une période (quantités, chiffre d'affaires) ou catalogue "
                "des produits (prix, coût de revient, marge). Seule source autorisée pour ces chiffres."
            ),
            args_schema=ConsulterArgs,
        ),
        StructuredTool.from_function(
            coroutine=prevoir_production,
            name="prevoir_production",
            description=(
                "Estime combien préparer de chaque produit pour un jour donné : moyenne des ventes du "
                "même jour de la semaine sur l'historique, plus 10 % de marge de sécurité."
            ),
            args_schema=PrevoirArgs,
        ),
    ]
