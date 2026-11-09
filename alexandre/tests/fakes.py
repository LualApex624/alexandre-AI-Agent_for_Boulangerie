"""Doublures des services externes, au niveau de leur interface publique.

FakeNotionClient imite le sous-ensemble du SDK `notion_client.AsyncClient`
utilisé par l'application (databases.retrieve, data_sources.query paginé,
pages.create) et renvoie des pages au format exact de l'API Notion.
"""

from __future__ import annotations

from typing import Any

from notion_client.errors import RequestTimeoutError

DB_STOCK, DB_VENTES, DB_CATALOGUE, DB_COMMANDES = "db-stock", "db-ventes", "db-catalogue", "db-commandes"


# --- Constructeurs de pages au format de l'API Notion -----------------------

def _title(text: str | None) -> dict:
    return {"type": "title", "title": [{"plain_text": text}] if text else []}


def _rich(text: str | None) -> dict:
    return {"type": "rich_text", "rich_text": [{"plain_text": text}] if text else []}


def _number(value: float | None) -> dict:
    return {"type": "number", "number": value}


def _select(name: str | None) -> dict:
    return {"type": "select", "select": {"name": name} if name else None}


def _date(value: str | None) -> dict:
    return {"type": "date", "date": {"start": value} if value else None}


def page_stock(ingredient, quantite, unite, seuil, fournisseur, email, prix, livraison=None) -> dict:
    return {
        "id": f"page-{ingredient}",
        "properties": {
            "Ingrédient": _title(ingredient),
            "Quantité en stock": _number(quantite),
            "Unité": _select(unite),
            "Seuil alerte": _number(seuil),
            "Fournisseur": _select(fournisseur),
            "Email fournisseur": {"type": "email", "email": email},
            "Prix unitaire (€)": _number(prix),
            "Dernière livraison": _date(livraison),
        },
    }


def page_vente(produit, quantite, ca, jour_iso) -> dict:
    return {
        "id": f"vente-{produit}-{jour_iso}",
        "properties": {
            "Vente": _title(f"{produit} {jour_iso}"),
            "Produit": _select(produit),
            "Quantité vendue": _number(quantite),
            "CA (€)": _number(ca),
            "Date": _date(jour_iso),
            "Jour": _select("Lundi"),
        },
    }


def page_produit(produit, categorie, prix, cout, marge_pct, ingredients, temps, disponible=True) -> dict:
    return {
        "id": f"produit-{produit}",
        "properties": {
            "Produit": _title(produit),
            "Catégorie": _select(categorie),
            "Prix de vente TTC (€)": _number(prix),
            "Coût de revient (€)": _number(cout),
            "Marge (%)": {"type": "formula", "formula": {"type": "number", "number": marge_pct}},
            "Ingrédients principaux": _rich(ingredients),
            "Temps de préparation (min)": _number(temps),
            "Disponible": {"type": "checkbox", "checkbox": disponible},
        },
    }


def jeu_de_donnees() -> dict[str, list[dict]]:
    """Jeu de référence. Les valeurs attendues des tests sont calculées à la main."""
    return {
        DB_STOCK: [
            page_stock("Beurre AOP", 8, "kg", 10, "Laiterie du Midi", "contact@laiterie-du-midi.fr", 6.6, "2026-02-10"),
            page_stock("Farine T65", 120, "kg", 50, "Minoterie Dupont", "commandes@minoterie-dupont.fr", 0.95, "2026-02-12"),
            page_stock("Amandes en poudre", 2, "kg", 3, "Épicerie Fine Martin", "pro@epicerie-martin.fr", 18.0),
            page_stock("Levure fraîche", 5, "kg", 5, "Minoterie Dupont", "commandes@minoterie-dupont.fr", 4.2),
        ],
        DB_CATALOGUE: [
            page_produit("Éclair au chocolat", "Pâtisserie", 3.20, 1.10, 65.6, "Pâte à choux, crème pâtissière chocolat", 45),
            page_produit("Croissant pur beurre", "Viennoiserie", 1.30, 0.42, 67.7, "Farine, beurre AOP, levure", 30),
            page_produit("Baguette tradition", "Pain", 1.30, 0.35, 73.1, "Farine T65, levain, sel", 20),
        ],
        DB_VENTES: [
            page_vente("Croissant pur beurre", 100, 130.0, "2026-02-03"),  # mardi
            page_vente("Baguette tradition", 180, 234.0, "2026-02-03"),  # mardi
            page_vente("Croissant pur beurre", 120, 156.0, "2026-02-09"),  # lundi
            page_vente("Baguette tradition", 150, 195.0, "2026-02-09"),  # lundi
            page_vente("Croissant pur beurre", 110, 143.0, "2026-02-10"),  # mardi
            page_vente("Baguette tradition", 200, 260.0, "2026-02-10"),  # mardi
            page_vente("Croissant pur beurre", 200, 260.0, "2026-02-14"),  # samedi
            page_vente("Éclair au chocolat", 40, 128.0, "2026-02-14"),  # samedi
        ],
        DB_COMMANDES: [],
    }


# --- Faux client Notion --------------------------------------------------------

class FakeNotionClient:
    def __init__(self, tables: dict[str, list[dict]] | None = None, page_size: int = 2):
        self.tables = tables if tables is not None else jeu_de_donnees()
        self.page_size = page_size
        self.retrieve_calls = 0
        self.query_calls = 0
        self.created: list[dict] = []
        self.query_error: Exception | None = None
        self.create_error: Exception | None = None
        self.databases = _Databases(self)
        self.data_sources = _DataSources(self)
        self.pages = _Pages(self)


class _Databases:
    def __init__(self, client: FakeNotionClient):
        self._c = client

    async def retrieve(self, database_id: str, **_: Any) -> dict:
        self._c.retrieve_calls += 1
        if database_id not in self._c.tables:
            raise RequestTimeoutError()
        return {"id": database_id, "data_sources": [{"id": f"ds-{database_id}"}]}


class _DataSources:
    def __init__(self, client: FakeNotionClient):
        self._c = client

    async def query(self, data_source_id: str, start_cursor: str | None = None, **_: Any) -> dict:
        self._c.query_calls += 1
        if self._c.query_error is not None:
            raise self._c.query_error
        rows = self._c.tables[data_source_id.removeprefix("ds-")]
        start = int(start_cursor) if start_cursor else 0
        end = start + self._c.page_size
        has_more = end < len(rows)
        return {"results": rows[start:end], "has_more": has_more, "next_cursor": str(end) if has_more else None}


class _Pages:
    def __init__(self, client: FakeNotionClient):
        self._c = client

    async def create(self, parent: dict, properties: dict, **_: Any) -> dict:
        if self._c.create_error is not None:
            raise self._c.create_error
        page = {"id": f"page-commande-{len(self._c.created) + 1}", "parent": parent, "properties": properties}
        self._c.created.append(page)
        return page


# --- Faux SMTP -----------------------------------------------------------------

class FakeMailer:
    def __init__(self, error: Exception | None = None):
        self.sent: list[dict] = []
        self.error = error

    async def envoyer(self, destinataire: str, objet: str, corps: str) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append({"destinataire": destinataire, "objet": objet, "corps": corps})


# --- Faux modèle de langage scripté ----------------------------------------------

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, BaseMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from pydantic import Field  # noqa: E402


class ScriptedChatModel(BaseChatModel):
    """Rejoue des réponses prédéfinies (texte, appels d'outils ou exceptions) et
    enregistre les messages reçus à chaque appel."""

    reponses: list[Any] = Field(default_factory=list)
    appels: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.appels.append(list(messages))
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return ChatResult(generations=[ChatGeneration(message=reponse)])


def appel_outil(nom: str, arguments: dict, identifiant: str = "appel-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nom, "args": arguments, "id": identifiant}])
