"""Point d'entrée A — outil 2 `passer_commande` (S4). La validation humaine est testée au niveau du graphe."""

import json
import re
import smtplib

import pytest
from notion_client.errors import RequestTimeoutError

from boulangerie.tools import build_tools

COMMANDE = {
    "fournisseur": "minoterie dupont",
    "produits": "50 kg de Farine T65",
    "objet": "Commande de farine T65",
    "corps": "Madame, Monsieur,\n\nJe souhaite commander 50 kg de farine T65.\n\nCordialement,\nMadeleine Croûton",
    "montant_estime": 47.5,
}


async def test_une_commande_validee_envoie_l_email_au_fournisseur_lu_dans_notion_et_la_trace(
    appeler, mailer, notion
):
    resultat = await appeler("passer_commande", **COMMANDE)

    assert resultat["status"] == "success"
    assert mailer.sent == [
        {"destinataire": "commandes@minoterie-dupont.fr", "objet": COMMANDE["objet"], "corps": COMMANDE["corps"]}
    ]
    assert len(notion.created) == 1
    page = notion.created[0]
    props = page["properties"]
    reference = props["Référence commande"]["title"][0]["text"]["content"]
    assert re.fullmatch(r"CMD-20261109-[A-Z0-9]{4}", reference)
    assert page["parent"] == {"type": "data_source_id", "data_source_id": "ds-db-commandes"}
    assert props["Fournisseur"] == {"select": {"name": "Minoterie Dupont"}}  # nom canonique Notion
    assert props["Email envoyé à"] == {"email": "commandes@minoterie-dupont.fr"}
    assert props["Date commande"] == {"date": {"start": "2026-11-09"}}
    assert props["Statut"] == {"select": {"name": "Envoyée"}}
    assert props["Montant estimé (€)"] == {"number": 47.5}
    assert props["Produits commandés"]["rich_text"][0]["text"]["content"] == "50 kg de Farine T65"
    assert props["Notes"]["rich_text"][0]["text"]["content"] == COMMANDE["corps"]
    assert resultat["artifacts"] == {"reference": reference, "notion_page_id": "page-commande-1"}


async def test_le_modele_ne_peut_pas_choisir_l_adresse_du_destinataire(deps):
    outil = next(t for t in build_tools(deps) if t.name == "passer_commande")

    assert set(outil.args) == {"fournisseur", "produits", "objet", "corps", "montant_estime"}


async def test_un_fournisseur_inconnu_n_envoie_rien_et_liste_les_fournisseurs_valides(appeler, mailer, notion):
    resultat = await appeler("passer_commande", **{**COMMANDE, "fournisseur": "Moulins Inconnus"})

    assert resultat["status"] == "error"
    assert resultat["error"]["code"] == "FOURNISSEUR_INCONNU"
    assert resultat["data"]["fournisseurs_connus"] == ["Épicerie Fine Martin", "Laiterie du Midi", "Minoterie Dupont"]
    assert mailer.sent == [] and notion.created == []


async def test_un_echec_smtp_n_ecrit_rien_dans_notion(appeler, mailer, notion):
    mailer.error = smtplib.SMTPAuthenticationError(535, b"bad credentials")

    resultat = await appeler("passer_commande", **COMMANDE)

    assert resultat["status"] == "error"
    assert resultat["error"]["code"] == "EMAIL_ECHEC"
    assert notion.created == []


async def test_email_parti_mais_notion_en_echec_garde_une_trace_locale_et_interdit_de_relancer(
    appeler, mailer, notion, deps
):
    notion.create_error = RequestTimeoutError()

    resultat = await appeler("passer_commande", **COMMANDE)

    assert resultat["status"] == "warning"
    assert resultat["error"]["code"] == "COMMANDE_NON_TRACEE"
    assert "jamais" in resultat["error"]["retry"].lower()
    assert len(mailer.sent) == 1
    trace = deps.trace_dir / "commandes_non_tracees.jsonl"
    enregistrement = json.loads(trace.read_text(encoding="utf-8").splitlines()[0])
    assert enregistrement["reference"] == resultat["artifacts"]["reference"]
    assert enregistrement["corps"] == COMMANDE["corps"]
    assert enregistrement["email"] == "commandes@minoterie-dupont.fr"
    assert resultat["artifacts"]["trace_locale"] == str(trace)


@pytest.mark.parametrize("objet", ["Commande\nBcc: pirate@example.com", "Commande\r\nX: y", ""])
async def test_un_objet_invalide_ou_avec_injection_d_en_tete_est_refuse(appeler, mailer, objet):
    resultat = await appeler("passer_commande", **{**COMMANDE, "objet": objet})

    assert resultat["status"] == "error"
    assert resultat["error"]["code"] == "PARAMETRE_INVALIDE"
    assert mailer.sent == []


async def test_sans_configuration_smtp_l_envoi_est_refuse_proprement(appeler, deps, notion):
    deps.mailer = None

    resultat = await appeler("passer_commande", **COMMANDE)

    assert resultat["error"]["code"] == "EMAIL_NON_CONFIGURE"
    assert notion.created == []
