import json
from datetime import date, datetime

import pytest

from boulangerie.notion_repo import NotionIds, NotionRepository
from boulangerie.tools import CLE_VALIDATION, Deps, build_tools
from tests.fakes import DB_CATALOGUE, DB_COMMANDES, DB_STOCK, DB_VENTES, FakeMailer, FakeNotionClient

DATE_REFERENCE = date(2026, 2, 16)
IDS = NotionIds(stock=DB_STOCK, ventes=DB_VENTES, catalogue=DB_CATALOGUE, commandes=DB_COMMANDES)


@pytest.fixture
def notion() -> FakeNotionClient:
    return FakeNotionClient()


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def deps(notion, mailer, tmp_path) -> Deps:
    return Deps(
        repo=NotionRepository(notion, IDS),
        mailer=mailer,
        trace_dir=tmp_path / "var",
        clock=lambda: datetime(2026, 11, 9, 10, 30),
    )


@pytest.fixture
def appeler(deps):
    """Appelle un outil comme le fait l'agent après validation de Madeleine, et décode l'enveloppe JSON."""
    tools = {t.name: t for t in build_tools(deps)}

    async def _appeler(nom: str, **arguments) -> dict:
        return json.loads(await tools[nom].ainvoke(arguments, config={"configurable": {CLE_VALIDATION: True}}))

    return _appeler
