"""Accès asynchrone aux quatre bases Notion de la boulangerie.

- Le `data_source_id` de chaque base est résolu une fois puis mis en cache.
- Toutes les lectures suivent la pagination (`has_more` / `next_cursor`).
- Les pages sont converties en objets typés ; une ligne incomplète est
  ignorée (et journalisée) plutôt que de faire échouer toute la lecture.
- Toute erreur réseau ou d'API devient `NotionIndisponible`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx
from notion_client.errors import NotionClientErrorBase

log = logging.getLogger(__name__)

PAGE_SIZE = 100


class NotionIndisponible(Exception):
    """Notion n'a pas pu répondre (réseau, délai, droits, réponse inattendue)."""


@dataclass(frozen=True)
class NotionIds:
    stock: str
    ventes: str
    catalogue: str
    commandes: str


@dataclass(frozen=True)
class Ingredient:
    nom: str
    quantite: float | None
    unite: str | None
    seuil: float | None
    fournisseur: str | None
    email: str | None
    prix_unitaire: float | None
    derniere_livraison: str | None

    @property
    def sous_seuil(self) -> bool:
        return self.quantite is not None and self.seuil is not None and self.quantite <= self.seuil


@dataclass(frozen=True)
class Vente:
    produit: str
    quantite: float
    ca: float
    jour: date


@dataclass(frozen=True)
class Produit:
    nom: str
    categorie: str | None
    prix: float | None
    cout: float | None
    marge_pct: float | None
    ingredients: str | None
    temps_preparation: float | None
    disponible: bool


@dataclass(frozen=True)
class NouvelleCommande:
    reference: str
    jour: date
    fournisseur: str
    email: str
    produits: str
    montant_estime: float | None
    notes: str


# --- Lecture tolérante des propriétés Notion -----------------------------------

def _texte(prop: dict | None) -> str | None:
    if not prop:
        return None
    morceaux = prop.get(prop.get("type", ""), None)
    if isinstance(morceaux, list):
        texte = "".join(m.get("plain_text", "") for m in morceaux).strip()
        return texte or None
    return None


def _nombre(prop: dict | None) -> float | None:
    if not prop:
        return None
    if prop.get("type") == "formula":
        return (prop.get("formula") or {}).get("number")
    return prop.get("number")


def _select(prop: dict | None) -> str | None:
    return ((prop or {}).get("select") or {}).get("name")


def _date(prop: dict | None) -> str | None:
    return ((prop or {}).get("date") or {}).get("start")


def _email(prop: dict | None) -> str | None:
    return (prop or {}).get("email")


class NotionRepository:
    def __init__(self, client: Any, ids: NotionIds):
        self._client = client
        self._ids = ids
        self._data_sources: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def _data_source_id(self, database_id: str) -> str:
        async with self._lock:
            if database_id not in self._data_sources:
                base = await self._client.databases.retrieve(database_id=database_id)
                self._data_sources[database_id] = base["data_sources"][0]["id"]
            return self._data_sources[database_id]

    async def _lire_tout(self, database_id: str) -> list[dict]:
        try:
            data_source_id = await self._data_source_id(database_id)
            pages: list[dict] = []
            curseur: str | None = None
            while True:
                kwargs: dict[str, Any] = {"data_source_id": data_source_id, "page_size": PAGE_SIZE}
                if curseur:
                    kwargs["start_cursor"] = curseur
                reponse = await self._client.data_sources.query(**kwargs)
                pages.extend(reponse["results"])
                if not reponse.get("has_more"):
                    return pages
                curseur = reponse["next_cursor"]
        except (NotionClientErrorBase, httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            log.warning("Lecture Notion impossible (%s) : %s", database_id, type(exc).__name__)
            raise NotionIndisponible from exc

    async def lister_stock(self) -> list[Ingredient]:
        ingredients = []
        for page in await self._lire_tout(self._ids.stock):
            p = page.get("properties", {})
            nom = _texte(p.get("Ingrédient"))
            if not nom:
                log.info("Ligne de stock sans nom ignorée (%s)", page.get("id"))
                continue
            ingredients.append(
                Ingredient(
                    nom=nom,
                    quantite=_nombre(p.get("Quantité en stock")),
                    unite=_select(p.get("Unité")),
                    seuil=_nombre(p.get("Seuil alerte")),
                    fournisseur=_select(p.get("Fournisseur")),
                    email=_email(p.get("Email fournisseur")),
                    prix_unitaire=_nombre(p.get("Prix unitaire (€)")),
                    derniere_livraison=_date(p.get("Dernière livraison")),
                )
            )
        return ingredients

    async def lister_ventes(self) -> list[Vente]:
        ventes = []
        for page in await self._lire_tout(self._ids.ventes):
            p = page.get("properties", {})
            produit = _select(p.get("Produit"))
            quantite = _nombre(p.get("Quantité vendue"))
            jour = _date(p.get("Date"))
            if not produit or quantite is None or not jour:
                log.info("Ligne de vente incomplète ignorée (%s)", page.get("id"))
                continue
            try:
                jour_date = date.fromisoformat(jour[:10])
            except ValueError:
                log.info("Date de vente illisible ignorée (%s)", page.get("id"))
                continue
            ventes.append(
                Vente(produit=produit, quantite=quantite, ca=_nombre(p.get("CA (€)")) or 0.0, jour=jour_date)
            )
        return ventes

    async def lister_catalogue(self) -> list[Produit]:
        produits = []
        for page in await self._lire_tout(self._ids.catalogue):
            p = page.get("properties", {})
            nom = _texte(p.get("Produit"))
            if not nom:
                log.info("Produit sans nom ignoré (%s)", page.get("id"))
                continue
            produits.append(
                Produit(
                    nom=nom,
                    categorie=_select(p.get("Catégorie")),
                    prix=_nombre(p.get("Prix de vente TTC (€)")),
                    cout=_nombre(p.get("Coût de revient (€)")),
                    marge_pct=_nombre(p.get("Marge (%)")),
                    ingredients=_texte(p.get("Ingrédients principaux")),
                    temps_preparation=_nombre(p.get("Temps de préparation (min)")),
                    disponible=bool((p.get("Disponible") or {}).get("checkbox")),
                )
            )
        return produits
