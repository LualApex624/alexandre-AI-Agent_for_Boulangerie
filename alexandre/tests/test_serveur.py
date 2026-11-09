"""Serveur web : page, sécurité et protocole WebSocket, de bout en bout avec un modèle scripté."""

import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from starlette.websockets import WebSocketDisconnect

from boulangerie.agent import build_agent
from boulangerie.conversation import Conversation
from boulangerie.serveur import Runtime, creer_app, creer_alerte
from boulangerie.tools import build_tools
from tests.conftest import DATE_REFERENCE
from tests.fakes import ScriptedChatModel, appel_outil
from tests.test_passer_commande import COMMANDE

ORIGINE = "http://localhost:8000"


@pytest.fixture
def scenario(deps):
    """Fabrique un client dont le modèle rejoue les réponses données."""

    def _client(*reponses) -> TestClient:
        modele = ScriptedChatModel(reponses=list(reponses))
        outils = build_tools(deps)
        agent = build_agent(modele, outils, DATE_REFERENCE, max_retries=0)
        runtime = Runtime(
            creer_conversation=lambda fil: Conversation(agent, thread_id=fil, repo=deps.repo),
            alerte=creer_alerte(outils),
            date_reference=DATE_REFERENCE,
            origines=frozenset({ORIGINE}),
        )
        return TestClient(creer_app(runtime))

    return _client


def _jusqua(ws, type_attendu: str) -> tuple[list[dict], dict]:
    """Lit les événements jusqu'à celui du type attendu ; renvoie (précédents, attendu)."""
    vus = []
    while True:
        evenement = ws.receive_json()
        if evenement["type"] == type_attendu:
            return vus, evenement
        vus.append(evenement)


def test_la_page_est_servie_avec_des_en_tetes_de_securite(scenario):
    reponse = scenario().get("/")

    assert reponse.status_code == 200
    assert "Alexandre" in reponse.text
    csp = reponse.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert reponse.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("entetes", [{"origin": "https://site-pirate.example"}, {}])
def test_une_connexion_depuis_une_autre_origine_est_refusee(scenario, entetes):
    with pytest.raises(WebSocketDisconnect) as exc:
        with scenario().websocket_connect("/ws", headers=entetes) as ws:
            ws.receive_json()

    assert exc.value.code == 1008


def test_la_bienvenue_donne_la_date_de_demo_et_l_alerte_stock_reelle(scenario):
    with scenario().websocket_connect("/ws", headers={"origin": ORIGINE}) as ws:
        bienvenue = ws.receive_json()

    assert bienvenue["type"] == "bienvenue"
    assert bienvenue["date"] == "lundi 16/02/2026"
    alerte = bienvenue["alerte"]
    assert alerte["titre"] == "À commander en priorité"
    assert [i["ingredient"] for i in alerte["items"]] == ["Amandes en poudre", "Beurre AOP", "Levure fraîche"]


def test_un_message_emet_l_humeur_les_appels_d_outils_puis_la_reponse_avec_sa_carte(scenario):
    client = scenario(
        appel_outil("consulter_boulangerie", {"table": "stock", "recherche": "beurre"}),
        AIMessage(content="Il te reste **8 kg** de beurre."),
    )
    with client.websocket_connect("/ws", headers={"origin": ORIGINE}) as ws:
        ws.receive_json()  # bienvenue
        ws.send_json({"type": "message", "texte": "Il me reste combien de beurre ?"})
        avant, reponse = _jusqua(ws, "reponse")

    assert avant[0] == {"type": "humeur", "valeur": "petrit"}
    outils = [(e["nom"], e["etat"]) for e in avant if e["type"] == "outil"]
    assert outils == [("consulter_boulangerie", "debut"), ("consulter_boulangerie", "fin")]
    assert reponse["texte"] == "Il te reste **8 kg** de beurre."
    assert [c["type"] for c in reponse["cartes"]] == ["stock"]


def test_une_commande_attend_la_validation_puis_part_une_seule_fois(scenario, mailer, notion):
    client = scenario(appel_outil("passer_commande", COMMANDE), AIMessage(content="C'est parti."))
    with client.websocket_connect("/ws", headers={"origin": ORIGINE}) as ws:
        ws.receive_json()
        ws.send_json({"type": "message", "texte": "Commande de farine"})
        _, validation = _jusqua(ws, "validation")
        assert mailer.sent == []
        ws.send_json({"type": "validation", "decisions": [True]})
        _, reponse = _jusqua(ws, "reponse")

    (demande,) = validation["demandes"]
    assert demande["destinataire"] == "commandes@minoterie-dupont.fr"
    assert demande["corps"] == COMMANDE["corps"]
    assert reponse["texte"] == "C'est parti."
    assert [c["type"] for c in reponse["cartes"]] == ["commande"]
    assert len(mailer.sent) == 1 and len(notion.created) == 1


def test_une_validation_sans_commande_en_attente_est_refusee(scenario, mailer):
    with scenario().websocket_connect("/ws", headers={"origin": ORIGINE}) as ws:
        ws.receive_json()
        ws.send_json({"type": "validation", "decisions": [True]})
        erreur = ws.receive_json()

    assert erreur["type"] == "erreur"
    assert mailer.sent == []


@pytest.mark.parametrize(
    "brut",
    [
        "pas du json",
        json.dumps({"type": "inconnu"}),
        json.dumps({"type": "message", "texte": ""}),
        json.dumps({"type": "message", "texte": "x" * 2001}),
        json.dumps({"type": "validation", "decisions": ["oui"]}),
    ],
)
def test_un_message_invalide_renvoie_une_erreur_sans_couper_la_connexion(scenario, brut):
    client = scenario(AIMessage(content="Bonjour Madeleine !"))
    with client.websocket_connect("/ws", headers={"origin": ORIGINE}) as ws:
        ws.receive_json()
        ws.send_text(brut)
        assert ws.receive_json()["type"] == "erreur"
        ws.send_json({"type": "message", "texte": "Bonjour"})
        _, reponse = _jusqua(ws, "reponse")

    assert reponse["texte"] == "Bonjour Madeleine !"
